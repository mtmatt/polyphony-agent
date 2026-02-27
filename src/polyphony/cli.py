import argparse
import sys
import os
from rich.console import Console
from .gemini_agent import GeminiAgent
from .openai_agent import OpenAIAgent
from .engine import Orchestrator
from .config import load_config

console = Console()

def main():
    parser = argparse.ArgumentParser(description="Polyphony Agent CLI")
    parser.add_argument("goal", type=str, nargs="?", help="The goal you want the agent to achieve.")
    parser.add_argument("--config", type=str, default="polyphony.toml", help="Path to the configuration file.")
    parser.add_argument("--provider", type=str, choices=["gemini", "openai"], help="The AI provider to use.")
    parser.add_argument("--model", type=str, help="The model to use.")
    parser.add_argument("--base-url", type=str, help="The base URL for the API (e.g. for OpenAI-compatible endpoints).")
    parser.add_argument("--api-key", type=str, help="The API key (if needed).")
    parser.add_argument("--auto-commit", action="store_true", default=None, help="Automatically commit changes to Git after successful tasks.")
    
    args = parser.parse_args()
    
    # Load config file (defaults to polyphony.toml if present)
    config = load_config(args.config)
    
    # Merge CLI arguments (take precedence over config file)
    provider = args.provider or config.provider
    model = args.model or config.model
    base_url = args.base_url or config.base_url
    api_key = args.api_key or config.api_key or os.environ.get("OPENAI_API_KEY")
    auto_commit = args.auto_commit if args.auto_commit is not None else config.auto_commit

    if not args.goal:
        parser.print_help()
        sys.exit(0)
    
    if provider == "gemini":
        model = model or "gemini-3-flash-preview"
        planner = GeminiAgent(model_name=model)
    elif provider == "openai":
        model = model or "gpt-4o"
        planner = OpenAIAgent(model_name=model, base_url=base_url, api_key=api_key)
    else:
        console.print(f"[bold red]Error:[/bold red] Unsupported provider: {provider}")
        sys.exit(1)

    orchestrator = Orchestrator(planner=planner, auto_commit=auto_commit)
    
    try:
        orchestrator.run_goal(args.goal)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
