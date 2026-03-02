import argparse
import os
import sys
import asyncio
from typing import Optional, List, Dict, Any
from rich.console import Console

from .gemini_agent import GeminiAgent
from .openai_agent import OpenAIAgent
from .ollama_agent import OllamaAgent
from .engine import Orchestrator
from .config import load_config, AgentConfig, Config, MCPServerConfig
from .checkpoint import RunCheckpoint
from .logging import setup_logging, setup_tracing
from .workflow import list_templates, get_template

console = Console()

def create_agent(agent_config: AgentConfig, mcp_servers: Optional[List[MCPServerConfig]] = None):
    if agent_config.provider == "gemini":
        return GeminiAgent(
            model_name=agent_config.model or "gemini-3-flash-preview", 
            flash_model_name=agent_config.flash_model,
            mcp_servers=mcp_servers,
            sandbox=agent_config.sandbox
        )
    elif agent_config.provider == "openai":
        return OpenAIAgent(
            model_name=agent_config.model or "gpt-4o", 
            api_key=agent_config.api_key or os.environ.get("OPENAI_API_KEY"),
            base_url=agent_config.base_url
        )
    elif agent_config.provider == "ollama":
        return OllamaAgent(
            model_name=agent_config.model or "llama3",
            base_url=agent_config.base_url or "http://localhost:11434"
        )
    else:
        raise ValueError(f"Unsupported provider: {agent_config.provider}")

async def run_async(orchestrator, goal, context):
    await orchestrator.run_goal(goal, context)

