from typing import Dict, Any, List, Optional
import subprocess
import time
import concurrent.futures
from threading import Lock
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from .agent import BaseAgent, AgentTask, AgentResult
from .gemini_agent import GeminiAgent
from .run_summary import RunSummary
from .utils import get_repo_map, is_git_repo, should_include_repo_map, extract_relevant_dirs

console = Console()

class Orchestrator:
    def __init__(self, planner: BaseAgent, executor: Optional[BaseAgent] = None, auto_commit: bool = True, parallel: bool = False):
        self.planner = planner
        self.executor = executor or planner
        self.agents: Dict[str, BaseAgent] = {
            "planner": self.planner,
            "executor": self.executor
        }
        self.auto_commit = auto_commit
        self.parallel = parallel
        self.run_summary = None
        self._lock = Lock()

    def register_agent(self, name: str, agent: BaseAgent):
        self.agents[name] = agent

    def _get_repo_map(self, goal: Optional[str] = None) -> str:
        include_only = None
        if goal:
            include_only = extract_relevant_dirs(goal)
            if include_only:
                console.print(f"[dim]Filtering repo map for: {', '.join(include_only)}[/dim]")
        
        return get_repo_map(include_only=include_only)

    def run_goal(self, goal: str, context: str = ""):
        self.run_summary = RunSummary(goal)
        console.print(f"\n[bold blue]>>> Orchestrating goal: {goal}[/bold blue]")
        
        # 1. Classify the goal
        is_simple = False
        if hasattr(self.planner, 'classify_goal'):
            classification = self.planner.classify_goal(goal)
            is_simple = (classification == "simple")
            console.print(f"[dim]Goal classified as: {classification}[/dim]")
        
        # Multi-model support: select model based on complexity
        original_models = {name: agent.model_name for name, agent in self.agents.items()}
        try:
            for name, agent in self.agents.items():
                if is_simple and agent.flash_model_name:
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
                
                if self.parallel and len(tasks) > 1:
                    console.print(f"[dim]Executing tasks in parallel (Max 4 workers).[/dim]")
                    self._execute_parallel(tasks, progress, global_task)
                else:
                    task_layer = progress.add_task("[cyan]Current Task Progress", total=100)
                    for task in tasks:
                        self.execute_with_verification(task, progress, global_task, task_layer)
                        progress.advance(global_task)
        finally:
            # Restore models
            for name, model in original_models.items():
                self.agents[name].model_name = model
        
        # Finalize and report summary
        summary_path = self.run_summary.save()
        console.print(f"\n[bold green]Goal execution complete![/bold green]")
        console.print(f"[bold cyan]Run Summary Document:[/bold cyan] {summary_path}")

    def _execute_parallel(self, tasks: List[AgentTask], progress: Progress, global_task):
        """
        Executes tasks in parallel while respecting dependencies.
        """
        completed_task_ids = set()
        pending_tasks = {t.id: t for t in tasks}
        running_futures = {}
        
        # Create dedicated task layers for parallel tasks
        active_task_layers = {}
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            while pending_tasks or running_futures:
                # 1. Identify tasks whose dependencies are met
                to_submit = []
                with self._lock:
                    for tid, task in list(pending_tasks.items()):
                        if all(dep in completed_task_ids for dep in task.dependencies):
                            to_submit.append(task)
                            del pending_tasks[tid]
                
                # 2. Submit new tasks
                for task in to_submit:
                    # Add a progress layer for this specific task
                    layer = progress.add_task(f"[cyan]Task: {task.id}", total=100)
                    active_task_layers[task.id] = layer
                    
                    # Wrap execute_with_verification to work in a thread
                    future = executor.submit(
                        self.execute_with_verification, 
                        task, progress, global_task, layer
                    )
                    running_futures[future] = task.id
                
                if not running_futures:
                    if pending_tasks:
                        # Deadlock or circular dependency
                        remaining = [t.id for t in pending_tasks.values()]
                        console.print(f"[bold red]Circular dependency detected or unmet dependencies: {remaining}[/bold red]")
                        break
                    break

                # 3. Wait for at least one task to finish
                done, _ = concurrent.futures.wait(
                    running_futures.keys(), 
                    return_when=concurrent.futures.FIRST_COMPLETED
                )
                
                for future in done:
                    tid = running_futures.pop(future)
                    with self._lock:
                        completed_task_ids.add(tid)
                    
                    # Cleanup the progress layer
                    if tid in active_task_layers:
                        progress.remove_task(active_task_layers[tid])
                    
                    progress.advance(global_task)
                    
                    try:
                        future.result() # Propagate exceptions if any
                    except Exception as e:
                        console.print(f"[bold red]Task {tid} failed with exception: {e}[/bold red]")

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
                progress.update(task_layer, completed=10, description=f"[cyan]Agent Thinking ({agent.model_name}): {task.id}")
                
                start_time = time.time()
                result = agent.execute_task(task, progress=lambda p: progress.update(task_layer, completed=p))
                result.duration = time.time() - start_time
                
                result.agent_model = getattr(agent, "model_name", "unknown")
                progress.update(task_layer, completed=50, description=f"[cyan]Executing: {task.id}")
                
                # Capture modified files before commit
                if is_git_repo():
                    result.files_changed = git_get_modified_files()

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
                            git_res_dict = git_commit(commit_msg)
                            if git_res_dict.get("success"):
                                result.commit_hash = git_res_dict.get("commit_hash")
                                console.print(f"  [dim][git][/dim] {git_res_dict.get('message')}")
                            else:
                                console.print(f"  [dim][git][/dim] [red]{git_res_dict.get('message')}[/red]")
                        
                        self.run_summary.add_result(task, result)
                        progress.update(task_layer, completed=100, description=f"[cyan]Done: {task.id}")
                        return
                    else:
                        task.retry_count += 1
                        reflection_prompt = self._generate_reflection_prompt(task, result)
                        task.context = f"{task.context or ''}\n{reflection_prompt}"
                        
                        console.print(f"  [yellow]Verification failed for {task.id}. Retrying with reflection...[/yellow]")
                        self.run_summary.add_result(task, result)
                else:
                    # No verification command, assume success if execution was successful
                    if self.auto_commit and is_git_repo():
                        progress.update(task_layer, completed=90, description=f"[cyan]Committing: {task.id}")
                        commit_msg = agent.generate_commit_message(result)
                        git_res_dict = git_commit(commit_msg)
                        if git_res_dict.get("success"):
                            result.commit_hash = git_res_dict.get("commit_hash")
                            console.print(f"  [dim][git][/dim] {git_res_dict.get('message')}")
                        else:
                            console.print(f"  [dim][git][/dim] [red]{git_res_dict.get('message')}[/red]")
                    
                    self.run_summary.add_result(task, result)
                    progress.update(task_layer, completed=100, description=f"[cyan]Done: {task.id}")
                    return
        finally:
            # Restore original model
            agent.model_name = original_model

        progress.update(task_layer, completed=100, description=f"[bold red]Failed: {task.id}")

    def _generate_reflection_prompt(self, task: AgentTask, result: AgentResult) -> str:
        """
        Generates a dedicated reflection prompt for verification failure.
        Includes error categorization and potential fix strategies.
        """
        output = result.verification_output or ""
        category = "UNKNOWN"
        strategy = "Analyze the full output to determine the root cause."

        if "SyntaxError" in output or "IndentationError" in output:
            category = "SYNTAX_ERROR"
            strategy = "Fix the syntax or indentation errors identified in the output."
        elif "ModuleNotFoundError" in output or "ImportError" in output:
            category = "IMPORT_ERROR"
            strategy = "Check your imports and ensure all necessary dependencies are installed or created. If you are missing a local file, ensure it was created in the correct location."
        elif "AssertionError" in output or "FAILED" in output or "E       " in output:
            category = "TEST_FAILURE"
            strategy = "Review the test assertions and your implementation. The logic does not match the expected behavior."
        elif "FileNotFoundError" in output or "No such file or directory" in output:
            category = "FILE_NOT_FOUND"
            strategy = "Ensure that all files you intended to create or modify were actually written to the correct location."
        elif "ENOSPC" in output or "Disk full" in output:
            category = "DISK_FULL"
            strategy = "The disk is full or there are no more inodes. Check your disk space and quota."
        elif "Timeout" in output or "timed out" in output:
            category = "TIMEOUT"
            strategy = "Consider if your implementation is efficient or if the verification command needs more time."

        return (
            f"\n--- REFLECTION ---\n"
            f"Your previous attempt to perform task '{task.id}' failed verification.\n"
            f"Task Description: {task.description}\n"
            f"Verification Command: {task.verification_command}\n"
            f"Error Category: {category}\n"
            f"Suggested Strategy: {strategy}\n\n"
            f"Verification Output:\n{output}\n\n"
            f"Please:\n"
            f"1. Analyze the verification output to understand exactly what went wrong.\n"
            f"2. Reflect on your previous approach and identify the flaw.\n"
            f"3. Formulate a corrected plan and execute it using your tools.\n"
            f"4. Ensure the task is fully completed and matches all requirements.\n"
            f"--- END REFLECTION ---\n"
        )
