# Polyphony Agent

A multi-agent orchestration framework for autonomous software engineering tasks. Polyphony decomposes goals into sub-tasks, executes them with AI agents, verifies results, and iterates — all from the command line.

## Features

- **Multi-provider support** — Gemini CLI, OpenAI, Anthropic Claude CLI, and Ollama (local)
- **Plan-Act-Verify loop** — tasks include verification commands; failed verifications trigger automated reflection and retry
- **Parallel execution** — independent tasks run concurrently via `asyncio`
- **Repository awareness** — AST-based repo map across Python, JS/TS, Go, Rust, Java fed into every agent prompt
- **Checkpointing & resume** — atomic saves after every task; resume interrupted runs by ID or latest
- **MCP (Model Context Protocol)** — plug in local tool servers for dynamic tool discovery
- **Git-native** — optional auto-commit with AI-generated commit messages after successful tasks
- **Cost & budget management** — live token tracking, per-model pricing, hard `--budget-limit` enforcement
- **Structured logging** — single-line ANSI console output + JSON file logging via structlog
- **Web dashboard** — FastAPI-based UI at `http://localhost:8000` for live task graphs and metrics
- **Workflow templates** — scaffolding for common project types
- **Collaborative review** — specialized agent roles (Security Architect, QA Specialist, Senior Dev) review plans before execution
- **Memory** — SQLite-backed run memory; learns from past successes and failures

## Directory Structure

```text
polyphony-agent/
├── polyphony.toml          # Your config (gitignored)
├── polyphony.toml.example  # Config reference
├── pyproject.toml
└── src/polyphony/
    ├── agent.py            # Base agent interface & shared models
    ├── gemini_agent.py     # Gemini CLI agent
    ├── openai_agent.py     # OpenAI agent
    ├── claude_agent.py     # Claude CLI agent
    ├── ollama_agent.py     # Local Ollama agent
    ├── engine.py           # Orchestrator, parallel execution, verify loop
    ├── cli.py              # CLI entry point
    ├── config.py           # TOML config loader
    ├── checkpoint.py       # Run checkpointing & resume
    ├── mcp_client.py       # MCP server client
    ├── cost.py             # Token usage & cost tracking
    ├── memory.py           # Persistent run memory (SQLite)
    ├── metrics.py          # Task metrics collection
    ├── logging.py          # Structured console + file logging
    ├── run_summary.py      # Markdown/JSON run summaries
    ├── workflow.py         # Workflow templates
    ├── ast_parsing.py      # Multi-language symbol extraction
    ├── utils.py            # Repo mapping, file tools
    └── web/                # FastAPI dashboard
```

## Setup

```bash
uv venv --python 3.14
source .venv/bin/activate
uv pip install -e .
```

## Configuration

Copy the example config and edit as needed:

```bash
cp polyphony.toml.example polyphony.toml
```

```toml
# polyphony.toml

auto_commit  = false
budget_limit = 5.0        # USD; 0 = unlimited

[planner]
provider    = "gemini"
model       = "gemini-2.5-pro-exp"
flash_model = "gemini-2.5-flash-exp"

[executor]
provider    = "openai"
model       = "gpt-4o"
flash_model = "gpt-4o-mini"
```

### Provider options

| Provider | `provider` value | Notes |
|---|---|---|
| Gemini CLI | `gemini` | Requires [`gemini` CLI](https://github.com/google-gemini/gemini-cli) installed & authenticated |
| OpenAI / compatible | `openai` | Set `api_key`, optional `base_url` for proxies or Ollama OpenAI-compat |
| Claude CLI | `claude` | Requires [`claude` CLI](https://github.com/anthropics/claude-code) installed & authenticated |
| Ollama (local) | `ollama` | Set `base_url` (default `http://localhost:11434`) |

## Usage

```bash
# Basic goal
polyphony "Add input validation to all API endpoints"

# With a spec file as additional context
polyphony "Implement all features in the spec" --spec REQUIREMENTS.md

# Limit budget and run time
polyphony "Refactor the auth module" --budget-limit 2.50 --max-duration 3600

# Choose a specific provider/model at the command line
polyphony "Write unit tests for utils.py" --provider claude --model claude-sonnet-4-5

# Override planner and executor independently
polyphony "Large refactor" \
  --planner-provider gemini --planner-model gemini-2.5-pro-exp \
  --executor-provider claude --executor-model claude-sonnet-4-5

# JSON logs (for ingestion into log aggregators)
polyphony "..." --json-logs --log-file ./logs/run.json

# Start the web dashboard
polyphony --dashboard
```

### Checkpointing & Resume

Every completed task is checkpointed atomically. If a run is interrupted:

```bash
# List saved checkpoints
polyphony --list-checkpoints

# Resume a specific run
polyphony --run-id <run-id>

# Resume the latest run automatically
polyphony --resume
```

### Workflow Templates

```bash
# List available templates
polyphony --list-templates

# Run a template
polyphony --template python-library
```

### MCP Servers

Add MCP tool servers to `polyphony.toml`:

```toml
[[mcp_servers]]
command = "npx"
args    = ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/workspace"]
```

## CLI Reference

```
polyphony [goal] [options]

Arguments:
  goal                        The goal for the agent to achieve

Options:
  --config FILE               Config file path (default: polyphony.toml)
  --spec FILE                 Specification file to include as context
  --provider PROVIDER         Default provider: gemini | openai | claude | ollama
  --model MODEL               Default model name
  --flash-model MODEL         Default flash/fast model name
  --planner-provider          Provider override for planner
  --planner-model             Model override for planner
  --executor-provider         Provider override for executor
  --executor-model            Model override for executor
  --qa-provider               Provider for QA review agent
  --qa-model                  Model for QA review agent
  --auto-commit               Auto-commit successful tasks to git
  --budget-limit USD          Hard spend limit in USD
  --max-duration SECONDS      Max run duration (default: 7200)
  --run-id ID                 Resume a specific checkpoint
  --resume                    Resume the latest checkpoint
  --list-checkpoints          List available checkpoints
  --template NAME             Run a workflow template
  --list-templates            List available templates
  --log-level LEVEL           DEBUG | INFO | WARNING | ERROR (default: INFO)
  --log-file FILE             Also write JSON structured logs to this file
  --json-logs                 Output JSON format to console
  --dashboard                 Start the web UI
  --host HOST                 Dashboard host (default: 127.0.0.1)
  --port PORT                 Dashboard port (default: 8000)
```

## Run Summaries

After each run, Polyphony saves a Markdown and JSON summary to `./logs/`:

```
logs/
  polyphony-run-<slug>-<timestamp>.md
  polyphony-run-<slug>-<timestamp>.json
```

## Development

```bash
# Run tests
pytest

# Run a specific test file
pytest tests/test_engine.py -v
```

