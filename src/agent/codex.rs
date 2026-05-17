use crate::agent::AgentProvider;

pub struct CodexAgent { model: String }
impl CodexAgent {
    pub fn new(model: String) -> Self { Self { model } }
}
impl AgentProvider for CodexAgent {
    fn run(&self, _prompt: &str) -> anyhow::Result<String> {
        anyhow::bail!("CodexAgent not yet implemented")
    }
    fn name(&self) -> &str { "codex" }
}
