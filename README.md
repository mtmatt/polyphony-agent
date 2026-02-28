# Polyphony Agent

A recursive agent structure that uses `gemini` (Gemini CLI) as a planner to decompose tasks and delegate them to sub-agents with specific contexts.

## Architecture

1.  **Agent Interface:** Base class for all agents (e.g., `execute_task`, `receive_context`).
2.  **Gemini Agent:** Uses the `gemini` CLI to decompose goals into sub-tasks and execute atomic tasks.
3.  **Recursive Execution:** An orchestrator that manages the recursive decomposition and execution of tasks.
4.  **CLI Wrapper:** Python interface for interacting with the agent system.

## Directory Structure

```text
polyphony-agent/
├── pyproject.toml         # Project metadata and dependencies
├── src/
│   └── polyphony/
│       ├── __init__.py
│       ├── agent.py        # Base Agent and Task models
│       ├── gemini_agent.py # Gemini-powered planning and execution
│       ├── engine.py       # Orchestration and recursive logic
│       └── cli.py          # CLI entry point
└── tests/                  # Test suite
```

## Setup

It is recommended to use `uv` for environment management.

```bash
# Create a virtual environment with Python 3.14
uv venv --python 3.14
source .venv/bin/activate

# Install the package in editable mode
uv pip install -e .
```

## Usage

You can run the agent by providing a goal as a string:

```bash
polyphony "Write a python script that fetches the current weather in London and saves it to a file."
```

### Providing a Specification
For complex tasks, you can provide an entire specification file as context:

```bash
polyphony "Implement the features described in the spec" --spec requirements.md
```
