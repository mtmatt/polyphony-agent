pub mod claude;
pub mod codex;
pub mod mock;
pub mod pi;

use crate::config::RoleConfig;
use std::path::Path;

pub trait AgentProvider: Send + Sync {
    fn run(&self, prompt: &str) -> anyhow::Result<String>;
    fn name(&self) -> &str;
}

pub fn create_provider(cfg: &RoleConfig, cwd: &Path) -> anyhow::Result<Box<dyn AgentProvider>> {
    match cfg.provider.as_str() {
        "claude" => Ok(Box::new(claude::ClaudeCodeAgent::new(cfg.model.clone(), cwd.to_path_buf()))),
        "pi" => Ok(Box::new(pi::PiAgent::new(cfg.model.clone(), cwd.to_path_buf()))),
        "codex" => Ok(Box::new(codex::CodexAgent::new(cfg.model.clone(), cwd.to_path_buf()))),
        other => anyhow::bail!("Unknown provider: {}", other),
    }
}
