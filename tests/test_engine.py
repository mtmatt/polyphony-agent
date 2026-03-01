import pytest
import asyncio
from unittest.mock import MagicMock, patch
from polyphony.engine import Orchestrator
from polyphony.agent import AgentTask, AgentResult, BaseAgent
from rich.progress import Progress

class MockAgent(BaseAgent):
    def __init__(self, model_name="mock-pro", flash_model_name="mock-flash"):
        self._model_name = model_name
        self._pro_model_name = model_name
        self._flash_model_name = flash_model_name
        self.context = ""

    @property
    def model_name(self) -> str:
        return self._model_name

    @model_name.setter
    def model_name(self, value: str):
        self._model_name = value

    @property
    def pro_model_name(self) -> str:
        return self._pro_model_name

    @property
    def flash_model_name(self) -> str:
        return self._flash_model_name

    def execute_task(self, task: AgentTask, progress=None) -> AgentResult:
        if "fail" in task.description and task.retry_count == 0:
            return AgentResult(task_id=task.id, success=False, error="Simulated failure")
        return AgentResult(task_id=task.id, success=True, output="Simulated success", agent_model=self.model_name)

    def receive_context(self, context: str):
        self.context = context

    def decompose_goal(self, goal: str):
        return [AgentTask(id="task1", description=goal)]

    def classify_goal(self, goal: str):
        return "simple"

def test_orchestrator_simple_goal():
    mock_agent = MockAgent()
    orchestrator = Orchestrator(planner=mock_agent, auto_commit=False)
    with patch("polyphony.engine.is_git_repo", return_value=False):
        asyncio.run(orchestrator.run_goal("simple goal"))
    # Verify that the goal was executed
    assert len(orchestrator.run_summary.results) == 1
    assert orchestrator.run_summary.results[0].success is True

def test_orchestrator_verification_success():
    mock_agent = MockAgent()
    orchestrator = Orchestrator(planner=mock_agent, auto_commit=False)
    from polyphony.run_summary import RunSummary
    orchestrator.run_summary = RunSummary("test goal")
    
    task = AgentTask(id="task1", description="Verify this", verification_command="echo 'success'")
    
    with patch("subprocess.run") as mock_run, \
         patch("polyphony.engine.is_git_repo", return_value=False):
        mock_run.return_value = MagicMock(returncode=0, stdout="Verified", stderr="")
        with Progress() as progress:
            global_task = progress.add_task("Global", total=1)
            task_layer = progress.add_task("Task", total=100)
            asyncio.run(orchestrator.execute_with_verification(task, progress, global_task, task_layer))
    
    assert task.retry_count == 0
    assert len(orchestrator.run_summary.results) == 1

def test_orchestrator_verification_retry():
    mock_agent = MockAgent()
    orchestrator = Orchestrator(planner=mock_agent, auto_commit=False)
    from polyphony.run_summary import RunSummary
    orchestrator.run_summary = RunSummary("test goal")
    
    task = AgentTask(id="task1", description="Retry this", verification_command="echo 'retry'")
    
    with patch("subprocess.run") as mock_run, \
         patch("polyphony.engine.is_git_repo", return_value=False):
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="Verification failed"),
            MagicMock(returncode=0, stdout="Verified", stderr="")
        ]
        with Progress() as progress:
            global_task = progress.add_task("Global", total=1)
            task_layer = progress.add_task("Task", total=100)
            asyncio.run(orchestrator.execute_with_verification(task, progress, global_task, task_layer))

    assert len(orchestrator.run_summary.results) == 2 # 1 failed, 1 succeeded

def test_orchestrator_verification_reflection():
    mock_agent = MockAgent()
    orchestrator = Orchestrator(planner=mock_agent, auto_commit=False)
    from polyphony.run_summary import RunSummary
    orchestrator.run_summary = RunSummary("test goal")
    
    task = AgentTask(id="task_refl", description="Reflection test", verification_command="echo 'fail'")
    
    with patch("subprocess.run") as mock_run, \
         patch("polyphony.engine.is_git_repo", return_value=False):
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="Failed output", stderr="Verification error"),
            MagicMock(returncode=0, stdout="Verified", stderr="")
        ]
        with Progress() as progress:
            global_task = progress.add_task("Global", total=1)
            task_layer = progress.add_task("Task", total=100)
            asyncio.run(orchestrator.execute_with_verification(task, progress, global_task, task_layer))

    # Verify that the context contains reflection info
    assert "--- REFLECTION ---" in task.context
    assert "Verification error" in task.context or "Failed output" in task.context
    assert "Reflection test" in task.context
    assert "echo 'fail'" in task.context

def test_orchestrator_model_switching():
    planner = MockAgent(model_name="pro-planner", flash_model_name="flash-planner")
    executor = MockAgent(model_name="pro-executor", flash_model_name="flash-executor")
    orchestrator = Orchestrator(planner=planner, executor=executor, auto_commit=False)
    
    with patch("polyphony.engine.is_git_repo", return_value=False):
        # Test simple goal switching
        planner.classify_goal = MagicMock(return_value="simple")
        asyncio.run(orchestrator.run_goal("simple goal"))
    
    # Verify both agents were switched to flash during execution
    assert planner.model_name == "pro-planner"
    assert executor.model_name == "pro-executor"
    
    # Verify that the executed task used the flash model
    assert orchestrator.run_summary.results[0].agent_model == "flash-executor"

def test_orchestrator_parallel_execution():
    planner = MockAgent()
    orchestrator = Orchestrator(planner=planner, auto_commit=False, parallel=True)
    from polyphony.run_summary import RunSummary
    orchestrator.run_summary = RunSummary("parallel test")
    
    # Define tasks with dependencies
    tasks = [
        AgentTask(id="t1", description="task 1"),
        AgentTask(id="t2", description="task 2"),
        AgentTask(id="t3", description="task 3", dependencies=["t1", "t2"])
    ]
    
    with patch("polyphony.engine.is_git_repo", return_value=False):
        with Progress() as progress:
            global_task = progress.add_task("Global", total=len(tasks))
            asyncio.run(orchestrator._execute_parallel(tasks, progress, global_task))
    
    # Verify all tasks completed
    assert len(orchestrator.run_summary.results) == 3
    task_ids = [r.task_id for r in orchestrator.run_summary.results]
    assert "t1" in task_ids
    assert "t2" in task_ids
    assert "t3" in task_ids
