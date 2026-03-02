from typing import Dict, Any, List, Optional
import subprocess
import time
import asyncio
import concurrent.futures
import uuid
import os
from datetime import datetime
from threading import Lock
from enum import Enum
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from .agent import BaseAgent, AgentTask, AgentResult
from .gemini_agent import GeminiAgent
from .run_summary import RunSummary
from .utils import get_repo_map, is_git_repo, should_include_repo_map, extract_relevant_dirs
from .checkpoint import RunCheckpoint

console = Console()

class ErrorCategory(str, Enum):
    SYNTAX = "SYNTAX_ERROR"
    IMPORT = "IMPORT_ERROR"
    TEST = "TEST_FAILURE"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    DISK_FULL = "DISK_FULL"
    TIMEOUT = "TIMEOUT"
    PERMISSION = "PERMISSION_DENIED"
    API_ERROR = "API_ERROR"
    UNKNOWN = "UNKNOWN"

class DependencyResolver:
    """Groups tasks into batches that can be executed in parallel."""
    @staticmethod
    def resolve(tasks: List[AgentTask]) -> List[List[AgentTask]]:
        """
        Resolves the dependency graph and returns a list of batches.
        Each batch contains tasks that can be executed in parallel.
        """
        batches = []
        pending_tasks = {t.id: t for t in tasks}
        completed_ids = set()

        while pending_tasks:
            current_batch = []
            for tid, task in list(pending_tasks.items()):
                # Check if all dependencies (both field names) are met
                deps = set(task.depends_on) | set(task.dependencies)
                if all(dep in completed_ids for dep in deps):
                    current_batch.append(task)
            
            if not current_batch:
                # Circular dependency or missing dependency
                remaining = list(pending_tasks.keys())
                raise ValueError(f"Circular dependency detected or unmet dependencies: {remaining}")
            
            batches.append(current_batch)
            for task in current_batch:
                completed_ids.add(task.id)
                del pending_tasks[task.id]
        
        return batches

from .cost import CostTracker

