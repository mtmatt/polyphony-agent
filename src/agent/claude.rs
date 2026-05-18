use crate::agent::AgentProvider;
use std::path::PathBuf;
use std::process::Command;

pub struct ClaudeCodeAgent {
    model: String,
    cwd: PathBuf,
}

impl ClaudeCodeAgent {
    pub fn new(model: String, cwd: PathBuf) -> Self {
        Self { model, cwd }
    }
}

impl AgentProvider for ClaudeCodeAgent {
    fn run(&self, prompt: &str) -> anyhow::Result<String> {
        let output = Command::new("claude")
            .args([
                "--model", &self.model,
                "--dangerously-skip-permissions",
                "-p", prompt,
            ])
            .current_dir(&self.cwd)
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
