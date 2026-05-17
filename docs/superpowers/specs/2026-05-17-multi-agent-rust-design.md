# Polyphony Agent — Multi-Agent Orchestration System (Rust)

**Date:** 2026-05-17  
**Status:** Approved

---

## Overview

Polyphony is a Rust-based multi-agent orchestration system that coordinates multiple AI coding agent providers (Claude Code, Pi, Codex) across four specialized roles. It runs unattended for hours, splits work into sequential atomic tasks, auto-verifies results, and retries on failure. Full checkpoint/resume support ensures a crash never loses progress.

---

## Input Modes

**Natural language input:** User provides a plain-text task description via CLI. The Planner engages in an interactive clarification loop before writing a spec.

**Spec file input:** User provides `--spec <path>`. The Planner is skipped entirely and the system begins at the Orchestrating state.

---

## Roles

| Role | Responsibility | Default Provider | Default Model |
|---|---|---|---|
| Planner | Clarify intent, write spec.md | Pi | gpt-4o |
| Orchestrator | Design task list, curate context | Claude Code | claude-opus-4-7 |
| Coder | Implement each task | Codex | codex |
| Verifier | Check implementation against spec | Pi | claude-sonnet-4-6 |

All role-to-provider mappings are user-configurable in `polyphony.toml`.

---

## Agent Providers

All providers are driven as subprocesses by the Rust engine.

- **ClaudeCodeAgent** — spawns the `claude` CLI
- **PiAgent** — spawns `pi --mode rpc`, communicates via newline-delimited JSONL over stdin/stdout
- **CodexAgent** — spawns the `codex` CLI

Each implements the `AgentProvider` trait:

```rust
trait AgentProvider: Send + Sync {
    fn run(&self, prompt: &str) -> Result<String>;
    fn name(&self) -> &str;
}
```

---

## State Machine

The engine is an explicit state machine persisted to SQLite. Every transition is written to `state.db` before the corresponding agent call executes, making all transitions safe to resume after a crash.

```
Idle
→ Clarifying { turn: u32 }          # natural-language input only
→ Planning                           # Planner writes spec.md
→ Orchestrating                      # Orchestrator produces tasks.json
→ Coding { task_idx: u32, attempt: u32 }
→ Verifying { task_idx: u32, attempt: u32 }
→ Done
→ Failed { reason: String }
```

On startup, the engine checks for an existing `state.db` in the run directory. If found, it restores the last committed state and resumes from there.

---

## Run Directory Layout

Each run gets a unique directory: `runs/<timestamp>-<slug>/`

```
runs/2026-05-17T14-30-00-add-login-page/
├── state.db                          # SQLite checkpoint
├── spec.md                           # written by Planner (or copied from --spec)
├── planner/
│   ├── prompt.md
│   └── output.md
├── orchestrator/
│   ├── prompt.md
│   ├── output.md
│   └── tasks.json
├── tasks/
│   ├── 001/
│   │   ├── coder_prompt.md
│   │   ├── coder_output.md
│   │   ├── verifier_prompt.md
│   │   └── verifier_result.json
│   └── 002/
│       └── ...
└── run_summary.json                  # written on Done or Failed
```

---

## Data Flow

### Natural Language Path

1. User provides task string via CLI
2. Planner receives prompt + clarification template → asks user questions interactively
3. Loop until Planner signals completion
4. Planner writes `spec.md` → state advances to Orchestrating

### Spec File Path

1. User provides `--spec ./path/to/spec.md`
2. `spec.md` copied into run directory
3. State begins at Orchestrating (Planner skipped)

### Orchestrating → Coding → Verifying Loop

```
Orchestrator ← spec.md + repo map
Orchestrator → tasks.json (ordered, atomic task list)

For each task:
  attempt = 0
  loop:
    ContextBuilder assembles prompt:
      - repo map (file tree + relevant file contents)
      - task description from tasks.json
      - outputs from previously completed tasks
      - [on retry] verifier failure reason from previous attempt

    Coder ← assembled prompt
    Coder → code changes applied to repo
    FileRecorder writes: coder_prompt.md, coder_output.md

    Verifier ← spec section + task description + git diff of changes
    Verifier → { passed: bool, reason: String }
    FileRecorder writes: verifier_prompt.md, verifier_result.json

    if passed:
      advance to next task
    elif attempt < max_retries:
      attempt += 1, loop
    else:
      State → Failed, write run_summary.json, halt

All tasks passed → State → Done, write run_summary.json
```

---

## tasks.json Schema

The Orchestrator must produce a JSON array. Each element:

```json
{
  "id": "001",
  "title": "Add JWT middleware",
  "description": "Implement JWT verification middleware in src/auth/middleware.rs ...",
  "relevant_files": ["src/auth/", "src/config.rs"],
  "depends_on": []
}
```

`depends_on` is informational only — execution is always sequential in `id` order. If the Orchestrator output fails to parse as this schema, the engine retries with an error-correction prompt.

---

## Planner Termination

The Planner clarification loop ends when the Planner's response contains a `<spec>...</spec>` block. The engine extracts this block and writes it to `spec.md`. If no `<spec>` block appears after `max_retries` turns, the engine halts with an error.

---

## Context Injection

The `ContextBuilder` is responsible for assembling the exact prompt fed to each Coder call. It never passes the full repo — only what is relevant:

- **Repo map**: directory tree (via `find`) with file sizes; for `.rs`, `.ts`, `.py`, `.go` files, top-level symbol names extracted via regex (function/struct/class/def names only — no full AST)
- **Relevant files**: files mentioned in the task description or referenced by recently changed files
- **Previous task outputs**: summaries of what prior tasks implemented (not full outputs)
- **Failure context** (on retry): the verifier's `reason` string appended to the prompt

---

## Configuration

`polyphony.toml` in the project root (or passed via `--config`):

```toml
[roles]
planner      = { provider = "pi",     model = "gpt-4o" }
orchestrator = { provider = "claude", model = "claude-opus-4-7" }
coder        = { provider = "codex",  model = "codex" }
verifier     = { provider = "pi",     model = "claude-sonnet-4-6" }

[run]
max_retries = 3
runs_dir    = "runs"
```

---

## Error Handling

| Error | Behavior |
|---|---|
| Subprocess crash / non-zero exit | Retry the call up to `max_retries`, then `Failed` |
| Malformed `tasks.json` from Orchestrator | Retry with error-correction prompt appended |
| Malformed `verifier_result.json` | Treat as verification failure, retry Coder |
| File write failure | Propagate as fatal error, halt immediately |

**Checkpoint safety:** State is written to SQLite *before* the agent call. A crash during a call causes the same call to re-run on resume — all agent calls must be treated as idempotent from the engine's perspective (the Coder re-applies changes; the Verifier re-checks).

**FileRecorder atomicity:** All file writes go to a `.tmp` sibling first, then renamed into place. The run directory never contains partial files.

---

## Testing Strategy

- **Unit tests**: `StateMachine` transitions, `ContextBuilder` prompt assembly, `FileRecorder` atomic write behavior, config parsing
- **Integration tests**: `MockAgentProvider` returns canned responses — full pipeline runs without real subprocesses
- **End-to-end**: one test against a small real repo using Pi with the cheapest available model to verify the full loop
