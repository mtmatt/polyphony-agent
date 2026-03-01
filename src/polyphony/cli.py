import argparse
import sys
import os
import asyncio
from typing import List, Optional
from rich.console import Console
from .gemini_agent import GeminiAgent
from .openai_agent import OpenAIAgent
from .engine import Orchestrator
from .config import load_config, AgentConfig, Config
from .checkpoint import RunCheckpoint

console = Console()

def create_agent(agent_config: AgentConfig, mcp_servers: Optional[List[MCPServerConfig]] = None):
    # If the provider is 'openai' or any other name but has a base_url, we treat it as OpenAI-compatible
    if agent_config.provider == "gemini":
        model = agent_config.model or "gemini-3-flash-preview"
        return GeminiAgent(model_name=model, flash_model_name=agent_config.flash_model, mcp_servers=mcp_servers)
    elif agent_config.provider == "openai" or agent_config.base_url:
        model = agent_config.model or "gpt-4o"
        return OpenAIAgent(model_name=model, flash_model_name=agent_config.flash_model, base_url=agent_config.base_url, api_key=agent_config.api_key, mcp_servers=mcp_servers)
    else:
        # Fallback to gemini if provider is unknown but no base_url
        console.print(f"[yellow]Warning:[/yellow] Unknown provider '{agent_config.provider}'. Defaulting to Gemini.")
        return GeminiAgent(model_name="gemini-3-flash-preview", flash_model_name=agent_config.flash_model, mcp_servers=mcp_servers)

def main():
    parser = argparse.ArgumentParser(description="Polyphony Agent CLI")
    parser.add_argument("goal", type=str, nargs="?", help="The goal you want the agent to achieve.")
    parser.add_argument("--config", type=str, default="polyphony.toml", help="Path to the configuration file.")
    
    # Simple flags (override both or default)
    parser.add_argument("--provider", type=str, help="Default AI provider.")
    parser.add_argument("--model", type=str, help="Default model.")
    parser.add_argument("--flash-model", type=str, help="Default flash model.")
    parser.add_argument("--base-url", type=str, help="Default base URL.")
    parser.add_argument("--api-key", type=str, help="Default API key.")
    
    # Planner specific flags
    parser.add_argument("--planner-provider", type=str, help="AI provider for planning.")
    parser.add_argument("--planner-model", type=str, help="Model for planning.")
    parser.add_argument("--planner-flash-model", type=str, help="Flash model for planning.")
    
    # Executor specific flags
    parser.add_argument("--executor-provider", type=str, help="AI provider for execution.")
    parser.add_argument("--executor-model", type=str, help="Model for execution.")
    parser.add_argument("--executor-flash-model", type=str, help="Flash model for execution.")
    
    parser.add_argument("--auto-commit", action="store_true", default=None, help="Auto-commit successful tasks.")
    parser.add_argument("--budget-limit", type=float, help="Maximum budget in USD.")
    parser.add_argument("--max-duration", type=int, default=7200, help="Maximum run duration in seconds (default 2 hours = 7200s)")
    parser.add_argument("--spec", type=str, help="Path to a specification file to provide as context.")
    parser.add_argument("--run-id", type=str, help="Run ID to resume.")
    parser.add_argument("--resume", action="store_true", help="Resume the latest run.")
    parser.add_argument("--list-checkpoints", action="store_true", help="List available checkpoints.")
    
    args = parser.parse_args()
    
    if args.list_checkpoints:
        checkpoints = RunCheckpoint.list_checkpoints()
        if not checkpoints:
            console.print("No checkpoints found.")
        else:
            console.print("[bold]Available Checkpoints:[/bold]")
            for cp in checkpoints:
                console.print(f"- [cyan]{cp['run_id']}[/cyan]: {cp['goal']} ({cp['tasks_completed']} tasks completed, last updated: {cp['last_updated']})")
        sys.exit(0)

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
        # Load goal from checkpoint to avoid error
        checkpoint = RunCheckpoint.load(run_id)
        if checkpoint:
            goal = checkpoint.goal
        else:
             console.print(f"[bold red]Error:[/bold red] Checkpoint {run_id} not found.")
             sys.exit(1)

    if not goal:
        parser.print_help()
        sys.exit(0)

    # Load config file
    config = load_config(args.config)
    
    # Merge Planner Config
    planner_config = config.planner
    planner_config.provider = args.planner_provider or args.provider or planner_config.provider
    planner_config.model = args.planner_model or args.model or planner_config.model
    planner_config.flash_model = args.planner_flash_model or args.flash_model or planner_config.flash_model
    planner_config.base_url = args.base_url or planner_config.base_url
    planner_config.api_key = args.api_key or planner_config.api_key or os.environ.get("OPENAI_API_KEY")

    # Merge Executor Config
    executor_config = config.executor
    executor_config.provider = args.executor_provider or args.provider or executor_config.provider
    executor_config.model = args.executor_model or args.model or executor_config.model
    executor_config.flash_model = args.executor_flash_model or args.flash_model or executor_config.flash_model
    executor_config.base_url = args.base_url or executor_config.base_url
    executor_config.api_key = args.api_key or executor_config.api_key or os.environ.get("OPENAI_API_KEY")

    auto_commit = args.auto_commit if args.auto_commit is not None else config.auto_commit
    budget_limit = args.budget_limit if args.budget_limit is not None else config.budget_limit
    max_run_duration = getattr(args, 'max_duration', None) or 7200  # Default 2 hours

    # Create Agents
    planner = create_agent(planner_config, mcp_servers=config.mcp_servers)
    executor = create_agent(executor_config, mcp_servers=config.mcp_servers)

    orchestrator = Orchestrator(planner=planner, executor=executor, auto_commit=auto_commit, budget_limit=budget_limit, run_id=run_id, max_run_duration=max_run_duration)
    
    # Load spec context if provided
    spec_context = ""
    if args.spec:
        try:
            with open(args.spec, "r") as f:
                spec_context = f"SPECIFICATION FROM {args.spec}:\n\n{f.read()}"
            console.print(f"[dim]Loaded spec from {args.spec}[/dim]")
        except Exception as e:
            console.print(f"[bold red]Error loading spec file:[/bold red] {e}")
            sys.exit(1)

    try:
        asyncio.run(orchestrator.run_goal(goal, context=spec_context))
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
