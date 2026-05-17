use crate::{
    agent::AgentProvider,
    config::Config,
    context::ContextBuilder,
    recorder::FileRecorder,
    state::{Checkpoint, RunState},
    types::{RunSummary, Task, VerifierResult},
};
use anyhow::Result;
use std::path::PathBuf;

pub struct RoleAgents {
    pub planner: Box<dyn AgentProvider>,
    pub orchestrator: Box<dyn AgentProvider>,
    pub coder: Box<dyn AgentProvider>,
    pub verifier: Box<dyn AgentProvider>,
}

pub enum Input {
    Task(String),
    SpecFile(PathBuf),
}

pub struct Engine {
    project_root: PathBuf,
    recorder: FileRecorder,
    checkpoint: Checkpoint,
    config: Config,
    agents: RoleAgents,
}

impl Engine {
    pub fn new(
        project_root: PathBuf,
        run_dir: PathBuf,
        config: Config,
        agents: RoleAgents,
    ) -> Result<Self> {
        let checkpoint = Checkpoint::open(&run_dir.join("state.db"))?;
        let recorder = FileRecorder::new(run_dir);
        Ok(Self { project_root, recorder, checkpoint, config, agents })
    }

    pub fn run(&mut self, input: Input) -> Result<RunSummary> {
        let mut state = self.checkpoint.load()?.unwrap_or(RunState::Idle);
        let mut tasks: Vec<Task> = vec![];
        let mut completed_summaries: Vec<String> = vec![];

        loop {
            match state.clone() {
                RunState::Idle => {
                    match &input {
                        Input::SpecFile(path) => {
                            let spec = std::fs::read_to_string(path)?;
                            self.recorder.write("spec.md", &spec)?;
                            state = RunState::Orchestrating;
                        }
                        Input::Task(_) => {
                            state = RunState::Clarifying { turn: 0 };
                        }
                    }
                    self.checkpoint.save(&state)?;
                }

                RunState::Clarifying { turn } => {
                    let task_desc = match &input {
                        Input::Task(t) => t.clone(),
                        _ => unreachable!(),
                    };
                    let history = self.load_clarification_history(turn)?;
                    let ctx = ContextBuilder::new(self.project_root.clone());
                    let prompt = ctx.planner_prompt(&task_desc, &history);
                    self.recorder.write(
                        &format!("planner/turn_{:03}_prompt.md", turn),
                        &prompt,
                    )?;

                    let output = self.agents.planner.run(&prompt)?;
                    self.recorder.write(
                        &format!("planner/turn_{:03}_output.md", turn),
                        &output,
                    )?;

                    if let Some(spec) = extract_spec_block(&output) {
                        self.recorder.write("spec.md", &spec)?;
                        state = RunState::Orchestrating;
                        self.checkpoint.save(&state)?;
                    } else {
                        println!("{}", output);
                        print!("Your response: ");
                        let mut user_input = String::new();
                        std::io::stdin().read_line(&mut user_input)?;
                        self.recorder.write(
                            &format!("planner/turn_{:03}_user.md", turn),
                            user_input.trim(),
                        )?;

                        let next_turn = turn + 1;
                        if next_turn >= self.config.run.max_retries {
                            state = RunState::Failed {
                                reason: "Planner did not produce a spec within max turns".into(),
                            };
                        } else {
                            state = RunState::Clarifying { turn: next_turn };
                        }
                        self.checkpoint.save(&state)?;
                    }
                }

                RunState::Planning => {
                    state = RunState::Orchestrating;
                    self.checkpoint.save(&state)?;
                }

                RunState::Orchestrating => {
                    self.checkpoint.save(&state)?;
                    let spec = self.recorder.read("spec.md")?;
                    let ctx = ContextBuilder::new(self.project_root.clone());
                    let prompt = ctx.orchestrator_prompt(&spec)?;
                    self.recorder.write("orchestrator/prompt.md", &prompt)?;

                    let raw = self.run_with_retry(
                        &*self.agents.orchestrator,
                        &prompt,
                        "Orchestrator failed",
                    )?;
                    self.recorder.write("orchestrator/output.md", &raw)?;

                    tasks = parse_tasks_json(&raw, self.config.run.max_retries, &*self.agents.orchestrator)?;
                    let tasks_json = serde_json::to_string_pretty(&tasks)?;
                    self.recorder.write("orchestrator/tasks.json", &tasks_json)?;

                    state = RunState::Coding { task_idx: 0, attempt: 0 };
                    self.checkpoint.save(&state)?;
                }

                RunState::Coding { task_idx, attempt } => {
                    self.checkpoint.save(&state)?;
                    if tasks.is_empty() {
                        tasks = load_tasks(&self.recorder)?;
                    }
                    let task = tasks[task_idx as usize].clone();
                    let ctx = ContextBuilder::new(self.project_root.clone());
                    let failure_reason = if attempt > 0 {
                        self.recorder
                            .read(&format!("tasks/{:03}/verifier_result.json", task_idx))
                            .ok()
                            .and_then(|s| serde_json::from_str::<VerifierResult>(&s).ok())
                            .map(|v| v.reason)
                    } else {
                        None
                    };

                    let prompt = ctx.coder_prompt(
                        &task,
                        &completed_summaries,
                        failure_reason.as_deref(),
                    )?;
                    self.recorder.write(
                        &format!("tasks/{:03}/coder_prompt.md", task_idx),
                        &prompt,
                    )?;

                    let output = self.agents.coder.run(&prompt)?;
                    self.recorder.write(
                        &format!("tasks/{:03}/coder_output.md", task_idx),
                        &output,
                    )?;

                    state = RunState::Verifying { task_idx, attempt };
                    self.checkpoint.save(&state)?;
                }

                RunState::Verifying { task_idx, attempt } => {
                    self.checkpoint.save(&state)?;
                    if tasks.is_empty() {
                        tasks = load_tasks(&self.recorder)?;
                    }
                    let task = tasks[task_idx as usize].clone();
                    let spec = self.recorder.read("spec.md")?;
                    let diff = git_diff(&self.project_root);
                    let ctx = ContextBuilder::new(self.project_root.clone());
                    let prompt = ctx.verifier_prompt(&spec, &task, &diff);
                    self.recorder.write(
                        &format!("tasks/{:03}/verifier_prompt.md", task_idx),
                        &prompt,
                    )?;

                    let raw = self.agents.verifier.run(&prompt)?;
                    let result: VerifierResult = parse_verifier_result(&raw);
                    let result_json = serde_json::to_string_pretty(&result)?;
                    self.recorder.write(
                        &format!("tasks/{:03}/verifier_result.json", task_idx),
                        &result_json,
                    )?;

                    if result.passed {
                        completed_summaries.push(format!("Task {}: {}", task.id, task.title));
                        let next = task_idx + 1;
                        if next as usize >= tasks.len() {
                            state = RunState::Done;
                        } else {
                            state = RunState::Coding { task_idx: next, attempt: 0 };
                        }
                    } else if attempt + 1 < self.config.run.max_retries {
                        state = RunState::Coding { task_idx, attempt: attempt + 1 };
                    } else {
                        state = RunState::Failed {
                            reason: format!(
                                "Task {} ({}) failed after {} attempts: {}",
                                task.id,
                                task.title,
                                attempt + 1,
                                result.reason
                            ),
                        };
                    }
                    self.checkpoint.save(&state)?;
                }

                RunState::Done => {
                    let summary = RunSummary {
                        outcome: "done".into(),
                        completed_tasks: completed_summaries.clone(),
                        failed_task: None,
                        reason: None,
                    };
                    self.recorder
                        .write("run_summary.json", &serde_json::to_string_pretty(&summary)?)?;
                    return Ok(summary);
                }

                RunState::Failed { reason } => {
                    let failed_task = reason
                        .strip_prefix("Task ")
                        .and_then(|s| s.find(' ').map(|i| s[..i].to_string()));
                    let summary = RunSummary {
                        outcome: "failed".into(),
                        completed_tasks: completed_summaries.clone(),
                        failed_task,
                        reason: Some(reason.clone()),
                    };
                    self.recorder
                        .write("run_summary.json", &serde_json::to_string_pretty(&summary)?)?;
                    return Ok(summary);
                }
            }
        }
    }

