# Polyphony Agent Architecture

Polyphony is a modular AI agent framework designed for efficient task execution and repository-aware planning. It follows a **Research -> Strategy -> Execution** lifecycle, optimized for both simple queries and complex multi-step engineering tasks.

## Core Components

### 1. Orchestrator (`src/polyphony/engine.py`)
The `Orchestrator` is the central brain of the system. It manages the flow of information between the user's goal and the agents.
- **Specification Context**: It can receive a large "spec" via the `--spec` CLI flag, providing detailed requirements from the start.
- **Goal Classification**: It first asks the planner to classify a goal as `simple` or `complex`.
- **Lazy Context**: It generates a "Repo Map" (directory structure) only if the goal requires it (e.g., tasks involving file modifications or project structure).
- **Task Decomposition**: For complex goals, it uses a Planner agent to break the goal into a sequence of `AgentTask` objects.
- **Execution Loop**: It iterates through tasks, using an Executor agent to perform the work and optionally running verification commands.

### 2. Agents (`src/polyphony/agent.py`)
Agents are abstracted via the `BaseAgent` class, allowing for multi-model support (Gemini, OpenAI, etc.).
- **Planner**: Specialized in high-level reasoning, task decomposition, and strategy.
- **Executor**: Specialized in performing specific actions, writing code, and interacting with tools.
- **Classification**: A fast-path classification method to avoid unnecessary planning overhead.

### 3. Task Model (`AgentTask`)
Tasks are structured objects containing:
- `description`: What needs to be done.
- `agent_type`: Whether it needs further planning (`planner`) or direct action (`executor`).
- `verification_command`: An optional shell command (like `pytest`) to verify success.
- `retry_logic`: Automated retry mechanism if verification fails.

## Key Workflows

### Plan-Act-Verify Loop
For every task executed by the Orchestrator:
1. **Act**: The Executor performs the task.
2. **Verify**: If a `verification_command` is provided, the Orchestrator runs it.
3. **Retry/Fix**: If verification fails, the error is fed back into the agent's context for a retry (up to a configurable limit).

### Resource Efficiency
To minimize token usage and latency:
- **Simple Task Fast-Path**: Direct execution without decomposition for one-off queries.
- **Heuristic Repo-Mapping**: The full project structure is only sent to the LLM if the goal contains keywords related to file/project manipulation.
- **Context Caching**: The repository map is cached during a single session to avoid redundant shell commands.

## Configuration (`polyphony.toml`)
The project supports fine-grained configuration for different stages. You can use a cheap, fast model for classification and execution, and a more capable model for complex planning.

```toml
[polyphony]
auto_commit = true

[polyphony.planner]
provider = "gemini"
model = "gemini-1.5-pro"

[polyphony.executor]
provider = "openai"
model = "gpt-4o-mini"
```
