from typing import Dict, Any, List
import subprocess
from rich.console import Console
from .agent import BaseAgent, AgentTask, AgentResult
from .gemini_agent import GeminiAgent
from .utils import git_commit, get_repo_map, is_git_repo, should_include_repo_map

console = Console()

class Orchestrator:
    def __init__(self, planner: BaseAgent, executor: Optional[BaseAgent] = None, auto_commit: bool = True):
        self.planner = planner
        self.executor = executor or planner
        self.agents: Dict[str, BaseAgent] = {}
        self.auto_commit = auto_commit
        self._cached_repo_map = None

    def register_agent(self, name: str, agent: BaseAgent):
        self.agents[name] = agent

    def _get_repo_map(self) -> str:
        if self._cached_repo_map is None:
            self._cached_repo_map = get_repo_map()
        return self._cached_repo_map

    def run_goal(self, goal: str, context: str = ""):
        console.print(f"\n[bold blue]>>> Orchestrating goal: {goal}[/bold blue]")
        
        # 1. Classify the goal
        is_simple = False
        if hasattr(self.planner, 'classify_goal'):
            classification = self.planner.classify_goal(goal)
            is_simple = (classification == "simple")
            console.print(f"[dim]Goal classified as: {classification}[/dim]")
        
        # 2. Build context lazily
        full_context = context
        if should_include_repo_map(goal):
            repo_map = self._get_repo_map()
            full_context = f"{full_context}\nProject Structure:\n{repo_map}"
            console.print(f"[dim]Included repo map in context.[/dim]")
        
        self.planner.receive_context(full_context)
        self.executor.receive_context(full_context)

        # 3. Plan or Direct Execution
        if is_simple:
            tasks = [AgentTask(id="direct_task", description=goal, agent_type="executor")]
            console.print(f"[dim]Executing simple goal directly.[/dim]")
        else:
            if hasattr(self.planner, 'decompose_goal'):
                tasks = self.planner.decompose_goal(goal)
            else:
                tasks = [AgentTask(id="fallback_task", description=goal, agent_type="executor")]
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
            # Step 1: Execute using the executor agent
            result = self.executor.execute_task(task)
            
            if not result.success:
                console.print(f"  [bold red]Execution Error:[/bold red] {result.error}")
                task.retry_count += 1
                continue
            
            # Step 2: Verify
            if task.verification_command:
                console.print(f"  [dim]Verifying with: {task.verification_command}[/dim]")
                verify_result = subprocess.run(
                    task.verification_command,
                    shell=True,
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
                    # Pass the error back to the task context for the next attempt
                    error_msg = verify_result.stderr or verify_result.stdout
                    task.context = f"{task.context or ''}\nPrevious attempt failed with error:\n{error_msg}"
            else:
                # No verification command, assume success if execution was successful
                if result.output and result.output != "Task completed.":
                    console.print(f"  [green]Result:[/green] {result.output}")
                if self.auto_commit and is_git_repo():
                    commit_msg = f"Task {task.id}: {task.description}"
                    commit_res = git_commit(commit_msg)
                    console.print(f"  [dim]{commit_res}[/dim]")
                return

        console.print(f"  [bold red]Task failed after {task.max_retries + 1} attempts.[/bold red]")
