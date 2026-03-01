# Project Mandates

- **Language:** Python 3.14+
- **Dependency Management:** Use `pyproject.toml` (standard `pip` / `uv` compatibility).
- **Core Dependencies:** `pydantic` for structured data, `rich` for CLI output.
- **Planner:** Use `gemini` via subprocess for planning tasks.
- **Recursive Logic:** Ensure agents can spawn other agents with specific, narrowed context.
- **Testing:** Maintain a `tests/` directory with `pytest`.

# Target Features (2026 CLI AI Standards)

1.  **Git-Native Integration:**
    *   Requirement: Optional auto-commit after successful task execution.
    *   Requirement: Generate descriptive commit messages based on task output.
2.  **Plan-Act-Verify Loop:**
    *   Requirement: Decomposed tasks must include a verification step (e.g., running a test or checking a file).
    *   Requirement: Automated retry/fix logic if verification fails.
3.  **Repository Awareness:**
    *   Requirement: Provide the agent with a "repo map" (file structure + key symbols) to improve context.
4.  **Multi-Model Support:**
    *   Requirement: Configurable models for different stages (Planning vs. Execution).
5.  **Parallel Execution Support (NEW):**
    *   Requirement: Identification of independent tasks within a plan.
    *   Requirement: Simultaneous execution using `asyncio` to minimize total latency.
6.  **MCP (Model Context Protocol) Support:**
    *   Requirement: Ability to plug into local tools via MCP servers.

# Implementation Roadmap (Prioritized)

1.  **High: Enhanced Git-Native Integration** COMPLETED
    *   Goal: Parity between `OpenAIAgent` and `GeminiAgent` for descriptive commit messages.
    *   Task: Implement `generate_commit_message` in `OpenAIAgent`.
2.  **High: Smarter Plan-Act-Verify Loop** COMPLETED
    *   Goal: Move beyond simple retries to "Reflection-based" error correction.
    *   Task: Update `Orchestrator` to provide agents with a dedicated reflection prompt on verification failure.
3.  **High: Parallel Task Execution** COMPLETED (Self-Improvement Cycle #1)
    *   Goal: Reduce execution time by processing independent tasks concurrently.
    *   Task: Implement `depends_on` in Task models and refactor `Orchestrator` to use `asyncio.gather` for non-sequential batches.
4.  **Medium: Intelligent Repository Mapping** COMPLETED
    *   Goal: Scoped and accurate repo maps for large projects.
    *   Task: Optimize `utils.get_repo_map` using `ast` and implement task-based directory filtering.
5.  **Medium: MCP Support Integration** COMPLETED
    *   Goal: Dynamic tool discovery and invocation via MCP servers.
    *   Task: Define `MCPServerConfig` in `config.py` and implement an `MCPClient` integrated into `OpenAIAgent`'s tool loop.
6.  **Low: Dynamic Model Switching** COMPLETED
    *   Goal: Optimize cost/latency by selecting models based on task complexity.
    *   Task: Implement automated model selection in `Orchestrator` for simple vs. complex goals.

# Recent Performance Audit Findings (March 2026)

- **Sequential Bottleneck:** Prior to the parallelization update, complex goals with 10+ tasks were experiencing significant idle time while waiting for independent sub-tasks to complete sequentially.
- **Dependency Clarity:** The addition of the `depends_on` field to the `Task` model has improved the agent's ability to express structural relationships between steps, not just linear order.
- **Atomic Reliability:** During the audit of the `complex` todo example, it was discovered that robust atomic file saves (using `fsync` and temporary files) are critical when operating under resource-constrained environments (e.g., simulated disk full scenarios).

# Future Agent Frontiers (2026-2027)

1.  **Self-Optimizing Workflows:** Agents should analyze their own performance metrics across runs to suggest architectural changes to the host application (Meta-Optimization).
2.  **Predictive Context Loading:** Pre-fetching repository maps and documentation for files identified in the planning phase before they are explicitly requested by execution agents.
3.  **Collaborative Multi-Agent Planning:** Utilizing different specialized agent roles (e.g., Security Architect, Senior Dev, QA Specialist) during the `enter_plan_mode` phase for high-stakes features.
4.  **Hardware-Accelerated Tooling:** Integration with local inference servers for sub-millisecond classification and simple task evaluation.
