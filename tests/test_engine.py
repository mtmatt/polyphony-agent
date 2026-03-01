import pytest
from unittest.mock import MagicMock
from polyphony.engine import Orchestrator
from polyphony.agent import AgentTask, AgentResult, BaseAgent
from rich.progress import Progress

class MockAgent(BaseAgent):
    def execute_task(self, task: AgentTask, progress=None) -> AgentResult:
        if "fail" in task.description and task.retry_count == 0:
            return AgentResult(task_id=task.id, success=False, error="Simulated failure")
        return AgentResult(task_id=task.id, success=True, output="Simulated success")

    def receive_context(self, context: str):
        pass

    def decompose_goal(self, goal: str):
        return [AgentTask(id="task1", description=goal)]

    def classify_goal(self, goal: str):
        return "simple"

def test_orchestrator_simple_goal():
    mock_agent = MockAgent()
    orchestrator = Orchestrator(planner=mock_agent, auto_commit=False)
    orchestrator.run_goal("simple goal")
    # Verify that the goal was executed
    assert len(orchestrator.run_summary.results) == 1
    assert orchestrator.run_summary.results[0].success is True

def test_orchestrator_verification_success():
    mock_agent = MockAgent()
    orchestrator = Orchestrator(planner=mock_agent, auto_commit=False)
    from polyphony.run_summary import RunSummary
    orchestrator.run_summary = RunSummary("test goal")
    
    # Mock subprocess.run for verification
    import subprocess
    original_run = subprocess.run
    subprocess.run = MagicMock(return_value=MagicMock(returncode=0, stdout="Verified", stderr=""))
    
    task = AgentTask(id="task1", description="Verify this", verification_command="echo 'success'")
    
    with Progress() as progress:
        global_task = progress.add_task("Global", total=1)
        task_layer = progress.add_task("Task", total=100)
        orchestrator.execute_with_verification(task, progress, global_task, task_layer)
    
    assert task.retry_count == 0
    assert len(orchestrator.run_summary.results) == 1
    
    # Restore subprocess.run
    subprocess.run = original_run

def test_orchestrator_verification_retry():
    mock_agent = MockAgent()
    orchestrator = Orchestrator(planner=mock_agent, auto_commit=False)
    from polyphony.run_summary import RunSummary
    orchestrator.run_summary = RunSummary("test goal")
    
    # Mock subprocess.run for verification: fails first time, succeeds second
    import subprocess
    original_run = subprocess.run
    
    # Create a side effect for mock_run
    mock_run = MagicMock()
    mock_run.side_effect = [
        MagicMock(returncode=1, stdout="", stderr="Verification failed"),
        MagicMock(returncode=0, stdout="Verified", stderr="")
    ]
    subprocess.run = mock_run
    
    task = AgentTask(id="task1", description="Retry this", verification_command="echo 'retry'")
    
    with Progress() as progress:
        global_task = progress.add_task("Global", total=1)
        task_layer = progress.add_task("Task", total=100)
        orchestrator.execute_with_verification(task, progress, global_task, task_layer)

    # Restore subprocess.run
    subprocess.run = original_run

def test_orchestrator_multi_agent():
    planner = MockAgent()
    executor = MockAgent()
    orchestrator = Orchestrator(planner=planner, executor=executor, auto_commit=False)
    
    special_agent = MockAgent()
    special_agent.execute_task = MagicMock(return_value=AgentResult(task_id="task2", success=True, output="Special success"))
    orchestrator.register_agent("special", special_agent)
    
    from polyphony.run_summary import RunSummary
    orchestrator.run_summary = RunSummary("multi agent goal")
    
    task1 = AgentTask(id="task1", description="normal task", agent_type="executor")
    task2 = AgentTask(id="task2", description="special task", agent_type="special")
    
    with Progress() as progress:
        global_task = progress.add_task("Global", total=2)
        task_layer = progress.add_task("Task", total=100)
        orchestrator.execute_with_verification(task1, progress, global_task, task_layer)
        orchestrator.execute_with_verification(task2, progress, global_task, task_layer)
    
    assert special_agent.execute_task.called
    assert orchestrator.run_summary.results[1].output == "Special success"
