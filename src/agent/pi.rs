use crate::agent::AgentProvider;

pub struct PiAgent { model: String }
impl PiAgent {
    pub fn new(model: String) -> Self { Self { model } }
}
impl AgentProvider for PiAgent {
    fn run(&self, _prompt: &str) -> anyhow::Result<String> {
        anyhow::bail!("PiAgent not yet implemented")
    }
    fn name(&self) -> &str { "pi" }
}
