# Polyphony Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Rust multi-agent orchestration system that coordinates Claude Code, Pi, and Codex across four roles (Planner, Orchestrator, Coder, Verifier) to execute coding tasks autonomously with checkpoint/resume support.

**Architecture:** Explicit state machine persisted to SQLite drives a sequential pipeline. Each agent role is a subprocess wrapped behind a common `AgentProvider` trait. Every prompt and output is written to a per-run file directory for auditability.

**Tech Stack:** Rust, tokio (subprocess), rusqlite (checkpoint), serde_json (tasks.json/events), clap (CLI), regex (symbol extraction), anyhow (errors)

---

## Task 1: Cargo project setup

**Files:**
- Create: `Cargo.toml`
- Create: `src/lib.rs`
- Create: `src/main.rs`

- [ ] **Step 1: Initialize Cargo project**

```bash
cargo init --name polyphony
```

- [ ] **Step 2: Replace Cargo.toml with full dependencies**

```toml
[package]
name = "polyphony"
version = "0.1.0"
edition = "2021"

[[bin]]
name = "polyphony"
path = "src/main.rs"

[lib]
path = "src/lib.rs"

[dependencies]
anyhow = "1"
chrono = { version = "0.4", features = ["serde"] }
clap = { version = "4", features = ["derive"] }
regex = "1"
rusqlite = { version = "0.31", features = ["bundled"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
toml = "0.8"

[dev-dependencies]
tempfile = "3"
```

- [ ] **Step 3: Write stub lib.rs**

```rust
pub mod agent;
pub mod config;
pub mod context;
pub mod engine;
pub mod recorder;
pub mod repo_map;
pub mod state;
pub mod types;
```

- [ ] **Step 4: Write stub main.rs**

```rust
fn main() -> anyhow::Result<()> {
    println!("polyphony");
    Ok(())
}
```

- [ ] **Step 5: Verify it compiles**

