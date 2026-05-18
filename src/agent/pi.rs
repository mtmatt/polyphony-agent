use crate::agent::AgentProvider;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::mpsc;

pub struct PiAgent {
    model: String,
    cwd: PathBuf,
}

impl PiAgent {
    pub fn new(model: String, cwd: PathBuf) -> Self {
        Self { model, cwd }
    }
}

impl AgentProvider for PiAgent {
    fn run(&self, prompt: &str) -> anyhow::Result<String> {
        let mut child = Command::new("pi")
            .args(["--mode", "rpc", "--no-session", "--model", &self.model])
            .current_dir(&self.cwd)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()?;

        let mut stdin = child.stdin.take().ok_or_else(|| anyhow::anyhow!("failed to get stdin"))?;
        let stdout = child.stdout.take().ok_or_else(|| anyhow::anyhow!("failed to get stdout"))?;

        // Reader thread sends lines over channel
        let (tx, rx) = mpsc::channel::<String>();
        std::thread::spawn(move || {
            for line in BufReader::new(stdout).lines() {
                match line {
                    Ok(l) if !l.is_empty() => {
                        if tx.send(l).is_err() {
                            break;
                        }
                    }
                    _ => {}
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

        // Wait for agent_end event; bail on error responses
        for line in &rx {
            if let Ok(ev) = serde_json::from_str::<serde_json::Value>(&line) {
                if ev["type"] == "agent_end" {
                    break;
                }
                // Pi sends {type:"response",success:false} for errors like missing API key
                if ev["type"] == "response" && ev["success"] == false {
                    let err = ev["error"].as_str().unwrap_or("unknown pi error");
                    drop(stdin);
                    let _ = child.kill();
                    let _ = child.wait();
                    anyhow::bail!("pi error: {}", err);
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
