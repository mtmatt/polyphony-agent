use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Task {
    pub id: String,
    pub title: String,
    pub description: String,
    pub relevant_files: Vec<String>,
    pub depends_on: Vec<String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct VerifierResult {
    pub passed: bool,
    pub reason: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct RunSummary {
    pub outcome: String,
    pub completed_tasks: Vec<String>,
    pub failed_task: Option<String>,
    pub reason: Option<String>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_task_roundtrip() {
        let task = Task {
            id: "001".into(),
            title: "Add auth".into(),
            description: "Implement JWT middleware".into(),
            relevant_files: vec!["src/auth.rs".into()],
            depends_on: vec![],
        };
        let json = serde_json::to_string(&task).unwrap();
        let parsed: Task = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed.id, "001");
    }

    #[test]
    fn test_verifier_result_roundtrip() {
        let v = VerifierResult { passed: false, reason: "missing tests".into() };
        let json = serde_json::to_string(&v).unwrap();
        let parsed: VerifierResult = serde_json::from_str(&json).unwrap();
        assert!(!parsed.passed);
        assert_eq!(parsed.reason, "missing tests");
    }

    #[test]
    fn test_parse_tasks_array() {
        let json = r#"[
            {"id":"001","title":"T1","description":"D1","relevant_files":[],"depends_on":[]},
            {"id":"002","title":"T2","description":"D2","relevant_files":["src/"],"depends_on":["001"]}
        ]"#;
        let tasks: Vec<Task> = serde_json::from_str(json).unwrap();
        assert_eq!(tasks.len(), 2);
        assert_eq!(tasks[1].depends_on[0], "001");
    }
}