    fn run_with_retry(
        &self,
        agent: &dyn AgentProvider,
        prompt: &str,
        ctx: &str,
    ) -> Result<String> {
        let mut last_err = anyhow::anyhow!("{} failed", ctx);
        for _ in 0..self.config.run.max_retries {
            match agent.run(prompt) {
                Ok(s) => return Ok(s),
                Err(e) => last_err = e,
            }
        }
        Err(last_err.context(ctx.to_string()))
    }

    fn load_clarification_history(&self, turn: u32) -> Result<Vec<(String, String)>> {
        let mut history = vec![];
        for i in 0..turn {
            let output =
                self.recorder.read(&format!("planner/turn_{:03}_output.md", i))?;
            let user =
                self.recorder.read(&format!("planner/turn_{:03}_user.md", i))?;
            history.push((output, user));
        }
        Ok(history)
    }
}

fn extract_spec_block(text: &str) -> Option<String> {
    let start = text.find("<spec>")?;
    let end = text.find("</spec>")?;
    if end <= start {
        return None;
    }
    Some(text[start + 6..end].trim().to_string())
}

fn parse_tasks_json(
    raw: &str,
    max_retries: u32,
    agent: &dyn AgentProvider,
) -> Result<Vec<Task>> {
    let json_str = extract_json_array(raw).unwrap_or(raw);
    if let Ok(tasks) = serde_json::from_str::<Vec<Task>>(json_str) {
        return Ok(tasks);
    }
    for _ in 0..max_retries {
        let correction = format!(
            "Your previous output was not valid JSON. Output ONLY a JSON array of tasks. Previous output:\n{}",
            raw
        );
        let retry = agent.run(&correction)?;
        let s = extract_json_array(&retry).unwrap_or(&retry);
        if let Ok(tasks) = serde_json::from_str::<Vec<Task>>(s) {
            return Ok(tasks);
        }
    }
    anyhow::bail!("Orchestrator failed to produce valid tasks.json after retries")
}

