import argparse
import sys
import os
from rich.console import Console
from .gemini_agent import GeminiAgent
from .openai_agent import OpenAIAgent
from .engine import Orchestrator
from .config import load_config, AgentConfig, Config

console = Console()

def create_agent(agent_config: AgentConfig):
    # If the provider is 'openai' or any other name but has a base_url, we treat it as OpenAI-compatible
    if agent_config.provider == "gemini":
        model = agent_config.model or "gemini-3-flash-preview"
        return GeminiAgent(model_name=model)
    elif agent_config.provider == "openai" or agent_config.base_url:
        model = agent_config.model or "gpt-4o"
        return OpenAIAgent(model_name=model, base_url=agent_config.base_url, api_key=agent_config.api_key)
    else:
        # Fallback to gemini if provider is unknown but no base_url
        console.print(f"[yellow]Warning:[/yellow] Unknown provider '{agent_config.provider}'. Defaulting to Gemini.")
        return GeminiAgent(model_name="gemini-3-flash-preview")

def main():
    parser = argparse.ArgumentParser(description="Polyphony Agent CLI")
    parser.add_argument("goal", type=str, nargs="?", help="The goal you want the agent to achieve.")
    parser.add_argument("--config", type=str, default="polyphony.toml", help="Path to the configuration file.")
    
    # Simple flags (override both or default)
    parser.add_argument("--provider", type=str, help="Default AI provider.")
    parser.add_argument("--model", type=str, help="Default model.")
    parser.add_argument("--base-url", type=str, help="Default base URL.")
    parser.add_argument("--api-key", type=str, help="Default API key.")
    
    # Planner specific flags
    parser.add_argument("--planner-provider", type=str, help="AI provider for planning.")
    parser.add_argument("--planner-model", type=str, help="Model for planning.")
    
    # Executor specific flags
    parser.add_argument("--executor-provider", type=str, help="AI provider for execution.")
    parser.add_argument("--executor-model", type=str, help="Model for execution.")
    
    parser.add_argument("--auto-commit", action="store_true", default=None, help="Auto-commit successful tasks.")
    parser.add_argument("--spec", type=str, help="Path to a specification file to provide as context.")
    
    args = parser.parse_args()
    
    if not args.goal:
        parser.print_help()
        sys.exit(0)

    # Load config file
    config = load_config(args.config)
    
    # Merge Planner Config
    planner_config = config.planner
    planner_config.provider = args.planner_provider or args.provider or planner_config.provider
    planner_config.model = args.planner_model or args.model or planner_config.model
    planner_config.base_url = args.base_url or planner_config.base_url
    planner_config.api_key = args.api_key or planner_config.api_key or os.environ.get("OPENAI_API_KEY")

    # Merge Executor Config
    executor_config = config.executor
    executor_config.provider = args.executor_provider or args.provider or executor_config.provider
    executor_config.model = args.executor_model or args.model or executor_config.model
    executor_config.base_url = args.base_url or executor_config.base_url
    executor_config.api_key = args.api_key or executor_config.api_key or os.environ.get("OPENAI_API_KEY")

    auto_commit = args.auto_commit if args.auto_commit is not None else config.auto_commit

    # Create Agents
    planner = create_agent(planner_config)
    executor = create_agent(executor_config)

    orchestrator = Orchestrator(planner=planner, executor=executor, auto_commit=auto_commit)
    
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
        orchestrator.run_goal(args.goal, context=spec_context)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
