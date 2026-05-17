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
