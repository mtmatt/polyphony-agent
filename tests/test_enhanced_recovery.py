import pytest
import asyncio
import subprocess
from unittest.mock import MagicMock, patch
from polyphony.engine import Orchestrator, ErrorCategory
from polyphony.agent import AgentTask, AgentResult, BaseAgent
from rich.progress import Progress

class RecoveryMockAgent(BaseAgent):
    def __init__(self, model_name="mock-pro", flash_model_name="mock-flash"):
        super().__init__()
        self._model_name = model_name
        self._pro_model_name = model_name
        self._flash_model_name = flash_model_name
        self.context = ""
        self.execute_calls = []

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
        self.execute_calls.append(self.model_name)
        # Always succeed in execution, we'll fail in verification
        return AgentResult(task_id=task.id, success=True, output="Success", agent_model=self.model_name)

    def receive_context(self, context: str):
        self.context = context

    def decompose_goal(self, goal: str):
        return []

    def classify_goal(self, goal: str):
        return "simple"

    def review_plan(self, plan, role):
        return {"approved": True, "comments": []}

def test_model_fallback_on_retry():
    """
    Verifies that the orchestrator falls back to the pro model on retry
    if it was using the flash model.
    """
    agent = RecoveryMockAgent(model_name="pro-model", flash_model_name="flash-model")
    orchestrator = Orchestrator(planner=agent, auto_commit=False)
    from polyphony.run_summary import RunSummary
    orchestrator.run_summary = RunSummary("fallback test")
    
    # Task with verification that fails once and then succeeds
    task = AgentTask(id="task1", description="Fallback test", verification_command="ls", complexity="simple")
    
    with patch("subprocess.run") as mock_run, \
         patch("polyphony.engine.is_git_repo", return_value=False):
        # 1st attempt: Verification fails
        # 2nd attempt: Verification succeeds
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="Verification failed"),
            MagicMock(returncode=0, stdout="Verified", stderr="")
        ]
        
        # Initially switched to flash because it's a simple task
        agent.model_name = "flash-model"
        
        with Progress(transient=True) as progress:
            global_task = progress.add_task("Global", total=1)
            task_layer = progress.add_task("Task", total=100)
            asyncio.run(orchestrator.execute_with_verification(task, progress, global_task, task_layer))
    
    # Check that it called execute_task twice
    assert len(agent.execute_calls) == 2
    # 1st call should be flash (as per initial setup for simple task)
    assert agent.execute_calls[0] == "flash-model"
    # 2nd call should be pro (due to fallback)
    assert agent.execute_calls[1] == "pro-model"
    assert task.status == "completed"

def test_error_categorization():
    """
    Verifies that different error outputs are correctly categorized.
    """
    orchestrator = Orchestrator(planner=RecoveryMockAgent())
    
    assert orchestrator._categorize_error("SyntaxError: invalid syntax") == ErrorCategory.SYNTAX
    assert orchestrator._categorize_error("IndentationError: unexpected indent") == ErrorCategory.SYNTAX
    assert orchestrator._categorize_error("ModuleNotFoundError: No module named 'foo'") == ErrorCategory.IMPORT
    assert orchestrator._categorize_error("ImportError: cannot import name 'bar'") == ErrorCategory.IMPORT
    assert orchestrator._categorize_error("AssertionError: 1 != 2") == ErrorCategory.TEST
    assert orchestrator._categorize_error("FAILED tests/test_foo.py - AssertionError") == ErrorCategory.TEST
    assert orchestrator._categorize_error("FileNotFoundError: [Errno 2] No such file or directory: 'file.txt'") == ErrorCategory.FILE_NOT_FOUND
    assert orchestrator._categorize_error("OSError: [Errno 28] No space left on device") == ErrorCategory.DISK_FULL
    assert orchestrator._categorize_error("ENOSPC: no space left on device") == ErrorCategory.DISK_FULL
    assert orchestrator._categorize_error("TimeoutExpired: Command 'foo' timed out") == ErrorCategory.TIMEOUT
    assert orchestrator._categorize_error("PermissionError: [Errno 13] Permission denied: 'secret.txt'") == ErrorCategory.PERMISSION
    assert orchestrator._categorize_error("API key not found") == ErrorCategory.API_ERROR
    assert orchestrator._categorize_error("Just some random error") == ErrorCategory.UNKNOWN

def test_parallel_execution_dependency_failure():
    """
    Verifies that if a dependency fails, the dependent task is marked as failed
    without even being executed.
    """
    agent = RecoveryMockAgent()
    orchestrator = Orchestrator(planner=agent, auto_commit=False, parallel=True)
    from polyphony.run_summary import RunSummary
    orchestrator.run_summary = RunSummary("dependency failure test")
    
    # t1 will fail
    # t2 depends on t1, should be skipped/failed
    # t3 is independent, should succeed
    tasks = [
        AgentTask(id="t1", description="fail me"),
        AgentTask(id="t2", description="dependent", depends_on=["t1"]),
        AgentTask(id="t3", description="independent")
    ]
    
    # Track which tasks were actually executed
    executed_task_ids = []
    
    async def mock_execute(task, progress, global_task, layer):
        executed_task_ids.append(task.id)
        if task.id == "t1":
            task.status = "failed"
            orchestrator.run_summary.add_result(task, AgentResult(task_id=task.id, success=False, error="Failed"))
        else:
            task.status = "completed"
            orchestrator.run_summary.add_result(task, AgentResult(task_id=task.id, success=True))
            
    with patch.object(orchestrator, 'execute_with_verification', side_effect=mock_execute), \
         patch("polyphony.engine.is_git_repo", return_value=False):
        with Progress(transient=True) as progress:
            global_task = progress.add_task("Global", total=len(tasks))
            asyncio.run(orchestrator._execute_parallel(tasks, progress, global_task))
            
    # t1 should be failed
    # t3 should be completed
    # t2 should be failed/skipped AND NOT EXECUTED
    assert tasks[0].status == "failed"
    assert tasks[2].status == "completed"
    assert tasks[1].status == "failed"
    assert "t2" not in executed_task_ids