def main():
    parser = argparse.ArgumentParser(description="Polyphony Agent - 2026 CLI AI Standard")
    parser.add_argument("goal", nargs="?", help="The goal you want the agent to achieve.")
    parser.add_argument("--config", type=str, default="polyphony.toml", help="Path to the config file.")
    parser.add_argument("--provider", type=str, choices=["gemini", "openai", "ollama"], help="Default AI provider.")
    parser.add_argument("--model", type=str, help="Default model name.")
    parser.add_argument("--flash-model", type=str, help="Default flash model name.")
    parser.add_argument("--api-key", type=str, help="API key for the provider.")
    parser.add_argument("--base-url", type=str, help="Base URL for the provider API.")
    
    # Advanced options
    parser.add_argument("--planner-provider", type=str, choices=["gemini", "openai", "ollama"], help="Provider for the planner agent.")
    parser.add_argument("--planner-model", type=str, help="Model for the planner agent.")
    parser.add_argument("--planner-flash-model", type=str, help="Flash model for the planner agent.")
    parser.add_argument("--executor-provider", type=str, choices=["gemini", "openai", "ollama"], help="Provider for the executor agent.")
    parser.add_argument("--executor-model", type=str, help="Model for the executor agent.")
    parser.add_argument("--executor-flash-model", type=str, help="Flash model for the executor agent.")
    parser.add_argument("--qa-provider", type=str, choices=["gemini", "openai", "ollama"], help="Provider for the QA agent.")
    parser.add_argument("--qa-model", type=str, help="Model for the QA agent.")
    
    parser.add_argument("--auto-commit", action="store_true", default=None, help="Auto-commit successful tasks.")
    parser.add_argument("--budget-limit", type=float, help="Maximum budget in USD.")
    parser.add_argument("--max-duration", type=int, default=7200, help="Maximum run duration in seconds (default 2 hours = 7200s)")
    parser.add_argument("--spec", type=str, help="Path to a specification file to provide as context.")
    parser.add_argument("--run-id", type=str, help="Run ID to resume.")
    parser.add_argument("--resume", action="store_true", help="Resume the latest run.")
    parser.add_argument("--list-checkpoints", action="store_true", help="List available checkpoints.")
    
    # Logging options
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Set log level.")
    parser.add_argument("--log-file", type=str, help="Path to a file for structured logging.")
    parser.add_argument("--json-logs", action="store_true", help="Output logs in JSON format to console.")
    
    # Dashboard options
    parser.add_argument("--dashboard", action="store_true", help="Start the web-based monitoring dashboard.")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host for the dashboard server.")
    parser.add_argument("--port", type=int, default=8000, help="Port for the dashboard server.")
    
    # Workflow options
    parser.add_argument("--template", type=str, help="Use a pre-defined workflow template.")
    parser.add_argument("--list-templates", action="store_true", help="List available workflow templates.")
    
    args = parser.parse_args()
    
    # Initialize Logging
    console_format = "json" if args.json_logs else "rich"
    setup_logging(log_level=args.log_level, log_file=args.log_file, console_format=console_format)
    setup_tracing()
    
    if args.dashboard:
        from .web.server import start_server
        console.print(f"[bold green]Starting dashboard at http://{args.host}:{args.port}[/bold green]")
        start_server(host=args.host, port=args.port)
        return
        
    if args.list_templates:
        templates = list_templates()
        if not templates:
            console.print("No templates found.")
        else:
            console.print("[bold]Available Templates:[/bold]")
            for t in templates:
                console.print(f"- {t}")
        return

    if args.list_checkpoints:
        checkpoints = RunCheckpoint.list_checkpoints()
        if not checkpoints:
            console.print("No checkpoints found.")
        else:
            console.print("[bold]Available Checkpoints:[/bold]")
            for cp in checkpoints:
                console.print(f"- [cyan]{cp['run_id']}[/cyan]: {cp['goal']} ({cp['tasks_completed']} tasks completed, last updated: {cp['last_updated']})")
        return

    run_id = args.run_id
    if args.resume and not run_id:
        checkpoints = RunCheckpoint.list_checkpoints()
        if checkpoints:
            run_id = checkpoints[0]["run_id"]
            console.print(f"[dim]Automatically selected latest checkpoint: {run_id}[/dim]")
        else:
            console.print("[bold red]Error:[/bold red] No checkpoints found to resume.")
            sys.exit(1)

    goal = args.goal
    if run_id and not goal:
        checkpoint = RunCheckpoint.load(run_id)
        if checkpoint:
            goal = checkpoint.goal
        else:
             console.print(f"[bold red]Error:[/bold red] Checkpoint {run_id} not found.")
             sys.exit(1)

    if args.template:
        template = get_template(args.template)
        if template:
            goal = f"Workflow: {template.name} - {template.description}"
            console.print(f"[bold blue]Using template: {template.name}[/bold blue]")
        else:
            console.print(f"[bold red]Error:[/bold red] Template {args.template} not found.")
            sys.exit(1)

    if not goal:
        parser.print_help()
        sys.exit(0)

    # Load config file
    config = load_config(args.config)
    
    # Create Agents
    planner = create_agent(config.planner, mcp_servers=config.mcp_servers)
    executor = create_agent(config.executor, mcp_servers=config.mcp_servers)
    
    qa_agent = None
    if args.qa_provider or args.qa_model:
        qa_config = AgentConfig(
            provider=args.qa_provider or config.planner.provider,
            model=args.qa_model or config.planner.model
        )
        qa_agent = create_agent(qa_config)

    auto_commit = args.auto_commit if args.auto_commit is not None else config.auto_commit
    budget_limit = args.budget_limit if args.budget_limit is not None else config.budget_limit
    max_run_duration = args.max_duration or 7200

    orchestrator = Orchestrator(
        planner=planner, 
        executor=executor, 
        qa_agent=qa_agent,
        auto_commit=auto_commit, 
        budget_limit=budget_limit, 
        run_id=run_id, 
        max_run_duration=max_run_duration
    )
    
    if args.template:
        template = get_template(args.template)
        orchestrator.tasks_by_goal[goal] = template.tasks

    # Load spec context if provided
    spec_context = ""
    if args.spec:
        try:
            with open(args.spec, "r") as f:
                spec_context = f"SPECIFICATION FROM {args.spec}:\n\n{f.read()}"
            console.print(f"[dim]Loaded spec from {args.spec}[/dim]")
        except Exception as e:
            console.print(f"[bold red]Error loading spec {args.spec}: {e}[/bold red]")

    try:
        asyncio.run(run_async(orchestrator, goal, spec_context))
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Run interrupted by user. State saved.[/bold yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]Error during run: {e}[/bold red]")
        sys.exit(1)

if __name__ == "__main__":
    main()
