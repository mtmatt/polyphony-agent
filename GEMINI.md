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
5.  **MCP (Model Context Protocol) Support (Future):**
    *   Requirement: Ability to plug into local tools via MCP servers.

# Implementation Roadmap (Prioritized)

1.  **High: Enhanced Git-Native Integration** COMPLETED
    *   Goal: Parity between `OpenAIAgent` and `GeminiAgent` for descriptive commit messages.
    *   Task: Implement `generate_commit_message` in `OpenAIAgent`.
2.  **High: Smarter Plan-Act-Verify Loop** COMPLETED
    *   Goal: Move beyond simple retries to "Reflection-based" error correction.
    *   Task: Update `Orchestrator` to provide agents with a dedicated reflection prompt on verification failure.
3.  **Medium: Intelligent Repository Mapping** COMPLETED
    *   Goal: Scoped and accurate repo maps for large projects.
    *   Task: Optimize `utils.get_repo_map` using `ast` and implement task-based directory filtering.
4.  **Medium: MCP Support Integration** COMPLETED
    *   Goal: Dynamic tool discovery and invocation via MCP servers.
    *   Task: Define `MCPServerConfig` in `config.py` and implement an `MCPClient` integrated into `OpenAIAgent`'s tool loop.
5.  **Low: Dynamic Model Switching** COMPLETED
    *   Goal: Optimize cost/latency by selecting models based on task complexity.
    *   Task: Implement automated model selection in `Orchestrator` for simple vs. complex goals.
