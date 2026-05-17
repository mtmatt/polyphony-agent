use crate::agent::AgentProvider;
use std::process::Command;

pub struct ClaudeCodeAgent {
    model: String,
}

impl ClaudeCodeAgent {
    pub fn new(model: String) -> Self {
        Self { model }
    }
}

impl AgentProvider for ClaudeCodeAgent {
    fn run(&self, prompt: &str) -> anyhow::Result<String> {
        let output = Command::new("claude")
            .args(["--model", &self.model, "-p", prompt])
            .output()?;
        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            anyhow::bail!("claude exited {}: {}", output.status, stderr);
        }
        Ok(String::from_utf8(output.stdout)?)
    }

    fn name(&self) -> &str {
        "claude"
    }
}
