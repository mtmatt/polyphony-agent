import argparse
import sys
from rich.console import Console
from .gemini_agent import GeminiAgent
from .engine import Orchestrator

console = Console()

def main():
    parser = argparse.ArgumentParser(description="Polyphony Agent CLI")
    parser.add_argument("goal", type=str, help="The goal you want the agent to achieve.")
    parser.add_argument("--model", type=str, default="gemini-2.0-flash-exp", help="The model to use for planning.")
    parser.add_argument("--auto-commit", action="store_true", help="Automatically commit changes to Git after successful tasks.")
    
    args = parser.parse_args()
    
    # We use GeminiAgent which can handle both planning and execution.
    planner = GeminiAgent(model_name=args.model)
    orchestrator = Orchestrator(planner=planner, auto_commit=args.auto_commit)
    
    try:
        # Wrap everything in a nice rich print handled inside engine.py
        orchestrator.run_goal(args.goal)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
