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

# Completed Features

1.  **Enhanced Git-Native Integration** - COMPLETED
2.  **Smarter Plan-Act-Verify Loop** - COMPLETED
3.  **Parallel Task Execution** - COMPLETED
4.  **Intelligent Repository Mapping** - COMPLETED (Supports Python, JS/TS, Go, Rust, Java)
5.  **MCP Support Integration** - COMPLETED
6.  **Dynamic Model Switching** - COMPLETED
7.  **Cost Tracking & Budget Management** - COMPLETED
8.  **Checkpointing & Resume** - COMPLETED (Atomic saves, recursive task support)
9.  **Enhanced Error Recovery** - COMPLETED (Categorized handlers, model fallback, robust parallel execution)
10. **Extended Session Duration (2-Hour Passes)** - COMPLETED
11. **Streaming Output & Progress** - COMPLETED (Real-time streaming callbacks, event-based progress UI, parallel execution status)
12. **Test Generation** - COMPLETED (Automatic unit test generation, property-based testing patterns, `generate_and_run_tests` utility)
13. **Enhanced Logging & Observability** - COMPLETED (Structured logging, log levels, metrics collection)
14. **Multi-Language Support** - COMPLETED (Symbol extraction for major languages)
15. **Web Interface** - COMPLETED (FastAPI-based dashboard with task graphs)
16. **Advanced Context Management** - COMPLETED (Intelligent context pruning)
17. **Collaborative Multi-Agent Protocols** - COMPLETED (Specialized QA Agent role)
18. **Local Model Support** - COMPLETED (Ollama integration)
19. **Security & Safety** - COMPLETED (Secure sandbox mode for Gemini)
20. **Workflow Templates** - COMPLETED (Scaffolding for common projects)

# Potential Improvements

1. **Self-Optimizing Workflows**
    *   Agents should analyze their own performance metrics across runs to suggest architectural changes to the host application (Meta-Optimization).

2. **Predictive Context Loading**
    *   Pre-fetching repository maps and documentation for files identified in the planning phase before they are explicitly requested by execution agents.

3. **Collaborative Multi-Agent Planning**
    *   Utilizing different specialized agent roles (e.g., Security Architect, Senior Dev, QA Specialist) during the `enter_plan_mode` phase for high-stakes features.

4. **Hardware-Accelerated Tooling**
    *   Integration with local inference servers for sub-millisecond classification and simple task evaluation.

# Recent Performance Audit Findings (March 2026)

- **Sequential Bottleneck:** Prior to the parallelization update, complex goals with 10+ tasks were experiencing significant idle time while waiting for independent sub-tasks to complete sequentially.
- **Dependency Clarity:** The addition of the `depends_on` field to the `Task` model has improved the agent's ability to express structural relationships between steps, not just linear order.
- **Atomic Reliability:** During the audit of the `complex` todo example, it was discovered that robust atomic file saves (using `fsync` and temporary files) are critical when operating under resource-constrained environments (e.g., simulated disk full scenarios).

# Future Agent Frontiers (2026-2027)

1.  **Self-Optimizing Workflows:** Agents should analyze their own performance metrics across runs to suggest architectural changes to the host application (Meta-Optimization).
2.  **Predictive Context Loading:** Pre-fetching repository maps and documentation for files identified in the planning phase before they are explicitly requested by execution agents.
3.  **Collaborative Multi-Agent Planning:** Utilizing different specialized agent roles (e.g., Security Architect, Senior Dev, QA Specialist) during the `enter_plan_mode` phase for high-stakes features.
4.  **Hardware-Accelerated Tooling:** Integration with local inference servers for sub-millisecond classification and simple task evaluation.

