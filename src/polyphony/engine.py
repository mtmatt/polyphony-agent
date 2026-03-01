from typing import Dict, Any, List, Optional
import subprocess
import time
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from .agent import BaseAgent, AgentTask, AgentResult
from .gemini_agent import GeminiAgent
from .utils import git_commit, get_repo_map, is_git_repo, should_include_repo_map
from .run_summary import RunSummary

console = Console()

class Orchestrator:
    def __init__(self, planner: BaseAgent, executor: Optional[BaseAgent] = None, auto_commit: bool = True):
        self.planner = planner
        self.executor = executor or planner
        self.agents: Dict[str, BaseAgent] = {
            "planner": self.planner,
            "executor": self.executor
        }
        self.auto_commit = auto_commit
        self._cached_repo_map = None
        self.run_summary = None

    def register_agent(self, name: str, agent: BaseAgent):
        self.agents[name] = agent

    def _get_repo_map(self) -> str:
        if self._cached_repo_map is None:
            self._cached_repo_map = get_repo_map()
        return self._cached_repo_map

    def run_goal(self, goal: str, context: str = ""):
        self.run_summary = RunSummary(goal)
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
        
        for agent in self.agents.values():
            agent.receive_context(full_context)

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
        
        # 4. Multi-layered progress
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=True
        ) as progress:
            global_task = progress.add_task("[blue]Overall Progress", total=len(tasks))
            task_layer = progress.add_task("[cyan]Current Task Progress", total=100)
            
            for task in tasks:
                self.execute_with_verification(task, progress, global_task, task_layer)
                progress.advance(global_task)
        
        # Finalize and report summary
        summary_path = self.run_summary.save()
        console.print(f"\n[bold green]Goal execution complete![/bold green]")
        console.print(f"[bold cyan]Run Summary Document:[/bold cyan] {summary_path}")

    def execute_with_verification(self, task: AgentTask, progress: Progress, global_task, task_layer):
        """
        Executes a task and verifies it using a verification command if provided.
        """
        progress.update(task_layer, completed=0, description=f"[cyan]Executing: {task.id}")
        
        # Recursive check: if the task needs more planning
        if task.agent_type == 'planner':
            progress.update(task_layer, completed=50, description=f"[cyan]Recursing: {task.id}")
            self.run_goal(task.description, context=task.context or "")
            progress.update(task_layer, completed=100)
            return

        # Multi-model support: select agent based on task.agent_type
        agent = self.agents.get(task.agent_type, self.executor)

        while task.retry_count <= task.max_retries:
            # Step 1: Execute using the selected agent
            progress.update(task_layer, completed=10, description=f"[cyan]Agent Thinking: {task.id}")
            result = agent.execute_task(task, progress=lambda p: progress.update(task_layer, completed=p))
            result.agent_model = getattr(agent, "model_name", "unknown")
            progress.update(task_layer, completed=50, description=f"[cyan]Executing: {task.id}")
            
            if not result.success:
                task.retry_count += 1
                self.run_summary.add_result(task, result)
                # Smarter context update for retry
                task.context = f"{task.context or ''}\nPrevious attempt failed with error: {result.error}"
                continue
            
            # Step 2: Verify
            if task.verification_command:
                progress.update(task_layer, completed=75, description=f"[cyan]Verifying: {task.id}")
                verify_result = subprocess.run(
                    task.verification_command,
                    shell=True,
                    capture_output=True,
                    text=True
                )
                
                result.verification_output = f"Command: {task.verification_command}\nStdout:\n{verify_result.stdout}\nStderr:\n{verify_result.stderr}"
                
                if verify_result.returncode == 0:
                    # Step 3: Git Commit (Optional)
                    if self.auto_commit and is_git_repo():
                        progress.update(task_layer, completed=90, description=f"[cyan]Committing: {task.id}")
                        commit_msg = agent.generate_commit_message(result)
                        git_res = git_commit(commit_msg)
                        if git_res:
                            console.print(f"  [dim][git][/dim] {git_res}")
                    
                    self.run_summary.add_result(task, result)
                    progress.update(task_layer, completed=100, description=f"[cyan]Done: {task.id}")
                    return
                else:
                    task.retry_count += 1
                    error_msg = verify_result.stderr or verify_result.stdout
                    task.context = f"{task.context or ''}\nPrevious attempt failed verification with error:\n{error_msg}"
                    self.run_summary.add_result(task, result)
            else:
                # No verification command, assume success if execution was successful
                if self.auto_commit and is_git_repo():
                    progress.update(task_layer, completed=90, description=f"[cyan]Committing: {task.id}")
                    commit_msg = agent.generate_commit_message(result)
                    git_res = git_commit(commit_msg)
                    if git_res:
                        console.print(f"  [dim][git][/dim] {git_res}")
                
                self.run_summary.add_result(task, result)
                progress.update(task_layer, completed=100, description=f"[cyan]Done: {task.id}")
                return

        progress.update(task_layer, completed=100, description=f"[bold red]Failed: {task.id}")
