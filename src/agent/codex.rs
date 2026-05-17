use crate::agent::AgentProvider;
use std::process::Command;

pub struct CodexAgent {
    model: String,
}

impl CodexAgent {
    pub fn new(model: String) -> Self {
        Self { model }
    }
}

impl AgentProvider for CodexAgent {
    fn run(&self, prompt: &str) -> anyhow::Result<String> {
        let output = Command::new("codex")
            .args(["--model", &self.model, "--quiet", prompt])
            .output()?;
        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            anyhow::bail!("codex exited {}: {}", output.status, stderr);
        }
        Ok(String::from_utf8(output.stdout)?)
    }

    fn name(&self) -> &str {
        "codex"
    }
}
