use crate::agent::AgentProvider;

pub struct ClaudeCodeAgent { model: String }
impl ClaudeCodeAgent {
    pub fn new(model: String) -> Self { Self { model } }
}
impl AgentProvider for ClaudeCodeAgent {
    fn run(&self, _prompt: &str) -> anyhow::Result<String> {
        anyhow::bail!("ClaudeCodeAgent not yet implemented")
    }
    fn name(&self) -> &str { "claude" }
}
