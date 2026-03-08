# Polyphony Agent — CLAUDE.md

Developer notes for Claude Code when working on this project.

## Project Overview

Polyphony is a Python multi-agent orchestration framework. Users run `polyphony "<goal>"` and the system plans, executes, verifies, and checkpoints tasks using AI agents across multiple providers.

## Key Files

| File | Role |
|---|---|
| `src/polyphony/cli.py` | Entry point; argument parsing; `create_agent()` factory; `main()` |
| `src/polyphony/engine.py` | `Orchestrator` class; plan-act-verify loop; parallel execution; checkpointing |
| `src/polyphony/agent.py` | `BaseAgent` ABC; `AgentTask`, `AgentRole`, `CollaborativePlan` models |
| `src/polyphony/config.py` | `Config`, `AgentConfig`, `MCPServerConfig` Pydantic models; `load_config()` |
| `src/polyphony/gemini_agent.py` | Gemini CLI provider |
| `src/polyphony/openai_agent.py` | OpenAI/compatible provider |
| `src/polyphony/claude_agent.py` | Claude CLI provider |
| `src/polyphony/ollama_agent.py` | Ollama provider with MCP tool-calling |
| `src/polyphony/checkpoint.py` | Atomic checkpoint save/load |
| `src/polyphony/memory.py` | SQLite-backed run memory |
| `src/polyphony/cost.py` | Token/cost tracking |
| `src/polyphony/metrics.py` | Task metrics |
| `src/polyphony/refactoring.py` | AST-based cross-file refactoring engine |
| `src/polyphony/doc_generation.py` | API doc and Mermaid diagram generation |
| `src/polyphony/web/server.py` | FastAPI dashboard backend |

## Architecture

```
CLI (cli.py)
  └─ Orchestrator (engine.py)
       ├─ Planner agent  → decompose_goal() → List[AgentTask]
       ├─ DependencyResolver → batch tasks for parallel execution
       ├─ Executor agent  → execute_task() per task
       │    └─ verify → retry loop (max 2, error-categorized reflection)
       ├─ QA agent (optional) → review_plan()
       └─ Checkpoint after each completed task
```

## Configuration

- Config file: `polyphony.toml` (gitignored; copy from `polyphony.toml.example`)
- Loaded via `load_config()` in `config.py`; supports flat or `[planner]`/`[executor]` sections
- Defaults: provider=gemini, model=gemini-3-flash-preview, no budget limit, 2h max duration

## Provider Pattern

All agents extend `BaseAgent` and must implement:
- `execute_task(task, context) -> str`
- `decompose_goal(goal, context) -> List[AgentTask]`
- `classify_goal(goal) -> "simple" | "complex"`
- `review_plan(plan, role) -> PlanReview`
- `model_name` property (get/set)
- `pro_model_name` property
- `flash_model_name` property (optional)

When adding a new provider, also register it in `create_agent()` in `cli.py`.

## Task Model

`AgentTask` fields to know:
- `depends_on`: list of task IDs that must complete first
- `complexity`: `"simple"` → flash model; `"complex"` → pro model
- `verification_command`: shell command run after execution; non-zero exit triggers retry
- `agent_type`: `"executor"` or `"planner"` (recursive decomposition)
- `status`: pending → in-progress → completed | failed

## Error Categorization (engine.py)

`_categorize_error()` maps stderr patterns to `ErrorCategory` enum. `_generate_reflection_prompt()` uses the category to build a focused retry prompt. Categories: `SYNTAX`, `IMPORT`, `TEST`, `FILE_NOT_FOUND`, `DISK_FULL`, `TIMEOUT`, `PERMISSION`, `API_ERROR`, `UNKNOWN`.

## Parallel Execution

`_execute_parallel()` uses `asyncio.Semaphore(4)`. `DependencyResolver.resolve()` groups tasks into waves — tasks within a wave have no inter-dependencies and run concurrently.

## Testing

```bash
pytest                    # all tests
pytest tests/test_engine.py -v
```

Test files mirror source modules. Mocks for agents live inline in each test file (e.g., `MockAgent`, `RecoveryMockAgent`).

## Python Version

Requires Python >= 3.14. Use `uv venv --python 3.14`.

## Dependencies

Core: `pydantic>=2`, `rich>=14`, `openai>=2.24`, `structlog>=24.1`, `fastapi>=0.110`, `uvicorn>=0.27`, `requests>=2.31`

## Common Pitfalls

- `polyphony.toml` is gitignored — never commit it; use `polyphony.toml.example` as the reference
- `budget_limit = 0` means unlimited (not zero budget)
- Checkpoint files are stored relative to CWD under `.polyphony/checkpoints/` by default
- The `flash_model` is optional; if not set, the main model is used for all tasks
