import pytest
import asyncio
import time
from unittest.mock import MagicMock, patch
from polyphony.engine import Orchestrator
from polyphony.agent import AgentTask, AgentResult, BaseAgent, CollaborativePlan, PlanReview, AgentRole
from rich.progress import Progress

class DelayedMockAgent(BaseAgent):
    def __init__(self, delay=0.1):
        super().__init__()
        self._model_name = "delayed-mock"
        self._pro_model_name = "delayed-mock-pro"
        self._flash_model_name = "delayed-mock-flash"
        self.delay = delay
        self.task_execution_order = []

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
        # Simulate work
        time.sleep(self.delay)
        self.task_execution_order.append(task.id)
        return AgentResult(task_id=task.id, success=True, output=f"Completed {task.id}")

    def receive_context(self, context: str):
        pass

    def decompose_goal(self, goal: str):
        return []

    def classify_goal(self, goal: str):
        return "complex"

    def review_plan(self, plan: CollaborativePlan, role: AgentRole) -> PlanReview:
        return PlanReview(
            original_plan_id="test",
            reviewers=[role],
            comments=[],
            approved=True,
            confidence_score=1.0,
            consensus_reached=True
        )

def test_parallel_execution_latency_reduction():
    """
    Verifies that independent tasks execute concurrently and reduce total latency.
    """
    delay = 0.5
    agent = DelayedMockAgent(delay=delay)
    orchestrator = Orchestrator(planner=agent, auto_commit=False, parallel=True)
    
    from polyphony.run_summary import RunSummary
    orchestrator.run_summary = RunSummary("latency test")
    
    # 4 independent tasks, each taking 0.5s
    # In serial: 2.0s
    # In parallel: ~0.5s (+ overhead)
    tasks = [
        AgentTask(id=f"t{i}", description=f"task {i}") for i in range(4)
    ]
    
    start_time = time.time()
    with patch("polyphony.engine.is_git_repo", return_value=False):
        with Progress(transient=True) as progress:
            global_task = progress.add_task("Global", total=len(tasks))
            asyncio.run(orchestrator._execute_parallel(tasks, progress, global_task))
    end_time = time.time()
    
    total_duration = end_time - start_time
    
    # Sum of individual delays
    expected_serial_duration = delay * len(tasks)
    
    print(f"Parallel duration: {total_duration:.4f}s")
    print(f"Expected serial duration: {expected_serial_duration:.4f}s")
    
    # We expect it to be significantly faster than serial execution
    # Allowing for some overhead, it should definitely be less than 1.0s (delay * 2)
    assert total_duration < expected_serial_duration * 0.75
    assert total_duration >= delay # Must take at least the delay of one task

def test_parallel_execution_with_dependencies():
    """
    Verifies that dependencies are respected even in parallel mode.
    """
    delay = 0.1
    agent = DelayedMockAgent(delay=delay)
    orchestrator = Orchestrator(planner=agent, auto_commit=False, parallel=True)
    
    from polyphony.run_summary import RunSummary
    orchestrator.run_summary = RunSummary("dependency test")
    
    # t1, t2 independent
    # t3 depends on t1, t2
    # t4 depends on t3
    tasks = [
        AgentTask(id="t1", description="task 1"),
        AgentTask(id="t2", description="task 2"),
        AgentTask(id="t3", description="task 3", depends_on=["t1", "t2"]),
        AgentTask(id="t4", description="task 4", depends_on=["t3"])
    ]
    
    with patch("polyphony.engine.is_git_repo", return_value=False):
        with Progress(transient=True) as progress:
            global_task = progress.add_task("Global", total=len(tasks))
            asyncio.run(orchestrator._execute_parallel(tasks, progress, global_task))
    
    execution_order = agent.task_execution_order
    print(f"Execution order: {execution_order}")
    
    # t1 and t2 can be in any order, but must come before t3
    assert execution_order.index("t1") < execution_order.index("t3")
    assert execution_order.index("t2") < execution_order.index("t3")
    
    # t3 must come before t4
    assert execution_order.index("t3") < execution_order.index("t4")

def test_parallel_execution_max_concurrency():
    """
    Verifies that we don't exceed max concurrency (currently hardcoded to 4 in engine.py).
    """
    delay = 0.5
    agent = DelayedMockAgent(delay=delay)
    orchestrator = Orchestrator(planner=agent, auto_commit=False, parallel=True)
    
    from polyphony.run_summary import RunSummary
    orchestrator.run_summary = RunSummary("concurrency test")
    
    # 8 independent tasks
    # With max 4 concurrency, it should take at least 2 * delay = 1.0s
    tasks = [
        AgentTask(id=f"t{i}", description=f"task {i}") for i in range(8)
    ]
    
    start_time = time.time()
    with patch("polyphony.engine.is_git_repo", return_value=False):
        with Progress(transient=True) as progress:
            global_task = progress.add_task("Global", total=len(tasks))
            asyncio.run(orchestrator._execute_parallel(tasks, progress, global_task))
    end_time = time.time()
    
    total_duration = end_time - start_time
    print(f"8 tasks parallel duration: {total_duration:.4f}s")
    
    # Expected time: 2 batches of 4 tasks = 2 * delay
    # Allow some buffer for overhead
    assert total_duration >= delay * 2
    assert total_duration < delay * 3
