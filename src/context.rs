use crate::types::Task;
use anyhow::Result;
use std::path::PathBuf;

pub struct ContextBuilder {
    project_root: PathBuf,
}

impl ContextBuilder {
    pub fn new(project_root: PathBuf) -> Self {
        Self { project_root }
    }

    pub fn orchestrator_prompt(&self, spec: &str) -> Result<String> {
        let repo_map = crate::repo_map::build_repo_map(&self.project_root)?;
        Ok(format!(
            "You are a software orchestrator. Break the following spec into an ordered list of atomic tasks.\n\
             Output ONLY a JSON array matching this schema:\n\
             [{{\"id\":\"001\",\"title\":\"...\",\"description\":\"...\",\
             \"relevant_files\":[\"path/or/dir/\"],\"depends_on\":[]}}]\n\n\
             # Spec\n{spec}\n\n# Repository Map\n{repo_map}"
        ))
    }

    pub fn coder_prompt(
        &self,
        task: &Task,
        completed_summaries: &[String],
        failure_reason: Option<&str>,
    ) -> Result<String> {
        let repo_map = crate::repo_map::build_repo_map(&self.project_root)?;
        let relevant = self.read_relevant_files(&task.relevant_files)?;

        let mut prompt = format!(
            "You are a software engineer. Implement the following task.\n\n\
             # Task {}: {}\n{}\n\n\
             # Repository Map\n{}\n\n\
             # Relevant Files\n{}",
            task.id, task.title, task.description, repo_map, relevant
        );

        if !completed_summaries.is_empty() {
            prompt.push_str("\n\n# Previously Completed Tasks\n");
            for s in completed_summaries {
                prompt.push_str(&format!("- {s}\n"));
            }
        }

        if let Some(reason) = failure_reason {
            prompt.push_str(&format!(
                "\n\n# Previous Attempt Failed\nVerifier rejection reason:\n{reason}"
            ));
        }

        Ok(prompt)
    }

    pub fn verifier_prompt(&self, spec: &str, task: &Task, diff: &str) -> String {
        format!(
            "You are a strict verifier. Check whether the implementation matches the spec.\n\
             Output ONLY valid JSON: {{\"passed\": true/false, \"reason\": \"...\"}}\n\n\
             # Spec\n{spec}\n\n\
             # Task {}: {}\n{}\n\n\
             # Changes (git diff)\n```diff\n{diff}\n```",
            task.id, task.title, task.description
        )
    }

    pub fn planner_prompt(&self, task_description: &str, history: &[(String, String)]) -> String {
        let mut prompt = format!(
            "You are a planning assistant. Ask clarifying questions about the user's task.\n\
             When you have enough information, write a complete spec inside <spec>...</spec> tags.\n\n\
             # Task\n{task_description}\n"
        );
        if !history.is_empty() {
            prompt.push_str("\n# Previous Clarifications\n");
            for (q, a) in history {
                prompt.push_str(&format!("Q: {q}\nA: {a}\n\n"));
            }
        }
        prompt
    }

    fn read_relevant_files(&self, paths: &[String]) -> Result<String> {
        let mut out = String::new();
        for p in paths {
            let full = self.project_root.join(p);
            if full.is_file() {
                let content = std::fs::read_to_string(&full)?;
                out.push_str(&format!("## {p}\n```\n{content}\n```\n\n"));
            } else if full.is_dir() {
                for entry in std::fs::read_dir(&full)?.flatten() {
                    if entry.path().is_file() {
                        let content = std::fs::read_to_string(entry.path())?;
                        let rel = entry.path().to_string_lossy().to_string();
                        out.push_str(&format!("## {rel}\n```\n{content}\n```\n\n"));
                    }
                }
            }
        }
        Ok(out)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    fn make_task() -> Task {
        Task {
            id: "001".into(),
            title: "Add auth".into(),
            description: "Implement JWT".into(),
            relevant_files: vec![],
            depends_on: vec![],
        }
    }

    #[test]
    fn test_coder_prompt_contains_task_info() {
        let dir = tempdir().unwrap();
        let cb = ContextBuilder::new(dir.path().to_path_buf());
        let prompt = cb.coder_prompt(&make_task(), &[], None).unwrap();
        assert!(prompt.contains("Add auth"));
        assert!(prompt.contains("Implement JWT"));
    }

    #[test]
    fn test_coder_prompt_includes_failure_reason() {
        let dir = tempdir().unwrap();
        let cb = ContextBuilder::new(dir.path().to_path_buf());
        let prompt = cb.coder_prompt(&make_task(), &[], Some("tests missing")).unwrap();
        assert!(prompt.contains("tests missing"));
    }

    #[test]
    fn test_verifier_prompt_contains_diff() {
        let dir = tempdir().unwrap();
        let cb = ContextBuilder::new(dir.path().to_path_buf());
        let prompt = cb.verifier_prompt("# Spec", &make_task(), "+fn foo() {}");
        assert!(prompt.contains("+fn foo()"));
        assert!(prompt.contains("passed"));
    }

    #[test]
    fn test_planner_prompt_includes_history() {
        let dir = tempdir().unwrap();
        let cb = ContextBuilder::new(dir.path().to_path_buf());
        let history = vec![("What auth?".into(), "JWT".into())];
        let prompt = cb.planner_prompt("Add login", &history);
        assert!(prompt.contains("What auth?"));
        assert!(prompt.contains("JWT"));
    }

    #[test]
    fn test_reads_relevant_file() {
        let dir = tempdir().unwrap();
        std::fs::write(dir.path().join("auth.rs"), "pub fn verify() {}").unwrap();
        let task = Task {
            id: "001".into(),
            title: "T".into(),
            description: "D".into(),
            relevant_files: vec!["auth.rs".into()],
            depends_on: vec![],
        };
        let cb = ContextBuilder::new(dir.path().to_path_buf());
        let prompt = cb.coder_prompt(&task, &[], None).unwrap();
        assert!(prompt.contains("pub fn verify()"));
    }
}