Run: `cargo build`
Expected: compiles with warnings about unused modules (stubs not written yet — that's fine, add `#![allow(dead_code)]` to lib.rs temporarily)

- [ ] **Step 6: Commit**

```bash
git add Cargo.toml src/lib.rs src/main.rs
git commit -m "chore: initialize Rust project with dependencies"
```

---

## Task 2: Config

**Files:**
- Create: `src/config.rs`
- Create: `polyphony.toml.example`

- [ ] **Step 1: Write failing test**

Create `src/config.rs`:

```rust
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
```

- [ ] **Step 2: Run test — expect fail (module not wired)**

Run: `cargo test config`
Expected: compile error (config module empty)

- [ ] **Step 3: Run test — expect pass**

Run: `cargo test config`
Expected: 2 tests pass

- [ ] **Step 4: Write polyphony.toml.example**

```toml
[roles]
planner      = { provider = "pi",     model = "openai/gpt-4o" }
orchestrator = { provider = "claude", model = "claude-opus-4-7" }
coder        = { provider = "codex",  model = "codex" }
verifier     = { provider = "pi",     model = "anthropic/claude-sonnet-4-6" }

[run]
max_retries = 3
runs_dir    = "runs"
```

- [ ] **Step 5: Commit**

```bash
git add src/config.rs polyphony.toml.example
git commit -m "feat: add Config struct and TOML parsing"
```

---

## Task 3: Shared types

**Files:**
- Create: `src/types.rs`

- [ ] **Step 1: Write types with tests**

```rust
use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Task {
    pub id: String,
    pub title: String,
    pub description: String,
    pub relevant_files: Vec<String>,
    pub depends_on: Vec<String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct VerifierResult {
    pub passed: bool,
    pub reason: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct RunSummary {
    pub outcome: String,
    pub completed_tasks: Vec<String>,
    pub failed_task: Option<String>,
    pub reason: Option<String>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_task_roundtrip() {
        let task = Task {
            id: "001".into(),
            title: "Add auth".into(),
            description: "Implement JWT middleware".into(),
            relevant_files: vec!["src/auth.rs".into()],
            depends_on: vec![],
        };
        let json = serde_json::to_string(&task).unwrap();
        let parsed: Task = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed.id, "001");
    }

    #[test]
    fn test_verifier_result_roundtrip() {
        let v = VerifierResult { passed: false, reason: "missing tests".into() };
        let json = serde_json::to_string(&v).unwrap();
        let parsed: VerifierResult = serde_json::from_str(&json).unwrap();
        assert!(!parsed.passed);
        assert_eq!(parsed.reason, "missing tests");
    }

    #[test]
    fn test_parse_tasks_array() {
        let json = r#"[
            {"id":"001","title":"T1","description":"D1","relevant_files":[],"depends_on":[]},
            {"id":"002","title":"T2","description":"D2","relevant_files":["src/"],"depends_on":["001"]}
        ]"#;
        let tasks: Vec<Task> = serde_json::from_str(json).unwrap();
        assert_eq!(tasks.len(), 2);
        assert_eq!(tasks[1].depends_on[0], "001");
    }
}
```

- [ ] **Step 2: Run and verify**

Run: `cargo test types`
Expected: 3 tests pass

- [ ] **Step 3: Commit**

```bash
git add src/types.rs
git commit -m "feat: add shared Task, VerifierResult, RunSummary types"
```

---

## Task 4: RunState + Checkpoint

**Files:**
- Create: `src/state.rs`

- [ ] **Step 1: Write state module with tests**

```rust
use anyhow::Result;
use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use std::path::Path;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "state", rename_all = "snake_case")]
pub enum RunState {
    Idle,
    Clarifying { turn: u32 },
    Planning,
    Orchestrating,
    Coding { task_idx: u32, attempt: u32 },
    Verifying { task_idx: u32, attempt: u32 },
    Done,
    Failed { reason: String },
}

pub struct Checkpoint {
    conn: Connection,
}

impl Checkpoint {
    pub fn open(path: &Path) -> Result<Self> {
        let conn = Connection::open(path)?;
        conn.execute_batch(
            "CREATE TABLE IF NOT EXISTS state \
             (id INTEGER PRIMARY KEY, value TEXT NOT NULL);",
        )?;
        Ok(Self { conn })
    }

    pub fn save(&self, state: &RunState) -> Result<()> {
        let value = serde_json::to_string(state)?;
        self.conn.execute(
            "INSERT OR REPLACE INTO state (id, value) VALUES (1, ?1)",
            rusqlite::params![value],
        )?;
        Ok(())
    }

    pub fn load(&self) -> Result<Option<RunState>> {
        match self.conn.query_row(
            "SELECT value FROM state WHERE id = 1",
            [],
            |row| row.get::<_, String>(0),
        ) {
            Ok(v) => Ok(Some(serde_json::from_str(&v)?)),
            Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
            Err(e) => Err(e.into()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn test_save_and_load() {
        let dir = tempdir().unwrap();
        let cp = Checkpoint::open(&dir.path().join("state.db")).unwrap();

        cp.save(&RunState::Idle).unwrap();
        assert_eq!(cp.load().unwrap(), Some(RunState::Idle));

        cp.save(&RunState::Coding { task_idx: 2, attempt: 1 }).unwrap();
        assert_eq!(
            cp.load().unwrap(),
            Some(RunState::Coding { task_idx: 2, attempt: 1 })
        );
    }

    #[test]
    fn test_load_empty_returns_none() {
        let dir = tempdir().unwrap();
        let cp = Checkpoint::open(&dir.path().join("state.db")).unwrap();
        assert_eq!(cp.load().unwrap(), None);
    }

    #[test]
    fn test_resume_same_file() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("state.db");

        {
            let cp = Checkpoint::open(&path).unwrap();
            cp.save(&RunState::Orchestrating).unwrap();
        }
        {
            let cp = Checkpoint::open(&path).unwrap();
            assert_eq!(cp.load().unwrap(), Some(RunState::Orchestrating));
        }
    }

    #[test]
    fn test_failed_state_roundtrip() {
        let dir = tempdir().unwrap();
        let cp = Checkpoint::open(&dir.path().join("state.db")).unwrap();
        let state = RunState::Failed { reason: "verifier gave up".into() };
        cp.save(&state).unwrap();
        assert_eq!(cp.load().unwrap(), Some(state));
    }
}
```

- [ ] **Step 2: Run and verify**

Run: `cargo test state`
Expected: 4 tests pass

- [ ] **Step 3: Commit**

```bash
git add src/state.rs
git commit -m "feat: add RunState enum and SQLite checkpoint"
```

---

## Task 5: FileRecorder

**Files:**
- Create: `src/recorder.rs`

- [ ] **Step 1: Write recorder with tests**

```rust
use anyhow::Result;
use std::path::PathBuf;

pub struct FileRecorder {
    run_dir: PathBuf,
}

impl FileRecorder {
    pub fn new(run_dir: PathBuf) -> Self {
        Self { run_dir }
    }

    pub fn write(&self, rel_path: &str, content: &str) -> Result<()> {
        let dest = self.run_dir.join(rel_path);
        if let Some(parent) = dest.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let tmp = dest.with_extension(
            dest.extension()
                .map(|e| format!("{}.tmp", e.to_string_lossy()))
                .unwrap_or_else(|| "tmp".into()),
        );
        std::fs::write(&tmp, content)?;
        std::fs::rename(&tmp, &dest)?;
        Ok(())
    }

    pub fn read(&self, rel_path: &str) -> Result<String> {
        Ok(std::fs::read_to_string(self.run_dir.join(rel_path))?)
    }

    pub fn exists(&self, rel_path: &str) -> bool {
        self.run_dir.join(rel_path).exists()
    }

    pub fn run_dir(&self) -> &PathBuf {
        &self.run_dir
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn test_write_and_read() {
        let dir = tempdir().unwrap();
        let rec = FileRecorder::new(dir.path().to_path_buf());
        rec.write("planner/output.md", "hello world").unwrap();
        assert_eq!(rec.read("planner/output.md").unwrap(), "hello world");
    }

    #[test]
    fn test_creates_subdirectories() {
        let dir = tempdir().unwrap();
        let rec = FileRecorder::new(dir.path().to_path_buf());
        rec.write("tasks/001/coder_output.md", "code here").unwrap();
        assert!(dir.path().join("tasks/001/coder_output.md").exists());
    }

    #[test]
    fn test_no_tmp_file_left_after_write() {
        let dir = tempdir().unwrap();
        let rec = FileRecorder::new(dir.path().to_path_buf());
        rec.write("spec.md", "content").unwrap();
        assert!(!dir.path().join("spec.md.tmp").exists());
        assert!(dir.path().join("spec.md").exists());
    }

    #[test]
    fn test_overwrite_is_atomic() {
        let dir = tempdir().unwrap();
        let rec = FileRecorder::new(dir.path().to_path_buf());
        rec.write("out.md", "v1").unwrap();
        rec.write("out.md", "v2").unwrap();
        assert_eq!(rec.read("out.md").unwrap(), "v2");
    }
}
```

- [ ] **Step 2: Run and verify**

Run: `cargo test recorder`
Expected: 4 tests pass

- [ ] **Step 3: Commit**

```bash
git add src/recorder.rs
git commit -m "feat: add FileRecorder with atomic writes"
```

---

## Task 6: AgentProvider trait + MockAgent

**Files:**
- Create: `src/agent/mod.rs`
- Create: `src/agent/mock.rs`

- [ ] **Step 1: Write agent mod.rs**

```rust
pub mod claude;
pub mod codex;
pub mod mock;
pub mod pi;

use crate::config::RoleConfig;

pub trait AgentProvider: Send + Sync {
    fn run(&self, prompt: &str) -> anyhow::Result<String>;
    fn name(&self) -> &str;
}

pub fn create_provider(cfg: &RoleConfig) -> anyhow::Result<Box<dyn AgentProvider>> {
    match cfg.provider.as_str() {
        "claude" => Ok(Box::new(claude::ClaudeCodeAgent::new(cfg.model.clone()))),
        "pi" => Ok(Box::new(pi::PiAgent::new(cfg.model.clone()))),
        "codex" => Ok(Box::new(codex::CodexAgent::new(cfg.model.clone()))),
        other => anyhow::bail!("Unknown provider: {}", other),
    }
}
```

- [ ] **Step 2: Write mock.rs with tests**

```rust
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
```

- [ ] **Step 3: Create stub files for other agents so it compiles**

Create `src/agent/claude.rs`:
```rust
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
```

Create `src/agent/pi.rs`:
```rust
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
```

Create `src/agent/codex.rs`:
```rust
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
```

- [ ] **Step 4: Run and verify**

Run: `cargo test agent`
Expected: 3 tests pass

- [ ] **Step 5: Commit**

```bash
git add src/agent/
git commit -m "feat: add AgentProvider trait, MockAgentProvider, and agent stubs"
```

---

## Task 7: ClaudeCodeAgent

**Files:**
- Modify: `src/agent/claude.rs`

- [ ] **Step 1: Implement ClaudeCodeAgent**

```rust
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
```

- [ ] **Step 2: Run cargo check**

Run: `cargo check`
Expected: compiles cleanly

- [ ] **Step 3: Commit**

```bash
git add src/agent/claude.rs
git commit -m "feat: implement ClaudeCodeAgent subprocess"
```

---

## Task 8: CodexAgent

**Files:**
- Modify: `src/agent/codex.rs`

- [ ] **Step 1: Implement CodexAgent**

```rust
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
```

- [ ] **Step 2: Commit**

```bash
git add src/agent/codex.rs
git commit -m "feat: implement CodexAgent subprocess"
```

---

## Task 9: PiAgent

**Files:**
- Modify: `src/agent/pi.rs`

Pi uses RPC mode over stdin/stdout JSONL. Protocol: send `{"id":"req-1","type":"prompt","message":"..."}`, wait for `agent_end` event, then send `{"id":"req-2","type":"get_last_assistant_text"}` and read the response.

- [ ] **Step 1: Implement PiAgent**

```rust
use crate::agent::AgentProvider;
use std::io::{BufRead, BufReader, Write};
use std::process::{Command, Stdio};
use std::sync::mpsc;

pub struct PiAgent {
    model: String,
}

impl PiAgent {
    pub fn new(model: String) -> Self {
        Self { model }
    }
}

impl AgentProvider for PiAgent {
    fn run(&self, prompt: &str) -> anyhow::Result<String> {
        let mut child = Command::new("pi")
            .args(["--mode", "rpc", "--no-session", "--model", &self.model])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()?;

        let mut stdin = child.stdin.take().unwrap();
        let stdout = child.stdout.take().unwrap();

        // Reader thread sends lines over channel
        let (tx, rx) = mpsc::channel::<String>();
        std::thread::spawn(move || {
            for line in BufReader::new(stdout).lines() {
                match line {
                    Ok(l) if !l.is_empty() => { let _ = tx.send(l); }
                    _ => break,
                }
            }
        });

        // Send prompt command
        writeln!(
            stdin,
            "{}",
            serde_json::to_string(&serde_json::json!({
                "id": "req-1", "type": "prompt", "message": prompt
            }))?
        )?;

        // Wait for agent_end event
        for line in &rx {
            if let Ok(ev) = serde_json::from_str::<serde_json::Value>(&line) {
                if ev["type"] == "agent_end" {
                    break;
                }
            }
        }

        // Request final assistant text
        writeln!(
            stdin,
            "{}",
            serde_json::to_string(&serde_json::json!({
                "id": "req-2", "type": "get_last_assistant_text"
            }))?
        )?;

        // Read until response for req-2
        let mut result = String::new();
        for line in &rx {
            if let Ok(msg) = serde_json::from_str::<serde_json::Value>(&line) {
                if msg["id"] == "req-2" && msg["type"] == "response" {
                    result = msg["data"]["text"]
                        .as_str()
                        .unwrap_or("")
                        .to_string();
                    break;
                }
            }
        }

        drop(stdin);
        child.wait()?;
        Ok(result)
    }

    fn name(&self) -> &str {
        "pi"
    }
}
```

- [ ] **Step 2: Cargo check**

Run: `cargo check`
Expected: compiles cleanly

- [ ] **Step 3: Commit**

```bash
git add src/agent/pi.rs
git commit -m "feat: implement PiAgent with RPC JSONL protocol"
```

---

## Task 10: RepoMap

**Files:**
- Create: `src/repo_map.rs`

- [ ] **Step 1: Write repo_map with tests**

```rust
use anyhow::Result;
use regex::Regex;
use std::path::Path;

const SKIP_DIRS: &[&str] = &[".git", "target", "node_modules", ".pi", "runs"];

pub fn build_repo_map(root: &Path) -> Result<String> {
    let mut out = String::new();
    walk(root, root, 0, &mut out)?;
    Ok(out)
}

fn walk(root: &Path, dir: &Path, depth: usize, out: &mut String) -> Result<()> {
    let mut entries: Vec<_> = std::fs::read_dir(dir)?.flatten().collect();
    entries.sort_by_key(|e| e.file_name());

    let indent = "  ".repeat(depth);
    for entry in entries {
        let path = entry.path();
        let name = entry.file_name().to_string_lossy().to_string();
        if path.is_dir() {
            if SKIP_DIRS.contains(&name.as_str()) {
                continue;
            }
            out.push_str(&format!("{}{}/\n", indent, name));
            walk(root, &path, depth + 1, out)?;
        } else {
            let size = std::fs::metadata(&path).map(|m| m.len()).unwrap_or(0);
            let syms = extract_symbols(&path);
            if syms.is_empty() {
                out.push_str(&format!("{}{} ({}B)\n", indent, name, size));
            } else {
                out.push_str(&format!("{}{} ({}B) [{}]\n", indent, name, size, syms.join(", ")));
            }
        }
    }
    Ok(())
}

fn extract_symbols(path: &Path) -> Vec<String> {
    let pattern = match path.extension().and_then(|e| e.to_str()) {
        Some("rs") => r"(?m)^pub (?:fn|struct|enum|trait)\s+(\w+)",
        Some("ts") | Some("js") => r"(?m)^(?:export )?(?:function|class|const)\s+(\w+)",
        Some("py") => r"(?m)^(?:def|class)\s+(\w+)",
        Some("go") => r"(?m)^func\s+(?:\(\w+ \*?\w+\) )?(\w+)",
        _ => return vec![],
    };
    let Ok(src) = std::fs::read_to_string(path) else { return vec![] };
    let re = Regex::new(pattern).unwrap();
    re.captures_iter(&src)
        .filter_map(|c| c.get(1).map(|m| m.as_str().to_string()))
        .take(10)
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::tempdir;

    #[test]
    fn test_repo_map_lists_files() {
        let dir = tempdir().unwrap();
        std::fs::write(dir.path().join("main.rs"), "fn main() {}").unwrap();
        let map = build_repo_map(dir.path()).unwrap();
        assert!(map.contains("main.rs"));
    }

    #[test]
    fn test_repo_map_skips_git() {
        let dir = tempdir().unwrap();
        std::fs::create_dir(dir.path().join(".git")).unwrap();
        std::fs::write(dir.path().join(".git/config"), "").unwrap();
        let map = build_repo_map(dir.path()).unwrap();
        assert!(!map.contains(".git"));
    }

    #[test]
    fn test_extract_rust_symbols() {
        let dir = tempdir().unwrap();
        let src = "pub fn run() {}\npub struct Config {}\npub enum State {}";
        let path = dir.path().join("lib.rs");
        std::fs::write(&path, src).unwrap();
        let syms = extract_symbols(&path);
        assert!(syms.contains(&"run".to_string()));
        assert!(syms.contains(&"Config".to_string()));
        assert!(syms.contains(&"State".to_string()));
    }

    #[test]
    fn test_symbols_appear_in_map() {
        let dir = tempdir().unwrap();
        std::fs::write(dir.path().join("engine.rs"), "pub fn run() {}").unwrap();
        let map = build_repo_map(dir.path()).unwrap();
        assert!(map.contains("run"));
    }
}
```

- [ ] **Step 2: Run and verify**

Run: `cargo test repo_map`
Expected: 4 tests pass

- [ ] **Step 3: Commit**

```bash
git add src/repo_map.rs
git commit -m "feat: add RepoMap with directory tree and symbol extraction"
```

---

## Task 11: ContextBuilder

**Files:**
- Create: `src/context.rs`

- [ ] **Step 1: Write context module with tests**

```rust
use crate::types::Task;
use anyhow::Result;
use std::path::{Path, PathBuf};

pub struct ContextBuilder {
    project_root: PathBuf,
}

impl ContextBuilder {
    pub fn new(project_root: PathBuf) -> Self {
        Self { project_root }
    }

    pub fn orchestrator_prompt(&self, spec: &str) -> Result<String> {
        let repo_map = crate::repo_map::build_repo_map(&self.project_root)?;
        Ok(format!(
            "You are a software orchestrator. Break the following spec into an ordered list of atomic tasks.\n\
             Output ONLY a JSON array matching this schema:\n\
             [{{\"id\":\"001\",\"title\":\"...\",\"description\":\"...\",\
             \"relevant_files\":[\"path/or/dir/\"],\"depends_on\":[]}}]\n\n\
             # Spec\n{spec}\n\n# Repository Map\n{repo_map}"
        ))
    }

    pub fn coder_prompt(
        &self,
        task: &Task,
        completed_summaries: &[String],
        failure_reason: Option<&str>,
    ) -> Result<String> {
        let repo_map = crate::repo_map::build_repo_map(&self.project_root)?;
        let relevant = self.read_relevant_files(&task.relevant_files)?;

        let mut prompt = format!(
            "You are a software engineer. Implement the following task.\n\n\
             # Task {}: {}\n{}\n\n\
             # Repository Map\n{}\n\n\
             # Relevant Files\n{}",
            task.id, task.title, task.description, repo_map, relevant
        );

        if !completed_summaries.is_empty() {
            prompt.push_str("\n\n# Previously Completed Tasks\n");
            for s in completed_summaries {
                prompt.push_str(&format!("- {s}\n"));
            }
        }

        if let Some(reason) = failure_reason {
            prompt.push_str(&format!(
                "\n\n# Previous Attempt Failed\nVerifier rejection reason:\n{reason}"
            ));
        }

        Ok(prompt)
    }

    pub fn verifier_prompt(&self, spec: &str, task: &Task, diff: &str) -> String {
        format!(
            "You are a strict verifier. Check whether the implementation matches the spec.\n\
             Output ONLY valid JSON: {{\"passed\": true/false, \"reason\": \"...\"}}\n\n\
             # Spec\n{spec}\n\n\
             # Task {}: {}\n{}\n\n\
             # Changes (git diff)\n```diff\n{diff}\n```",
            task.id, task.title, task.description
        )
    }

    pub fn planner_prompt(&self, task_description: &str, history: &[(String, String)]) -> String {
        let mut prompt = format!(
            "You are a planning assistant. Ask clarifying questions about the user's task.\n\
             When you have enough information, write a complete spec inside <spec>...</spec> tags.\n\n\
             # Task\n{task_description}\n"
        );
        if !history.is_empty() {
            prompt.push_str("\n# Previous Clarifications\n");
            for (q, a) in history {
                prompt.push_str(&format!("Q: {q}\nA: {a}\n\n"));
            }
        }
        prompt
    }

    fn read_relevant_files(&self, paths: &[String]) -> Result<String> {
        let mut out = String::new();
        for p in paths {
            let full = self.project_root.join(p);
            if full.is_file() {
                let content = std::fs::read_to_string(&full)?;
                out.push_str(&format!("## {p}\n```\n{content}\n```\n\n"));
            } else if full.is_dir() {
                for entry in std::fs::read_dir(&full)?.flatten() {
                    if entry.path().is_file() {
                        let content = std::fs::read_to_string(entry.path())?;
                        let rel = entry.path().to_string_lossy().to_string();
                        out.push_str(&format!("## {rel}\n```\n{content}\n```\n\n"));
                    }
                }
            }
        }
        Ok(out)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    fn make_task() -> Task {
        Task {
            id: "001".into(),
            title: "Add auth".into(),
            description: "Implement JWT".into(),
            relevant_files: vec![],
            depends_on: vec![],
        }
    }

    #[test]
    fn test_coder_prompt_contains_task_info() {
        let dir = tempdir().unwrap();
        let cb = ContextBuilder::new(dir.path().to_path_buf());
        let prompt = cb.coder_prompt(&make_task(), &[], None).unwrap();
        assert!(prompt.contains("Add auth"));
        assert!(prompt.contains("Implement JWT"));
    }

    #[test]
    fn test_coder_prompt_includes_failure_reason() {
        let dir = tempdir().unwrap();
        let cb = ContextBuilder::new(dir.path().to_path_buf());
        let prompt = cb.coder_prompt(&make_task(), &[], Some("tests missing")).unwrap();
        assert!(prompt.contains("tests missing"));
    }

    #[test]
    fn test_verifier_prompt_contains_diff() {
        let dir = tempdir().unwrap();
        let cb = ContextBuilder::new(dir.path().to_path_buf());
        let prompt = cb.verifier_prompt("# Spec", &make_task(), "+fn foo() {}");
        assert!(prompt.contains("+fn foo()"));
        assert!(prompt.contains("passed"));
    }

    #[test]
    fn test_planner_prompt_includes_history() {
        let dir = tempdir().unwrap();
        let cb = ContextBuilder::new(dir.path().to_path_buf());
        let history = vec![("What auth?".into(), "JWT".into())];
        let prompt = cb.planner_prompt("Add login", &history);
        assert!(prompt.contains("What auth?"));
        assert!(prompt.contains("JWT"));
    }

    #[test]
    fn test_reads_relevant_file() {
        let dir = tempdir().unwrap();
        std::fs::write(dir.path().join("auth.rs"), "pub fn verify() {}").unwrap();
        let task = Task {
            id: "001".into(),
            title: "T".into(),
            description: "D".into(),
            relevant_files: vec!["auth.rs".into()],
            depends_on: vec![],
        };
        let cb = ContextBuilder::new(dir.path().to_path_buf());
        let prompt = cb.coder_prompt(&task, &[], None).unwrap();
        assert!(prompt.contains("pub fn verify()"));
    }
}
```

- [ ] **Step 2: Run and verify**

Run: `cargo test context`
Expected: 5 tests pass

- [ ] **Step 3: Commit**

```bash
git add src/context.rs
git commit -m "feat: add ContextBuilder for prompt assembly"
```

---

## Task 12: Engine

**Files:**
- Create: `src/engine.rs`

- [ ] **Step 1: Write engine**

```rust
use crate::{
    agent::AgentProvider,
    config::Config,
    context::ContextBuilder,
    recorder::FileRecorder,
    state::{Checkpoint, RunState},
    types::{RunSummary, Task, VerifierResult},
};
use anyhow::Result;
use std::path::PathBuf;

pub struct RoleAgents {
    pub planner: Box<dyn AgentProvider>,
    pub orchestrator: Box<dyn AgentProvider>,
    pub coder: Box<dyn AgentProvider>,
    pub verifier: Box<dyn AgentProvider>,
}

pub enum Input {
    Task(String),
    SpecFile(PathBuf),
}

pub struct Engine {
    project_root: PathBuf,
    recorder: FileRecorder,
    checkpoint: Checkpoint,
    config: Config,
    agents: RoleAgents,
}

impl Engine {
    pub fn new(
        project_root: PathBuf,
        run_dir: PathBuf,
        config: Config,
        agents: RoleAgents,
    ) -> Result<Self> {
        let checkpoint = Checkpoint::open(&run_dir.join("state.db"))?;
        let recorder = FileRecorder::new(run_dir);
        Ok(Self { project_root, recorder, checkpoint, config, agents })
    }

    pub fn run(&mut self, input: Input) -> Result<RunSummary> {
        let mut state = self.checkpoint.load()?.unwrap_or(RunState::Idle);
        let mut tasks: Vec<Task> = vec![];
        let mut completed_summaries: Vec<String> = vec![];

        loop {
            match state.clone() {
                RunState::Idle => {
                    match &input {
                        Input::SpecFile(path) => {
                            let spec = std::fs::read_to_string(path)?;
                            self.recorder.write("spec.md", &spec)?;
                            state = RunState::Orchestrating;
                        }
                        Input::Task(_) => {
                            state = RunState::Clarifying { turn: 0 };
                        }
                    }
                    self.checkpoint.save(&state)?;
                }

                RunState::Clarifying { turn } => {
                    let task_desc = match &input {
                        Input::Task(t) => t.clone(),
                        _ => unreachable!(),
                    };
                    let history = self.load_clarification_history(turn)?;
                    let ctx = ContextBuilder::new(self.project_root.clone());
                    let prompt = ctx.planner_prompt(&task_desc, &history);
                    self.recorder.write(
                        &format!("planner/turn_{:03}_prompt.md", turn),
                        &prompt,
                    )?;

                    let output = self.agents.planner.run(&prompt)?;
                    self.recorder.write(
                        &format!("planner/turn_{:03}_output.md", turn),
                        &output,
                    )?;

                    if let Some(spec) = extract_spec_block(&output) {
                        self.recorder.write("spec.md", &spec)?;
                        state = RunState::Orchestrating;
                        self.checkpoint.save(&state)?;
                    } else {
                        // Show output to user and get response
                        println!("{}", output);
                        print!("Your response: ");
                        let mut user_input = String::new();
                        std::io::stdin().read_line(&mut user_input)?;
                        self.recorder.write(
                            &format!("planner/turn_{:03}_user.md", turn),
                            user_input.trim(),
                        )?;

                        let next_turn = turn + 1;
                        if next_turn >= self.config.run.max_retries {
                            state = RunState::Failed {
                                reason: "Planner did not produce a spec within max turns".into(),
                            };
                        } else {
                            state = RunState::Clarifying { turn: next_turn };
                        }
                        self.checkpoint.save(&state)?;
                    }
                }

                RunState::Planning => {
                    // Planning is handled inline in Clarifying; skip to Orchestrating
                    state = RunState::Orchestrating;
                    self.checkpoint.save(&state)?;
                }

                RunState::Orchestrating => {
                    let spec = self.recorder.read("spec.md")?;
                    let ctx = ContextBuilder::new(self.project_root.clone());
                    let prompt = ctx.orchestrator_prompt(&spec)?;
                    self.recorder.write("orchestrator/prompt.md", &prompt)?;

                    let raw = self.run_with_retry(
                        &*self.agents.orchestrator,
                        &prompt,
                        "Orchestrator failed",
                    )?;
                    self.recorder.write("orchestrator/output.md", &raw)?;

                    tasks = parse_tasks_json(&raw, self.config.run.max_retries, &self.agents.orchestrator)?;
                    let tasks_json = serde_json::to_string_pretty(&tasks)?;
                    self.recorder.write("orchestrator/tasks.json", &tasks_json)?;

                    state = RunState::Coding { task_idx: 0, attempt: 0 };
                    self.checkpoint.save(&state)?;
                }

                RunState::Coding { task_idx, attempt } => {
                    if tasks.is_empty() {
                        tasks = load_tasks(&self.recorder)?;
                    }
                    let task = &tasks[task_idx as usize];
                    let ctx = ContextBuilder::new(self.project_root.clone());
                    let failure_reason = if attempt > 0 {
                        self.recorder
                            .read(&format!("tasks/{:03}/verifier_result.json", task_idx))
                            .ok()
                            .and_then(|s| serde_json::from_str::<VerifierResult>(&s).ok())
                            .map(|v| v.reason)
                    } else {
                        None
                    };

                    let prompt = ctx.coder_prompt(
                        task,
                        &completed_summaries,
                        failure_reason.as_deref(),
                    )?;
                    self.recorder.write(
                        &format!("tasks/{:03}/coder_prompt.md", task_idx),
                        &prompt,
                    )?;

                    let output = self.agents.coder.run(&prompt)?;
                    self.recorder.write(
                        &format!("tasks/{:03}/coder_output.md", task_idx),
                        &output,
                    )?;

                    state = RunState::Verifying { task_idx, attempt };
                    self.checkpoint.save(&state)?;
                }

                RunState::Verifying { task_idx, attempt } => {
                    if tasks.is_empty() {
                        tasks = load_tasks(&self.recorder)?;
                    }
                    let task = &tasks[task_idx as usize];
                    let spec = self.recorder.read("spec.md")?;
                    let diff = git_diff(&self.project_root);
                    let ctx = ContextBuilder::new(self.project_root.clone());
                    let prompt = ctx.verifier_prompt(&spec, task, &diff);
                    self.recorder.write(
                        &format!("tasks/{:03}/verifier_prompt.md", task_idx),
                        &prompt,
                    )?;

                    let raw = self.agents.verifier.run(&prompt)?;
                    let result: VerifierResult = parse_verifier_result(&raw);
                    let result_json = serde_json::to_string_pretty(&result)?;
                    self.recorder.write(
                        &format!("tasks/{:03}/verifier_result.json", task_idx),
                        &result_json,
                    )?;

                    if result.passed {
                        completed_summaries.push(format!("Task {}: {}", task.id, task.title));
                        let next = task_idx + 1;
                        if next as usize >= tasks.len() {
                            state = RunState::Done;
                        } else {
                            state = RunState::Coding { task_idx: next, attempt: 0 };
                        }
                    } else if attempt + 1 < self.config.run.max_retries {
                        state = RunState::Coding { task_idx, attempt: attempt + 1 };
                    } else {
                        state = RunState::Failed {
                            reason: format!("Task {} failed after {} attempts: {}", task.id, attempt + 1, result.reason),
                        };
                    }
                    self.checkpoint.save(&state)?;
                }

                RunState::Done => {
                    let summary = RunSummary {
                        outcome: "done".into(),
                        completed_tasks: completed_summaries.clone(),
                        failed_task: None,
                        reason: None,
                    };
                    self.recorder.write("run_summary.json", &serde_json::to_string_pretty(&summary)?)?;
                    return Ok(summary);
                }

                RunState::Failed { reason } => {
                    let summary = RunSummary {
                        outcome: "failed".into(),
                        completed_tasks: completed_summaries.clone(),
                        failed_task: None,
                        reason: Some(reason.clone()),
                    };
                    self.recorder.write("run_summary.json", &serde_json::to_string_pretty(&summary)?)?;
                    return Ok(summary);
                }
            }
        }
    }

    fn run_with_retry(&self, agent: &dyn AgentProvider, prompt: &str, ctx: &str) -> Result<String> {
        let mut last_err = None;
        for _ in 0..self.config.run.max_retries {
            match agent.run(prompt) {
                Ok(s) => return Ok(s),
                Err(e) => last_err = Some(e),
            }
        }
        Err(last_err.unwrap().context(ctx.to_string()))
    }

    fn load_clarification_history(&self, turn: u32) -> Result<Vec<(String, String)>> {
        let mut history = vec![];
        for i in 0..turn {
            let output = self.recorder.read(&format!("planner/turn_{:03}_output.md", i))?;
            let user = self.recorder.read(&format!("planner/turn_{:03}_user.md", i))?;
            history.push((output, user));
        }
        Ok(history)
    }
}

fn extract_spec_block(text: &str) -> Option<String> {
    let start = text.find("<spec>")?;
    let end = text.find("</spec>")?;
    if end <= start { return None; }
    Some(text[start + 6..end].trim().to_string())
}

fn parse_tasks_json(
    raw: &str,
    max_retries: u32,
    agent: &dyn AgentProvider,
) -> Result<Vec<Task>> {
    let json_str = extract_json_array(raw).unwrap_or(raw);
    if let Ok(tasks) = serde_json::from_str::<Vec<Task>>(json_str) {
        return Ok(tasks);
    }
    // Retry with error correction
    for _ in 0..max_retries {
        let correction = format!(
            "Your previous output was not valid JSON. Output ONLY a JSON array of tasks. Previous output:\n{}",
            raw
        );
        let retry = agent.run(&correction)?;
        let s = extract_json_array(&retry).unwrap_or(&retry);
        if let Ok(tasks) = serde_json::from_str::<Vec<Task>>(s) {
            return Ok(tasks);
        }
    }
    anyhow::bail!("Orchestrator failed to produce valid tasks.json after retries")
}

fn extract_json_array(text: &str) -> Option<&str> {
    let start = text.find('[')?;
    let end = text.rfind(']')?;
    if end < start { return None; }
    Some(&text[start..=end])
}

fn parse_verifier_result(raw: &str) -> VerifierResult {
    let s = extract_json_object(raw).unwrap_or(raw);
    serde_json::from_str(s).unwrap_or(VerifierResult {
        passed: false,
        reason: format!("Could not parse verifier output: {}", raw),
    })
}

fn extract_json_object(text: &str) -> Option<&str> {
    let start = text.find('{')?;
    let end = text.rfind('}')?;
    if end < start { return None; }
    Some(&text[start..=end])
}

fn load_tasks(recorder: &FileRecorder) -> Result<Vec<Task>> {
    let json = recorder.read("orchestrator/tasks.json")?;
    Ok(serde_json::from_str(&json)?)
}

fn git_diff(root: &std::path::Path) -> String {
    std::process::Command::new("git")
        .args(["diff", "HEAD"])
        .current_dir(root)
        .output()
        .ok()
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_spec_block() {
        let text = "Here is a spec:\n<spec>\n# My Spec\nBuild X\n</spec>\nEnd.";
        assert_eq!(extract_spec_block(text), Some("# My Spec\nBuild X".into()));
    }

    #[test]
    fn test_extract_spec_block_none() {
        assert_eq!(extract_spec_block("no spec here"), None);
    }

    #[test]
    fn test_extract_json_array() {
        let text = "Some text [1,2,3] more text";
        assert_eq!(extract_json_array(text), Some("[1,2,3]"));
    }

    #[test]
    fn test_parse_verifier_result_valid() {
        let raw = r#"{"passed": true, "reason": "all good"}"#;
        let v = parse_verifier_result(raw);
        assert!(v.passed);
    }

    #[test]
    fn test_parse_verifier_result_with_surrounding_text() {
        let raw = r#"Here is my analysis: {"passed": false, "reason": "missing tests"} done."#;
        let v = parse_verifier_result(raw);
        assert!(!v.passed);
        assert_eq!(v.reason, "missing tests");
    }

    #[test]
    fn test_parse_verifier_result_fallback_on_garbage() {
        let v = parse_verifier_result("not json at all");
        assert!(!v.passed);
        assert!(v.reason.contains("not json at all"));
    }
}
```

- [ ] **Step 2: Run unit tests**

Run: `cargo test engine`
Expected: 6 tests pass

- [ ] **Step 3: Commit**

```bash
git add src/engine.rs
git commit -m "feat: implement Engine orchestration loop"
```

---

## Task 13: CLI

**Files:**
- Modify: `src/main.rs`

- [ ] **Step 1: Write main.rs**

```rust
use clap::Parser;
use polyphony::{
    agent::{create_provider, mock::MockAgentProvider},
    config::Config,
    engine::{Engine, Input, RoleAgents},
};
use std::path::PathBuf;

#[derive(Parser)]
#[command(name = "polyphony", about = "Multi-agent code orchestration")]
struct Cli {
    /// Natural language task description
    task: Option<String>,

    /// Path to spec file — skips the Planner
    #[arg(long)]
    spec: Option<PathBuf>,

    /// Path to polyphony.toml
    #[arg(long, default_value = "polyphony.toml")]
    config: PathBuf,

    /// Resume an existing run directory
    #[arg(long)]
    resume: Option<PathBuf>,
}

fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    let cfg = Config::load(&cli.config)?;

    let agents = RoleAgents {
        planner: create_provider(&cfg.roles.planner)?,
        orchestrator: create_provider(&cfg.roles.orchestrator)?,
        coder: create_provider(&cfg.roles.coder)?,
        verifier: create_provider(&cfg.roles.verifier)?,
    };

    let run_dir = match &cli.resume {
        Some(dir) => dir.clone(),
        None => {
            let ts = chrono::Local::now().format("%Y-%m-%dT%H-%M-%S");
            let slug = cli
                .task
                .as_deref()
                .or_else(|| cli.spec.as_ref().and_then(|p| p.file_stem()?.to_str()))
                .unwrap_or("run")
                .split_whitespace()
                .take(4)
                .collect::<Vec<_>>()
                .join("-")
                .to_lowercase();
            let dir = PathBuf::from(&cfg.run.runs_dir).join(format!("{}-{}", ts, slug));
            std::fs::create_dir_all(&dir)?;
            dir
        }
    };

    let project_root = std::env::current_dir()?;

    let mut engine = Engine::new(project_root, run_dir.clone(), cfg, agents)?;

    let input = if let Some(spec_path) = cli.spec {
        Input::SpecFile(spec_path)
    } else if let Some(task) = cli.task {
        Input::Task(task)
    } else {
        anyhow::bail!("Provide a task description or --spec <file>");
    };

    let summary = engine.run(input)?;
    println!("\nRun complete: {}", summary.outcome);
    if let Some(reason) = summary.reason {
        println!("Reason: {}", reason);
    }
    println!("Run directory: {}", run_dir.display());

    Ok(())
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cargo build`
Expected: binary builds cleanly

- [ ] **Step 3: Smoke test help**

Run: `./target/debug/polyphony --help`
Expected: shows usage with `task`, `--spec`, `--config`, `--resume` options

- [ ] **Step 4: Commit**

```bash
git add src/main.rs
git commit -m "feat: add CLI with clap (task, --spec, --config, --resume)"
```

---

## Task 14: Integration test

**Files:**
- Create: `tests/integration_test.rs`

- [ ] **Step 1: Write integration test**

```rust
use polyphony::{
    agent::mock::MockAgentProvider,
    config::{Config, RoleConfig, RolesConfig, RunConfig},
    engine::{Engine, Input, RoleAgents},
};
use std::io::Write;
use tempfile::tempdir;

fn make_config() -> Config {
    Config {
        roles: RolesConfig {
            planner: RoleConfig { provider: "mock".into(), model: "mock".into() },
            orchestrator: RoleConfig { provider: "mock".into(), model: "mock".into() },
            coder: RoleConfig { provider: "mock".into(), model: "mock".into() },
            verifier: RoleConfig { provider: "mock".into(), model: "mock".into() },
        },
        run: RunConfig { max_retries: 3, runs_dir: "runs".into() },
    }
}

#[test]
fn test_spec_file_happy_path() {
    let project_dir = tempdir().unwrap();
    let run_dir = tempdir().unwrap();

    // Spec file
    let spec_path = project_dir.path().join("spec.md");
    std::fs::write(&spec_path, "# Spec\nAdd a hello function.").unwrap();

    let tasks_json = r#"[{"id":"001","title":"Add hello","description":"Add fn hello()","relevant_files":[],"depends_on":[]}]"#;

    let agents = RoleAgents {
        planner: Box::new(MockAgentProvider::new("planner", vec![])),
        orchestrator: Box::new(MockAgentProvider::new(
            "orchestrator",
            vec![tasks_json.to_string()],
        )),
        coder: Box::new(MockAgentProvider::new("coder", vec!["fn hello() {}".to_string()])),
        verifier: Box::new(MockAgentProvider::new(
            "verifier",
            vec![r#"{"passed": true, "reason": "looks good"}"#.to_string()],
        )),
    };

    let mut engine = Engine::new(
        project_dir.path().to_path_buf(),
        run_dir.path().to_path_buf(),
        make_config(),
        agents,
    )
    .unwrap();

    let summary = engine.run(Input::SpecFile(spec_path)).unwrap();
    assert_eq!(summary.outcome, "done");
    assert_eq!(summary.completed_tasks.len(), 1);
    assert!(summary.completed_tasks[0].contains("Add hello"));
}

#[test]
fn test_verifier_retry_then_pass() {
    let project_dir = tempdir().unwrap();
    let run_dir = tempdir().unwrap();
    let spec_path = project_dir.path().join("spec.md");
    std::fs::write(&spec_path, "# Spec\nAdd tests.").unwrap();

    let tasks_json = r#"[{"id":"001","title":"Add tests","description":"Write unit tests","relevant_files":[],"depends_on":[]}]"#;

    let agents = RoleAgents {
        planner: Box::new(MockAgentProvider::new("planner", vec![])),
        orchestrator: Box::new(MockAgentProvider::new("orchestrator", vec![tasks_json.to_string()])),
        coder: Box::new(MockAgentProvider::new(
            "coder",
            vec!["attempt 1".to_string(), "attempt 2".to_string()],
        )),
        verifier: Box::new(MockAgentProvider::new(
            "verifier",
            vec![
                r#"{"passed": false, "reason": "no assertions"}"#.to_string(),
                r#"{"passed": true, "reason": "assertions added"}"#.to_string(),
            ],
        )),
    };

    let mut engine = Engine::new(
        project_dir.path().to_path_buf(),
        run_dir.path().to_path_buf(),
        make_config(),
        agents,
    )
    .unwrap();

    let summary = engine.run(Input::SpecFile(spec_path)).unwrap();
    assert_eq!(summary.outcome, "done");
}

#[test]
fn test_verifier_exhausts_retries() {
    let project_dir = tempdir().unwrap();
    let run_dir = tempdir().unwrap();
    let spec_path = project_dir.path().join("spec.md");
    std::fs::write(&spec_path, "# Spec\nAdd feature X.").unwrap();

    let tasks_json = r#"[{"id":"001","title":"Feature X","description":"Do X","relevant_files":[],"depends_on":[]}]"#;

    let agents = RoleAgents {
        planner: Box::new(MockAgentProvider::new("planner", vec![])),
        orchestrator: Box::new(MockAgentProvider::new("orchestrator", vec![tasks_json.to_string()])),
        coder: Box::new(MockAgentProvider::new(
            "coder",
            vec!["a".to_string(), "b".to_string(), "c".to_string()],
        )),
        verifier: Box::new(MockAgentProvider::new(
            "verifier",
            vec![
                r#"{"passed": false, "reason": "wrong"}"#.to_string(),
                r#"{"passed": false, "reason": "still wrong"}"#.to_string(),
                r#"{"passed": false, "reason": "still wrong"}"#.to_string(),
            ],
        )),
    };

    let mut engine = Engine::new(
        project_dir.path().to_path_buf(),
        run_dir.path().to_path_buf(),
        make_config(),
        agents,
    )
    .unwrap();

    let summary = engine.run(Input::SpecFile(spec_path)).unwrap();
    assert_eq!(summary.outcome, "failed");
    assert!(summary.reason.unwrap().contains("Feature X"));
}

#[test]
fn test_resume_skips_done_tasks() {
    let project_dir = tempdir().unwrap();
    let run_dir = tempdir().unwrap();

    // Pre-populate run dir as if task 0 is done and we're at Coding{1,0}
    let spec_path = project_dir.path().join("spec.md");
    std::fs::write(&spec_path, "# Spec").unwrap();
    std::fs::copy(&spec_path, run_dir.path().join("spec.md")).unwrap();

    let tasks_json = r#"[
        {"id":"001","title":"T1","description":"D1","relevant_files":[],"depends_on":[]},
        {"id":"002","title":"T2","description":"D2","relevant_files":[],"depends_on":[]}
    ]"#;
    std::fs::create_dir_all(run_dir.path().join("orchestrator")).unwrap();
    std::fs::write(run_dir.path().join("orchestrator/tasks.json"), tasks_json).unwrap();

    // Set checkpoint to Coding{task_idx:1, attempt:0}
    {
        let cp = polyphony::state::Checkpoint::open(&run_dir.path().join("state.db")).unwrap();
        cp.save(&polyphony::state::RunState::Coding { task_idx: 1, attempt: 0 }).unwrap();
    }

    let agents = RoleAgents {
        planner: Box::new(MockAgentProvider::new("planner", vec![])),
        orchestrator: Box::new(MockAgentProvider::new("orchestrator", vec![])),
        coder: Box::new(MockAgentProvider::new("coder", vec!["impl T2".to_string()])),
        verifier: Box::new(MockAgentProvider::new(
            "verifier",
            vec![r#"{"passed": true, "reason": "ok"}"#.to_string()],
        )),
    };

    let mut engine = Engine::new(
        project_dir.path().to_path_buf(),
        run_dir.path().to_path_buf(),
        make_config(),
        agents,
    )
    .unwrap();

    let summary = engine.run(Input::SpecFile(spec_path)).unwrap();
    assert_eq!(summary.outcome, "done");
}
```

- [ ] **Step 2: Run integration tests**

Run: `cargo test --test integration_test`
Expected: 4 tests pass

- [ ] **Step 3: Run all tests**

Run: `cargo test`
Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/integration_test.rs
git commit -m "test: add integration tests for full pipeline and resume"
```

---

## Self-Review Notes

**Spec coverage check:**
- ✅ Natural language input → Clarifying loop
- ✅ Spec file input → skips Planner
- ✅ Planner `<spec>` termination condition
- ✅ Orchestrator produces tasks.json
- ✅ ContextBuilder injects repo map + relevant files + history + failure reason
- ✅ Sequential Coding → Verifying loop
- ✅ Fixed N retries → Failed state
- ✅ SQLite checkpoint before every agent call
- ✅ FileRecorder atomic writes
- ✅ run_summary.json on Done and Failed
- ✅ All three agents: ClaudeCodeAgent, PiAgent, CodexAgent
- ✅ Config-driven role → provider mapping
- ✅ Resume via `--resume` flag
- ✅ MockAgentProvider for tests

**Pi model format:** The config model field for Pi uses Pi's `provider/model` syntax (e.g. `openai/gpt-4o`, `anthropic/claude-sonnet-4-6`). This is passed directly as `--model` to `pi --mode rpc`.
