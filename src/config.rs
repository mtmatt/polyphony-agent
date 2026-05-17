use serde::Deserialize;
use std::path::Path;

#[derive(Debug, Deserialize, Clone)]
pub struct Config {
    pub roles: RolesConfig,
    #[serde(default)]
    pub run: RunConfig,
}

#[derive(Debug, Deserialize, Clone)]
pub struct RolesConfig {
    pub planner: RoleConfig,
    pub orchestrator: RoleConfig,
    pub coder: RoleConfig,
    pub verifier: RoleConfig,
}

#[derive(Debug, Deserialize, Clone)]
pub struct RoleConfig {
    pub provider: String,
    pub model: String,
}

#[derive(Debug, Deserialize, Clone)]
pub struct RunConfig {
    pub max_retries: u32,
    pub runs_dir: String,
}

impl Default for RunConfig {
    fn default() -> Self {
        Self { max_retries: 3, runs_dir: "runs".to_string() }
    }
}

impl Config {
    pub fn load(path: &Path) -> anyhow::Result<Self> {
        let text = std::fs::read_to_string(path)?;
        Ok(toml::from_str(&text)?)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    #[test]
    fn test_load_config() {
        let mut f = tempfile::NamedTempFile::new().unwrap();
        write!(f, r#"
[roles]
planner      = {{ provider = "pi",     model = "openai/gpt-4o" }}
orchestrator = {{ provider = "claude", model = "claude-opus-4-7" }}
coder        = {{ provider = "codex",  model = "codex" }}
verifier     = {{ provider = "pi",     model = "anthropic/claude-sonnet-4-6" }}

[run]
max_retries = 3
runs_dir    = "runs"
"#).unwrap();

        let config = Config::load(f.path()).unwrap();
        assert_eq!(config.roles.planner.provider, "pi");
        assert_eq!(config.roles.planner.model, "openai/gpt-4o");
        assert_eq!(config.run.max_retries, 3);
    }

    #[test]
    fn test_default_run_config() {
        let mut f = tempfile::NamedTempFile::new().unwrap();
        write!(f, r#"
[roles]
planner      = {{ provider = "pi",     model = "openai/gpt-4o" }}
orchestrator = {{ provider = "claude", model = "claude-opus-4-7" }}
coder        = {{ provider = "codex",  model = "codex" }}
verifier     = {{ provider = "pi",     model = "anthropic/claude-sonnet-4-6" }}
"#).unwrap();

        let config = Config::load(f.path()).unwrap();
        assert_eq!(config.run.max_retries, 3);
        assert_eq!(config.run.runs_dir, "runs");
    }
}
