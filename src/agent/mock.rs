use crate::agent::AgentProvider;
use std::sync::Mutex;

pub struct MockAgentProvider {
    name: String,
    responses: Mutex<Vec<String>>,
    calls: Mutex<Vec<String>>,
}

impl MockAgentProvider {
    pub fn new(name: &str, responses: Vec<String>) -> Self {
        Self {
            name: name.to_string(),
            responses: Mutex::new(responses),
            calls: Mutex::new(vec![]),
        }
    }

    pub fn calls(&self) -> Vec<String> {
        self.calls.lock().unwrap().clone()
    }
}

impl AgentProvider for MockAgentProvider {
    fn run(&self, prompt: &str) -> anyhow::Result<String> {
        self.calls.lock().unwrap().push(prompt.to_string());
        let mut responses = self.responses.lock().unwrap();
        if responses.is_empty() {
            anyhow::bail!("MockAgentProvider '{}': no more responses", self.name);
        }
        Ok(responses.remove(0))
    }

    fn name(&self) -> &str {
        &self.name
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_returns_responses_in_order() {
        let m = MockAgentProvider::new("test", vec!["first".into(), "second".into()]);
        assert_eq!(m.run("p1").unwrap(), "first");
        assert_eq!(m.run("p2").unwrap(), "second");
    }

    #[test]
    fn test_records_calls() {
        let m = MockAgentProvider::new("test", vec!["ok".into()]);
        m.run("hello prompt").unwrap();
        assert_eq!(m.calls(), vec!["hello prompt"]);
    }

    #[test]
    fn test_errors_when_exhausted() {
        let m = MockAgentProvider::new("test", vec![]);
        assert!(m.run("p").is_err());
    }
}
