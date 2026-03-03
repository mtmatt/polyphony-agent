import pytest
import asyncio
from unittest.mock import MagicMock, patch
from datetime import datetime
from polyphony.engine import Orchestrator
from polyphony.agent import BaseAgent, AgentTask, AgentResult, CollaborativePlan, PlanReview, AgentRole
from polyphony.checkpoint import RunCheckpoint
from polyphony.cost import CostTracker

class MockAgent(BaseAgent):
    def __init__(self, name="mock"):
        super().__init__()
        self._name = name
    @property
    def model_name(self): return self._name
    @model_name.setter
    def model_name(self, v): self._name = v
    @property
    def pro_model_name(self): return "pro"
    @property
    def flash_model_name(self): return "flash"
    def execute_task(self, task, progress=None):
        return AgentResult(task_id=task.id, success=True, output="done")
    def receive_context(self, context): pass
    def decompose_goal(self, goal):
        return [AgentTask(id="task1", description="t1"), AgentTask(id="task2", description="t2")]
    def classify_goal(self, goal): return "complex"
    def review_plan(self, plan: CollaborativePlan, role: AgentRole) -> PlanReview:
        return PlanReview(
            original_plan_id="test",
            reviewers=[role],
            comments=[],
            approved=True,
            confidence_score=1.0,
            consensus_reached=True
        )

def test_orchestrator_resume(tmp_path):
    checkpoint_dir = str(tmp_path / "checkpoints")
    run_id = "resume-test"
    goal = "original goal"
    
    # Pre-create a checkpoint with one task completed
    tasks = [
        AgentTask(id="task1", description="t1", status="completed"),
        AgentTask(id="task2", description="t2", status="pending")
    ]
    results = [AgentResult(task_id="task1", success=True, output="already done")]
    
    checkpoint = RunCheckpoint(
        run_id=run_id,
        goal=goal,
        context="some context",
        tasks_by_goal={goal: tasks},
        results=results,
        result_tasks=[tasks[0]],
        cost_tracker=CostTracker(),
        start_time=datetime.now(),
        is_simple=False
    )
    checkpoint.save(checkpoint_dir)
    
    agent = MockAgent()
    orchestrator = Orchestrator(planner=agent, run_id=run_id, checkpoint_dir=checkpoint_dir)
    
    # Mock execute_task to check it's only called for task2
    agent.execute_task = MagicMock(return_value=AgentResult(task_id="task2", success=True, output="done now"))
    
    with patch("polyphony.engine.is_git_repo", return_value=False):
        asyncio.run(orchestrator.run_goal(goal))
    
    # Verify task1 was skipped and task2 was executed
    agent.execute_task.assert_called_once()
    assert agent.execute_task.call_args[0][0].id == "task2"
    
    # Verify run_summary has both results
    assert len(orchestrator.run_summary.results) == 2
    assert orchestrator.run_summary.results[0].output == "already done"
    assert orchestrator.run_summary.results[1].output == "done now"
