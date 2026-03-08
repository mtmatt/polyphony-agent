# Polyphony Agent

A multi-agent orchestration framework for autonomous software engineering tasks. Polyphony decomposes goals into sub-tasks, executes them with AI agents, verifies results, and iterates — all from the command line.

## Features

- **Multi-provider support** — Gemini CLI, OpenAI, Anthropic Claude CLI, and Ollama (local)
- **Plan-Act-Verify loop** — tasks include verification commands; failed verifications trigger automated reflection and retry
- **Parallel execution** — independent tasks run concurrently via `asyncio` with a 4-worker concurrency limit
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
- **AST-based refactoring** — safe cross-file symbol renaming and function extraction
- **Doc generation** — auto-generates API docs, user guides, and Mermaid architecture diagrams from source

## Directory Structure

```text
polyphony-agent/
├── polyphony.toml          # Your config (gitignored)
├── polyphony.toml.example  # Config reference
├── pyproject.toml
├── tests/
└── src/polyphony/
    ├── agent.py            # Base agent interface, roles & shared models
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
    ├── refactoring.py      # AST-based cross-file refactoring engine
    ├── doc_generation.py   # API doc & diagram generation
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
model       = "gemini-3-flash-preview"

[executor]
provider    = "gemini"
model       = "gemini-3-flash-preview"
```

### Provider options

| Provider | `provider` value | Notes |
|---|---|---|
| Gemini CLI | `gemini` | Requires [`gemini` CLI](https://github.com/google-gemini/gemini-cli) installed & authenticated |
| OpenAI / compatible | `openai` | Set `api_key`, optional `base_url` for proxies or OpenAI-compatible APIs |
| Claude CLI | `claude` | Requires [`claude` CLI](https://github.com/anthropics/claude-code) installed & authenticated |
| Ollama (local) | `ollama` | Set `base_url` (default `http://localhost:11434`) |

### Full config reference

```toml
auto_commit      = false
budget_limit     = 5.0   # USD; 0 = unlimited
max_run_duration = 7200  # seconds

[planner]
provider   = "gemini"
model      = "gemini-3-flash-preview"
flash_model = ""         # optional lighter model for simple tasks
api_key    = ""          # if required by provider
base_url   = ""          # custom API endpoint

[executor]
provider   = "gemini"
model      = "gemini-3-flash-preview"
flash_model = ""
api_key    = ""
base_url   = ""

[[mcp_servers]]
command = "npx"
args    = ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/workspace"]
# env   = { KEY = "value" }
```

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
  --planner-provider gemini --planner-model gemini-3-flash-preview \
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

Provider (default for both planner and executor):
  --provider PROVIDER         gemini | openai | claude | ollama
  --model MODEL               Model name
  --flash-model MODEL         Lightweight model for simple sub-tasks
  --api-key KEY               API key
  --base-url URL              Base URL for provider API

Planner overrides:
  --planner-provider          Provider for planner agent
  --planner-model             Model for planner agent
  --planner-flash-model       Flash model for planner agent

Executor overrides:
  --executor-provider         Provider for executor agent
  --executor-model            Model for executor agent
  --executor-flash-model      Flash model for executor agent

QA overrides:
  --qa-provider               Provider for QA review agent
  --qa-model                  Model for QA review agent

Execution:
  --auto-commit               Auto-commit successful tasks to git
  --budget-limit USD          Hard spend limit in USD
  --max-duration SECONDS      Max run duration (default: 7200)

Checkpoints:
  --run-id ID                 Resume a specific checkpoint
  --resume                    Resume the latest checkpoint
  --list-checkpoints          List available checkpoints

Logging:
  --log-level LEVEL           DEBUG | INFO | WARNING | ERROR (default: INFO)
  --log-file FILE             Also write JSON structured logs to this file
  --json-logs                 Output JSON format to console

Templates:
  --template NAME             Run a workflow template
  --list-templates            List available templates

Dashboard:
  --dashboard                 Start the web UI
  --host HOST                 Dashboard host (default: 127.0.0.1)
  --port PORT                 Dashboard port (default: 8000)
```

## Agent Roles

Polyphony uses specialized agent roles for collaborative plan review:

| Role | Keyword triggers |
|---|---|
| `SECURITY_ARCHITECT` | security, auth, password, encrypt, token |
| `QA_SPECIALIST` | test, verify, validate, quality |
| `SENIOR_DEVELOPER` | refactor, architecture, design, complex |
| `PERFORMANCE_EXPERT` | performance, optimize, cache, load, slow |

When a task's description matches a role's keywords, that specialized agent is included in plan review.

## Task Model

Tasks produced by the planner support:

- **Dependencies** — `depends_on` list enforces ordering; independent tasks run in parallel
- **Complexity** — `"simple"` tasks use the flash model; `"complex"` tasks use the full model
- **Verification** — optional `verification_command` is run after execution; failure triggers retry
- **Retries** — up to `max_retries` (default 2) attempts with smart error-categorized reflection prompts
- **Agent type** — tasks can be `"executor"` or `"planner"` (for recursive decomposition)

## Error Recovery

The engine categorizes failures into: `SYNTAX`, `IMPORT`, `TEST`, `FILE_NOT_FOUND`, `DISK_FULL`, `TIMEOUT`, `PERMISSION`, `API_ERROR`, `UNKNOWN`. Each category produces a tailored reflection prompt for the retry attempt.

## Run Summaries

After each run, Polyphony saves a Markdown and JSON summary to `./logs/`:

```
logs/
  polyphony-run-<slug>-<timestamp>.md
  polyphony-run-<slug>-<timestamp>.json
```

Summaries include task statistics, token usage, cost breakdown, and timing.

## Development

```bash
# Run tests
pytest

# Run a specific test file
pytest tests/test_engine.py -v
```
