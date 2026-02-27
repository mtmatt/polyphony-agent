from typing import Dict, Any, List
import subprocess
from rich.console import Console
from .agent import BaseAgent, AgentTask, AgentResult
from .gemini_agent import GeminiAgent
from .utils import git_commit, get_repo_map, is_git_repo

console = Console()

class Orchestrator:
    def __init__(self, planner: BaseAgent, auto_commit: bool = True):
        self.planner = planner
        self.agents: Dict[str, BaseAgent] = {}
        self.auto_commit = auto_commit

    def register_agent(self, name: str, agent: BaseAgent):
        self.agents[name] = agent

    def run_goal(self, goal: str, context: str = ""):
        # Generate a repo map for better context
        repo_map = get_repo_map()
        full_context = f"{context}\nProject Structure:\n{repo_map}"
        self.planner.receive_context(full_context)

        console.print(f"\n[bold blue]>>> Orchestrating goal: {goal}[/bold blue]")
        
        # We need to make sure the planner has a decompose_goal method.
        # Since it's not in the BaseAgent interface yet, let's cast or add it.
        # For simplicity, we'll assume the planner passed to Orchestrator has it.
        if hasattr(self.planner, 'decompose_goal'):
            tasks = self.planner.decompose_goal(goal)
        else:
            # Fallback if the agent doesn't support decomposition
            tasks = [AgentTask(id="goal_task", description=goal, agent_type="executor")]
        
        console.print(f"[dim]Decomposed into {len(tasks)} tasks.[/dim]")
        
        for task in tasks:
            self.execute_with_verification(task)

    def execute_with_verification(self, task: AgentTask):
        """
        Executes a task and verifies it using a verification command if provided.
        """
        console.print(f"\n  [bold cyan]--- Task: {task.description} ({task.id}) ---[/bold cyan]")
        
        # Recursive check: if the task needs more planning
        if task.agent_type == 'planner':
            console.print(f"  [dim]Task is complex, recursing...[/dim]")
            self.run_goal(task.description, context=task.context or "")
            return

        while task.retry_count <= task.max_retries:
            # Step 1: Execute
            result = self.planner.execute_task(task)
            
            if not result.success:
                console.print(f"  [bold red]Execution Error:[/bold red] {result.error}")
                task.retry_count += 1
                continue
            
            # Step 2: Verify
            if task.verification_command:
                console.print(f"  [dim]Verifying with: {task.verification_command}[/dim]")
                verify_result = subprocess.run(
                    task.verification_command.split(),
                    capture_output=True,
                    text=True
                )
                
                if verify_result.returncode == 0:
                    console.print(f"  [bold green]Verification successful![/bold green]")
                    # Step 3: Git Commit (Optional)
                    if self.auto_commit and is_git_repo():
                        commit_msg = f"Task {task.id}: {task.description}"
                        commit_res = git_commit(commit_msg)
                        console.print(f"  [dim]{commit_res}[/dim]")
                    return
                else:
                    console.print(f"  [bold yellow]Verification failed (Attempt {task.retry_count+1}/{task.max_retries+1}):[/bold yellow]")
                    console.print(f"  [dim]{verify_result.stdout}\n{verify_result.stderr}[/dim]")
                    task.retry_count += 1
                    # Pass the error back to the planner to "fix" the task
                    task.context = f"Previous attempt failed with error:\n{verify_result.stderr or verify_result.stdout}"
            else:
                # No verification command, assume success if execution was successful
                console.print(f"  [green]Result:[/green] {result.output}")
                if self.auto_commit and is_git_repo():
                    commit_msg = f"Task {task.id}: {task.description}"
                    commit_res = git_commit(commit_msg)
                    console.print(f"  [dim]{commit_res}[/dim]")
                return

        console.print(f"  [bold red]Task failed after {task.max_retries + 1} attempts.[/bold red]")
