use crate::agent::AgentProvider;
use std::path::PathBuf;
use std::process::Command;

pub struct CodexAgent {
    model: String,
    cwd: PathBuf,
}

impl CodexAgent {
    pub fn new(model: String, cwd: PathBuf) -> Self {
        Self { model, cwd }
    }
}

impl AgentProvider for CodexAgent {
    fn run(&self, prompt: &str) -> anyhow::Result<String> {
        let output = Command::new("codex")
            .args(["--model", &self.model, "--quiet", prompt])
            .current_dir(&self.cwd)
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