class Orchestrator:
    def __init__(self, planner: BaseAgent, executor: Optional[BaseAgent] = None, auto_commit: bool = True, parallel: bool = False, budget_limit: float = 0.0, run_id: Optional[str] = None, checkpoint_dir: str = ".polyphony/checkpoints", max_run_duration: int = 7200):
        self.planner = planner
        self.executor = executor or planner
        self.agents: Dict[str, BaseAgent] = {
            "planner": self.planner,
            "executor": self.executor
        }
        self.auto_commit = auto_commit
        self.parallel = parallel
        self.budget_limit = budget_limit
        self.max_run_duration = max_run_duration  # Default 2 hours (7200 seconds)
        self.total_cost_tracker = CostTracker()
        self.run_summary = None
        self._lock = Lock()
        self.run_id = run_id or str(uuid.uuid4())[:8]
        self.checkpoint_dir = checkpoint_dir
        self.start_time = datetime.now()
        self.tasks_by_goal: Dict[str, List[AgentTask]] = {}
        self.is_simple = False
        self._is_resumed = False
        self.goal = None
        self.context = None

    def register_agent(self, name: str, agent: BaseAgent):
        self.agents[name] = agent

    def _save_checkpoint(self):
        """Saves the current state to a checkpoint file."""
        if not self.goal:
            return

        with self._lock:
            checkpoint = RunCheckpoint(
                run_id=self.run_id,
                goal=self.goal,
                context=self.context or "",
                tasks_by_goal=self.tasks_by_goal,
                results=self.run_summary.results if self.run_summary else [],
                result_tasks=self.run_summary.tasks if self.run_summary else [],
                cost_tracker=self.total_cost_tracker,
                start_time=self.start_time,
                is_simple=self.is_simple,
                last_updated=datetime.now()
            )
            checkpoint.save(self.checkpoint_dir)

    def _check_duration(self):
        """Checks if the max run duration has been exceeded."""
        if self.max_run_duration > 0:
            elapsed = (datetime.now() - self.start_time).total_seconds()
            if elapsed >= self.max_run_duration:
                raise RuntimeError(f"Max run duration ({self.max_run_duration}s) exceeded. Elapsed: {elapsed:.0f}s")
            # Warn at 80% of max duration
            if elapsed >= self.max_run_duration * 0.8:
                remaining = self.max_run_duration - elapsed
                console.print(f"\n[bold yellow]Warning: {remaining:.0f}s remaining in session (of {self.max_run_duration}s max)[/bold yellow]")

    def _get_remaining_duration(self) -> int:
        """Returns the remaining duration in seconds for this session."""
        if self.max_run_duration <= 0:
            return -1
        elapsed = (datetime.now() - self.start_time).total_seconds()
        return max(0, int(self.max_run_duration - elapsed))

    def _check_budget(self):
        """Checks if the budget limit has been reached and raises an error if it has."""
        # Check duration first
        self._check_duration()
        
        if self.budget_limit > 0 and self.total_cost_tracker.total_cost >= self.budget_limit:
            console.print(f"\n[bold red]Budget limit reached: ${self.budget_limit:.4f}[/bold red]")
            raise RuntimeError(f"Budget limit reached: ${self.budget_limit:.4f}")
        
        # Warn at 80%
        if self.budget_limit > 0 and self.total_cost_tracker.total_cost >= self.budget_limit * 0.8:
            console.print(f"\n[bold yellow]Warning: Budget usage at {self.total_cost_tracker.total_cost / self.budget_limit:.1%}[/bold yellow]")

    def _sync_usage(self):
        """Syncs usage from all agents to the current run summary and total cost tracker."""
        for agent in self.agents.values():
            for model, usage in list(agent.usage_by_model.items()):
                if self.run_summary:
                    self.run_summary.cost_tracker.add_usage(
                        model, usage.prompt_tokens, usage.completion_tokens
                    )
                self.total_cost_tracker.add_usage(
                    model, usage.prompt_tokens, usage.completion_tokens
                )
                # Clear agent's usage so it's not double-counted
                agent.usage_by_model = {}
        self._check_budget()

    def _get_repo_map(self, goal: Optional[str] = None) -> str:
        include_only = None
        if goal:
            include_only = extract_relevant_dirs(goal)
            if include_only:
                console.print(f"[dim]Filtering repo map for: {', '.join(include_only)}[/dim]")
        
        return get_repo_map(include_only=include_only)

    async def run_goal(self, goal: str, context: str = ""):
        self._check_budget()
        is_root = False
        
        # Check if we should resume
        if self.run_summary is None:
            is_root = True
            checkpoint = RunCheckpoint.load(self.run_id, self.checkpoint_dir)
            if checkpoint:
                console.print(f"[bold green]Resuming run from checkpoint: {self.run_id}[/bold green]")
                self.run_summary = RunSummary(checkpoint.goal)
                self.run_summary.start_time = checkpoint.start_time
                self.tasks_by_goal = checkpoint.tasks_by_goal
                self.total_cost_tracker = checkpoint.cost_tracker
                self.is_simple = checkpoint.is_simple
                for task, result in zip(checkpoint.result_tasks, checkpoint.results):
                    self.run_summary.add_result(task, result)
                self._is_resumed = True
                self.goal = checkpoint.goal
                self.context = checkpoint.context
                goal = checkpoint.goal
                context = checkpoint.context
            else:
                self.run_summary = RunSummary(goal)
                self.goal = goal
                self.context = context

        console.print(f"\n[bold blue]>>> Orchestrating goal: {goal} (Run ID: {self.run_id})[/bold blue]")
        
        # Check if we have tasks for this goal (already planned/decomposed)
        tasks = self.tasks_by_goal.get(goal)
        
        # 1. Classify the goal (Skip if resumed or already have tasks)
        if tasks is None and not self._is_resumed:
            if hasattr(self.planner, 'classify_goal'):
                classification = await asyncio.to_thread(self.planner.classify_goal, goal)
                self.is_simple = (classification == "simple")
                console.print(f"[dim]Goal classified as: {classification}[/dim]")
                self._sync_usage()
            else:
                self.is_simple = False
        
        # Multi-model support: select model based on complexity
        original_models = {name: agent.model_name for name, agent in self.agents.items()}
        try:
            for name, agent in self.agents.items():
                if self.is_simple and agent.flash_model_name:
                    agent.model_name = agent.flash_model_name
                    console.print(f"[dim]Switching {name} to flash model: {agent.model_name}[/dim]")
                else:
                    agent.model_name = agent.pro_model_name
                    # Only print if it's different from the flash model to avoid noise
                    if agent.flash_model_name:
                         console.print(f"[dim]Using {name} pro model: {agent.model_name}[/dim]")
            
            # 2. Build context lazily
            full_context = context
            if should_include_repo_map(goal):
                repo_map = self._get_repo_map(goal)
                full_context = f"{full_context}\nProject Structure:\n{repo_map}"
                console.print(f"[dim]Included repo map in context.[/dim]")
            
            for agent in self.agents.values():
                agent.receive_context(full_context)

            # 3. Plan or Direct Execution
            if tasks is None:
                if self.is_simple:
                    tasks = [AgentTask(id="direct_task", description=goal, agent_type="executor")]
                    console.print(f"[dim]Executing simple goal directly.[/dim]")
                else:
                    if hasattr(self.planner, 'decompose_goal'):
                        tasks = await asyncio.to_thread(self.planner.decompose_goal, goal)
                        self._sync_usage()
                    else:
                        tasks = [AgentTask(id="fallback_task", description=goal, agent_type="executor")]
                    console.print(f"[dim]Decomposed into {len(tasks)} tasks.[/dim]")
                
                self.tasks_by_goal[goal] = tasks
                
                # Save initial checkpoint
                self._save_checkpoint()
            
            # 4. Filter out completed tasks
            remaining_tasks = [t for t in tasks if t.status != "completed"]
            
            if len(remaining_tasks) < len(tasks):
                console.print(f"[dim]Skipping {len(tasks) - len(remaining_tasks)} completed tasks for this goal.[/dim]")
            
            if not remaining_tasks:
                console.print(f"[bold green]All tasks for this goal already completed.[/bold green]")
                return

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
                # Advance for completed tasks
                progress.advance(global_task, len(tasks) - len(remaining_tasks))
                
                if self.parallel and len(remaining_tasks) > 1:
                    console.print(f"[dim]Executing tasks in parallel (Max 4 workers).[/dim]")
                    await self._execute_parallel(remaining_tasks, progress, global_task)
                else:
                    task_layer = progress.add_task("[cyan]Current Task Progress", total=100)
                    for task in remaining_tasks:
                        await self.execute_with_verification(task, progress, global_task, task_layer)
                        progress.advance(global_task)
                        # Save checkpoint after each task
                        self._save_checkpoint()
        finally:
            # Restore models
            for name, model in original_models.items():
                self.agents[name].model_name = model

            # Final sync and budget check for this level
            self._sync_usage()
            
            # Save checkpoint when leaving run_goal level
            self._save_checkpoint()
        
        # Only finalize if this is the root goal
        if is_root:
            # Save final checkpoint before summary
            self._save_checkpoint()
            
            # Finalize and report summary
            summary_path = self.run_summary.save()
            console.print(f"\n[bold green]Goal execution complete![/bold green]")
            console.print(f"[bold cyan]Run Summary:[/bold cyan] {summary_path}")
            
            # Show brief summary
            total = len(self.run_summary.tasks)
            successful = sum(1 for r in self.run_summary.results if r.success)
            if successful == total and total > 0:
                console.print(f"[green][OK] All {total} task(s) completed successfully[/green]")
                console.print(f"[dim]Total Cost: ${self.run_summary.cost_tracker.total_cost:.4f}[/dim]")
                console.print(f"[dim]Documentation updated in GEMINI.md and README.md[/dim]")
            else:
                console.print(f"[yellow][WARNING] {successful}/{total} task(s) completed[/yellow]")
                console.print(f"[dim]Total Cost so far: ${self.run_summary.cost_tracker.total_cost:.4f}[/dim]")
            
            # Remove checkpoint after successful completion?
            # Or keep it for history. Let's keep it for now.

    async def _execute_parallel(self, tasks: List[AgentTask], progress: Progress, global_task):
        """
        Executes tasks in parallel while respecting dependencies by grouping them into batches.
        Uses asyncio.gather for processing batches of independent tasks with a concurrency limit.
        """
        try:
            batches = DependencyResolver.resolve(tasks)
        except ValueError as e:
            console.print(f"[bold red]Planning Error: {e}[/bold red]")
            return

        semaphore = asyncio.Semaphore(4)
        failed_tasks = set()
        task_map = {t.id: t for t in tasks}

        for batch in batches:
            async def run_task(task):
                async with semaphore:
                    # Check if any dependencies failed
                    deps = set(task.depends_on) | set(task.dependencies)
                    failed_deps = [dep for dep in deps if task_map.get(dep) and task_map[dep].status == "failed"]
                    
                    if failed_deps:
                        console.print(f"[yellow]Skipping task {task.id} because dependencies failed: {', '.join(failed_deps)}[/yellow]")
                        task.status = "failed"
                        failed_tasks.add(task.id)
                        progress.advance(global_task)
                        return

                    # Add a progress layer for this specific task
                    layer = progress.add_task(f"[cyan]Task: {task.id}", total=100)
                    try:
                        await self.execute_with_verification(task, progress, global_task, layer)
                        if task.status != "completed":
                            failed_tasks.add(task.id)
                        # Save checkpoint after each task in parallel too
                        self._save_checkpoint()
                    except Exception as e:
                        console.print(f"[bold red]Task {task.id} failed with critical exception: {e}[/bold red]")
                        task.status = "failed"
                        failed_tasks.add(task.id)
                    finally:
                        # Cleanup the progress layer
                        progress.remove_task(layer)
                        progress.advance(global_task)

            # asyncio.gather allows parallel execution of all tasks in the current batch
            await asyncio.gather(*(run_task(task) for task in batch))
        
        if failed_tasks:
            console.print(f"[bold yellow]Parallel execution finished with some failures: {', '.join(list(failed_tasks))}[/bold yellow]")

    def _get_history_context(self) -> str:
        """Aggregates results of completed tasks into a context string."""
        if not self.run_summary or not self.run_summary.results:
            return ""
        
        history_parts = ["\n[COMPLETED TASKS HISTORY]"]
        # Only include successful results
        for res in self.run_summary.results:
            if res.success:
                part = f"Task: {res.task_id}\nResult: {res.output}"
                if res.files_changed:
                    part += f"\nFiles modified: {', '.join(res.files_changed)}"
                history_parts.append(part)
        
        if len(history_parts) == 1: # Only header
            return ""
            
        return "\n---\n".join(history_parts)

    async def execute_with_verification(self, task: AgentTask, progress: Progress, global_task, task_layer):
        """
        Executes a task and verifies it using a verification command if provided.
        """
        # If the task was previously failed, reset its retry count on resume
        if self._is_resumed and task.status == "failed":
            task.retry_count = 0
            
        task.status = "in-progress"
        self._save_checkpoint()
        progress.update(task_layer, completed=0, description=f"[cyan]Executing: {task.id}")
        
        # Recursive check: if the task needs more planning
        if task.agent_type == 'planner':
            progress.update(task_layer, completed=50, description=f"[cyan]Recursing: {task.id}")
            # Add historical context to recursive goal
            history = self._get_history_context()
            await self.run_goal(task.description, context=f"{task.context or ''}\n{history}")
            task.status = "completed"
            progress.update(task_layer, completed=100)
            return

        # Multi-model support: select agent based on task.agent_type
        agent = self.agents.get(task.agent_type, self.executor)

        # Dynamic model switching based on task complexity
        original_model = agent.model_name
        if task.complexity == "simple" and agent.flash_model_name:
            agent.model_name = agent.flash_model_name
        elif task.complexity == "complex":
            agent.model_name = agent.pro_model_name
        
        from .utils import git_get_modified_files, git_commit

        try:
            while task.retry_count <= task.max_retries:
                # Step 1: Execute using the selected agent
                # Model Fallback: If it's a retry and we're not already on the pro model, switch to pro
                if task.retry_count > 0 and agent.flash_model_name and agent.model_name == agent.flash_model_name:
                    agent.model_name = agent.pro_model_name
                    console.print(f"  [dim]Retry {task.retry_count}: Falling back to pro model {agent.model_name}[/dim]")

                progress.update(task_layer, completed=10, description=f"[cyan]Agent Thinking ({agent.model_name}): {task.id}")
                
                # Enrich task context with history of previous tasks
                history = self._get_history_context()
                original_task_context = task.context
                if history:
                    # Temporary update context for this attempt
                    task.context = f"{original_task_context or ''}\n{history}"

                start_time = time.time()
                # Wrap blocking execution in a thread
                try:
                    result = await asyncio.to_thread(agent.execute_task, task, lambda p: progress.update(task_layer, completed=p))
                except Exception as e:
                    # Handle agent-level exceptions (e.g., API errors, subprocess failures)
                    result = AgentResult(
                        task_id=task.id,
                        success=False,
                        error=str(e),
                        agent_model=agent.model_name
                    )

                # Restore original task context
                task.context = original_task_context
                result.duration = time.time() - (result.duration or start_time)
                
                result.agent_model = result.agent_model or getattr(agent, "model_name", "unknown")
                
                # Sync usage and check budget
                self._sync_usage()
                
                progress.update(task_layer, completed=50, description=f"[cyan]Executing: {task.id}")
                
                # Capture modified files before commit
                if is_git_repo():
                    result.files_changed = await asyncio.to_thread(git_get_modified_files)

                if not result.success:
                    task.retry_count += 1
                    self.run_summary.add_result(task, result)
                    # Smarter context update for retry
                    category = self._categorize_error(result.error or "")
                    task.context = f"{task.context or ''}\nPrevious attempt failed with {category.value}: {result.error}"
                    continue
                
                # Step 2: Verify
                if task.verification_command:
                    progress.update(task_layer, completed=75, description=f"[cyan]Verifying: {task.id}")
                    try:
                        verify_result = await asyncio.to_thread(
                            subprocess.run,
                            task.verification_command,
                            shell=True,
                            capture_output=True,
                            text=True,
                            timeout=60 # Add a timeout for safety
                        )
                        
                        result.verification_output = f"Command: {task.verification_command}\nStdout:\n{verify_result.stdout}\nStderr:\n{verify_result.stderr}"
                        return_code = verify_result.returncode
                    except subprocess.TimeoutExpired:
                        result.verification_output = f"Command: {task.verification_command}\nError: Verification timed out after 60 seconds."
                        return_code = 1
                    except Exception as e:
                        result.verification_output = f"Command: {task.verification_command}\nError: {str(e)}"
                        return_code = 1
                    
                    if return_code == 0:
                        # Step 3: Git Commit (Optional)
                        if self.auto_commit and is_git_repo():
                            progress.update(task_layer, completed=90, description=f"[cyan]Committing: {task.id}")
                            commit_msg = await asyncio.to_thread(agent.generate_commit_message, result)
                            self._sync_usage()
                            git_res_dict = await asyncio.to_thread(git_commit, commit_msg)
                            if git_res_dict.get("success"):
                                result.commit_hash = git_res_dict.get("commit_hash")
                                console.print(f"  [dim][git][/dim] {git_res_dict.get('message')}")
                            else:
                                console.print(f"  [dim][git][/dim] [red]{git_res_dict.get('message')}[/red]")
                        
                        self.run_summary.add_result(task, result)
                        task.status = "completed"
                        progress.update(task_layer, completed=100, description=f"[cyan]Done: {task.id}")
                        return
                    else:
                        task.retry_count += 1
                        reflection_prompt = self._generate_reflection_prompt(task, result)
                        task.context = f"{task.context or ''}\n{reflection_prompt}"
                        
                        console.print(f"  [yellow]Verification failed for {task.id} ({task.retry_count}/{task.max_retries + 1}). Retrying...[/yellow]")
                        self.run_summary.add_result(task, result)
                else:
                    # No verification command, assume success if execution was successful
                    if self.auto_commit and is_git_repo():
                        progress.update(task_layer, completed=90, description=f"[cyan]Committing: {task.id}")
                        commit_msg = await asyncio.to_thread(agent.generate_commit_message, result)
                        self._sync_usage()
                        git_res_dict = await asyncio.to_thread(git_commit, commit_msg)
                        if git_res_dict.get("success"):
                            result.commit_hash = git_res_dict.get("commit_hash")
                            console.print(f"  [dim][git][/dim] {git_res_dict.get('message')}")
                        else:
                            console.print(f"  [dim][git][/dim] [red]{git_res_dict.get('message')}[/red]")
                    
                    self.run_summary.add_result(task, result)
                    task.status = "completed"
                    progress.update(task_layer, completed=100, description=f"[cyan]Done: {task.id}")
                    return
        finally:
            # Restore original model
            agent.model_name = original_model

        task.status = "failed"
        progress.update(task_layer, completed=100, description=f"[bold red]Failed: {task.id}")

    def _categorize_error(self, output: str) -> ErrorCategory:
        """Categorizes an error based on its output."""
        if "SyntaxError" in output or "IndentationError" in output:
            return ErrorCategory.SYNTAX
        elif "ModuleNotFoundError" in output or "ImportError" in output:
            return ErrorCategory.IMPORT
        elif "AssertionError" in output or "FAILED" in output or "E       " in output:
            return ErrorCategory.TEST
        elif "FileNotFoundError" in output or "No such file or directory" in output:
            return ErrorCategory.FILE_NOT_FOUND
        elif "ENOSPC" in output or "Disk full" in output or "No space left on device" in output:
            return ErrorCategory.DISK_FULL
        elif "Timeout" in output or "timed out" in output:
            return ErrorCategory.TIMEOUT
        elif "Permission denied" in output or "EACCES" in output:
            return ErrorCategory.PERMISSION
        elif "API key" in output or "quota exceeded" in output or "rate limit" in output:
            return ErrorCategory.API_ERROR
        return ErrorCategory.UNKNOWN

    def _generate_reflection_prompt(self, task: AgentTask, result: AgentResult) -> str:
        """
        Generates a dedicated reflection prompt for verification failure.
        Includes error categorization and potential fix strategies.
        """
        output = result.verification_output or ""
        category = self._categorize_error(output)
        
        strategies = {
            ErrorCategory.SYNTAX: "Fix the syntax or indentation errors identified in the output.",
            ErrorCategory.IMPORT: "Check your imports and ensure all necessary dependencies are installed or created. If you are missing a local file, ensure it was created in the correct location.",
            ErrorCategory.TEST: "Review the test assertions and your implementation. The logic does not match the expected behavior.",
            ErrorCategory.FILE_NOT_FOUND: "Ensure that all files you intended to create or modify were actually written to the correct location.",
            ErrorCategory.DISK_FULL: "The disk is full or there are no more inodes. Check your disk space and quota.",
            ErrorCategory.TIMEOUT: "Consider if your implementation is efficient or if the verification command needs more time.",
            ErrorCategory.PERMISSION: "The process lacks necessary permissions to access a file or resource.",
            ErrorCategory.API_ERROR: "The LLM API returned an error, possibly due to quota or credentials.",
            ErrorCategory.UNKNOWN: "Analyze the full output to determine the root cause."
        }
        
        strategy = strategies.get(category, strategies[ErrorCategory.UNKNOWN])

        return (
            f"\n--- REFLECTION ---\n"
            f"Your previous attempt to perform task '{task.id}' failed verification.\n"
            f"Task Description: {task.description}\n"
            f"Verification Command: {task.verification_command}\n"
            f"Error Category: {category.value}\n"
            f"Suggested Strategy: {strategy}\n\n"
            f"Verification Output:\n{output}\n\n"
            f"Please:\n"
            f"1. Analyze the verification output to understand exactly what went wrong.\n"
            f"2. Reflect on your previous approach and identify the flaw.\n"
            f"3. Formulate a corrected plan and execute it using your tools.\n"
            f"4. Ensure the task is fully completed and matches all requirements.\n"
            f"--- END REFLECTION ---\n"
        )