fn extract_json_array(text: &str) -> Option<&str> {
    let start = text.find('[')?;
    let end = text.rfind(']')?;
    if end < start {
        return None;
    }
    Some(&text[start..=end])
}

fn parse_verifier_result(raw: &str) -> VerifierResult {
    let s = extract_json_object(raw).unwrap_or(raw);
    serde_json::from_str(s).unwrap_or(VerifierResult {
        passed: false,
        reason: format!("Could not parse verifier output: {}", raw),
    })
}

fn extract_json_object(text: &str) -> Option<&str> {
    let start = text.find('{')?;
    let end = text.rfind('}')?;
    if end < start {
        return None;
    }
    Some(&text[start..=end])
}

fn load_tasks(recorder: &FileRecorder) -> Result<Vec<Task>> {
    let json = recorder.read("orchestrator/tasks.json")?;
    Ok(serde_json::from_str(&json)?)
}

fn git_diff(root: &std::path::Path) -> String {
    std::process::Command::new("git")
        .args(["diff", "HEAD"])
        .current_dir(root)
        .output()
        .ok()
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_spec_block() {
        let text = "Here is a spec:\n<spec>\n# My Spec\nBuild X\n</spec>\nEnd.";
        assert_eq!(extract_spec_block(text), Some("# My Spec\nBuild X".into()));
    }

    #[test]
    fn test_extract_spec_block_none() {
        assert_eq!(extract_spec_block("no spec here"), None);
    }

    #[test]
    fn test_extract_json_array() {
        let text = "Some text [1,2,3] more text";
        assert_eq!(extract_json_array(text), Some("[1,2,3]"));
    }

    #[test]
    fn test_parse_verifier_result_valid() {
        let raw = r#"{"passed": true, "reason": "all good"}"#;
        let v = parse_verifier_result(raw);
        assert!(v.passed);
    }

    #[test]
    fn test_parse_verifier_result_with_surrounding_text() {
        let raw = r#"Here is my analysis: {"passed": false, "reason": "missing tests"} done."#;
        let v = parse_verifier_result(raw);
        assert!(!v.passed);
        assert_eq!(v.reason, "missing tests");
    }

    #[test]
    fn test_parse_verifier_result_fallback_on_garbage() {
        let v = parse_verifier_result("not json at all");
        assert!(!v.passed);
        assert!(v.reason.contains("not json at all"));
    }
}
