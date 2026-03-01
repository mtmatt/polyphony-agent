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
4.  **Intelligent Repository Mapping** - COMPLETED
5.  **MCP Support Integration** - COMPLETED
6.  **Dynamic Model Switching** - COMPLETED
7.  **Cost Tracking & Budget Management** - COMPLETED
8.  **Checkpointing & Resume** - COMPLETED

# Potential Improvements

## High Priority

1.  **Streaming Output & Progress**
    *   Real-time streaming of agent thoughts and tool calls during execution
    *   Live progress indicators for long-running operations
    *   WebSocket or SSE support for web-based monitoring

2.  **Enhanced Error Recovery**
    *   Categorized error handlers for different failure types
    *   Automatic fallback strategies (e.g., switch to simpler models)
    *   Context-aware retry with modified approaches

3.  **Test Generation**
    *   Automatic generation of unit tests for created code
    *   Property-based testing suggestions
    *   Coverage analysis and gap identification

## Medium Priority

5.  **Agent Memory & Learning**
    *   Persistent memory of past runs and common patterns
    *   Learn from successful strategies for similar tasks
    *   User preference learning (coding style, conventions)

6.  **Interactive Mode**
    *   Human-in-the-loop approval for critical operations
    *   Interactive clarification when goal is ambiguous
    *   Mid-run parameter adjustment

7.  **Cross-File Refactoring**
    *   Safe rename operations across multiple files
    *   Extract function/class with automatic import updates
    *   Dependency impact analysis

8.  **Documentation Generation**
    *   Auto-generate API documentation from code
    *   Create user guides and tutorials
    *   Architecture diagram generation

9.  **Performance Profiling**
    *   Identify performance bottlenecks in execution flow
    *   Token usage optimization suggestions
    *   Parallel execution opportunity detection

## Low Priority

10. **Enhanced Logging & Observability**
    *   Structured logging with log levels
    *   OpenTelemetry integration for tracing
    *   Performance metrics dashboard

11. **Multi-Language Support**
    *   Support for JavaScript/TypeScript, Go, Rust, Java
    *   Language-specific AST parsing and repo maps
    *   Cross-language dependency tracking

12. **Web Interface**
    *   Browser-based dashboard for run monitoring
    *   Historical run comparison and analytics
    *   Visual task dependency graphs

13. **Advanced Context Management**
    *   Intelligent context pruning based on relevance
    *   Semantic caching of frequently accessed files
    *   Incremental context updates instead of full reloads

14. **Collaborative Multi-Agent Protocols**
    *   Specialized agent roles (Architect, QA, Security)
    *   Agent negotiation and consensus mechanisms
    *   Parallel agent collaboration on sub-problems

15. **Local Model Support**
    *   Integration with Ollama, LM Studio
    *   On-device inference for simple tasks
    *   Hybrid cloud/local execution strategies

16. **Security & Safety**
    *   Sandbox execution environment for untrusted code
    *   Security vulnerability scanning
    *   Permission system for file operations

17. **Workflow Templates**
    *   Pre-defined workflows for common patterns (CRUD app, API, etc.)
    *   Custom workflow definition language
    *   Workflow composition and reuse

# Recent Performance Audit Findings (March 2026)

- **Sequential Bottleneck:** Prior to the parallelization update, complex goals with 10+ tasks were experiencing significant idle time while waiting for independent sub-tasks to complete sequentially.
- **Dependency Clarity:** The addition of the `depends_on` field to the `Task` model has improved the agent's ability to express structural relationships between steps, not just linear order.
- **Atomic Reliability:** During the audit of the `complex` todo example, it was discovered that robust atomic file saves (using `fsync` and temporary files) are critical when operating under resource-constrained environments (e.g., simulated disk full scenarios).

# Future Agent Frontiers (2026-2027)

1.  **Self-Optimizing Workflows:** Agents should analyze their own performance metrics across runs to suggest architectural changes to the host application (Meta-Optimization).
2.  **Predictive Context Loading:** Pre-fetching repository maps and documentation for files identified in the planning phase before they are explicitly requested by execution agents.
3.  **Collaborative Multi-Agent Planning:** Utilizing different specialized agent roles (e.g., Security Architect, Senior Dev, QA Specialist) during the `enter_plan_mode` phase for high-stakes features.
4.  **Hardware-Accelerated Tooling:** Integration with local inference servers for sub-millisecond classification and simple task evaluation.


# Recent Runs

### Run: original goal

- **Date:** 2026-03-01
- **Duration:** 0:00:00.003142
- **Status:** [SUCCESS]
- **Total Cost:** $0.0000
- **Tasks Completed:** 2/2

**Completed Tasks:**
- t1
- t2

### Run: original goal

- **Date:** 2026-03-01
- **Duration:** 0:00:00.003205
- **Status:** [SUCCESS]
- **Total Cost:** $0.0000
- **Tasks Completed:** 2/2

**Completed Tasks:**
- t1
- t2

### Run: original goal

- **Date:** 2026-03-01
- **Duration:** 0:00:00.003514
- **Status:** [SUCCESS]
- **Total Cost:** $0.0000
- **Tasks Completed:** 2/2

**Completed Tasks:**
- t1
- t2

### Run: Improve your self.

- **Date:** 2026-03-01
- **Duration:** 0:12:03.533411
- **Status:** [SUCCESS]
- **Tasks Completed:** 3/3

**Completed Tasks:**
- Research token usage extraction for Gemini and OpenAI, create a CostTracker module using Pydantic, and update agent implementations to report usage after each step.
- Add budget configuration to the config system and implement enforcement logic in the Engine to warn or halt when limits are reached.
- Create comprehensive unit tests for the cost tracking system and update GEMINI.md to mark the feature as completed.

### Run: simple goal

- **Date:** 2026-03-01
- **Duration:** 0:00:00.001793
- **Status:** [SUCCESS]
- **Total Cost:** $0.0000
- **Tasks Completed:** 1/1

**Completed Tasks:**
- simple goal

### Run: simple goal

- **Date:** 2026-03-01
- **Duration:** 0:00:00.002394
- **Status:** [SUCCESS]
- **Total Cost:** $0.0000
- **Tasks Completed:** 1/1

**Completed Tasks:**
- simple goal

### Run: simple goal

- **Date:** 2026-03-01
- **Duration:** 0:00:00.000940
- **Status:** [SUCCESS]
- **Total Cost:** $0.0000
- **Tasks Completed:** 1/1

**Completed Tasks:**
- simple goal

### Run: simple goal

- **Date:** 2026-03-01
- **Duration:** 0:00:00.002350
- **Status:** [SUCCESS]
- **Total Cost:** $0.0000
- **Tasks Completed:** 1/1

**Completed Tasks:**
- simple goal
