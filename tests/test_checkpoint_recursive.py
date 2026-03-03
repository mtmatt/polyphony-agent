import pytest
import asyncio
import os
from unittest.mock import MagicMock, patch
from polyphony.engine import Orchestrator
from polyphony.agent import BaseAgent, AgentTask, AgentResult
from polyphony.checkpoint import RunCheckpoint

from polyphony.agent import BaseAgent, AgentTask, AgentResult, AgentAction, CollaborativePlan, PlanReview, AgentRole

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
        history = [
            AgentAction(action_type="thought", content=f"Thinking about {task.id}"),
            AgentAction(action_type="tool_call", content="ls", metadata={"path": "."}),
            AgentAction(action_type="tool_result", content="file1.txt")
        ]
        return AgentResult(task_id=task.id, success=True, output=f"done {task.id}", history=history)
    def receive_context(self, context): pass
    def decompose_goal(self, goal):
        if goal == "root":
            return [AgentTask(id="subgoal1", description="sub1", agent_type="planner")]
        elif goal == "sub1":
            return [AgentTask(id="task1", description="t1"), AgentTask(id="task2", description="t2")]
        return []
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

def test_checkpoint_recursive_saving(tmp_path):
    checkpoint_dir = str(tmp_path / "checkpoints")
    run_id = "recursive-test"
    
    agent = MockAgent()
    orchestrator = Orchestrator(planner=agent, run_id=run_id, checkpoint_dir=checkpoint_dir)
    
    # We want to check if checkpoints are saved *during* sub1 execution
    original_save = orchestrator._save_checkpoint
    save_calls = []
    
    def mocked_save():
        save_calls.append("save")
        original_save()
    
    orchestrator._save_checkpoint = mocked_save
    
    with patch("polyphony.engine.is_git_repo", return_value=False):
        asyncio.run(orchestrator.run_goal("root"))
    
    # Let's see how many times save was called
    print(f"Save calls: {len(save_calls)}")
    for i, call in enumerate(save_calls):
        print(f"Call {i}: {call}")
    
    # Check if checkpoint actually contains root goal and history
    checkpoint = RunCheckpoint.load(run_id, checkpoint_dir)
    assert checkpoint.goal == "root"
    assert len(checkpoint.results) >= 2 # task1 and task2
    # Find task1 result
    task1_res = next(r for r in checkpoint.results if r.task_id == "task1")
    assert task1_res.output == "done task1"
    assert len(task1_res.history) == 3
    assert task1_res.history[0].action_type == "thought"
    assert "task1" in task1_res.history[0].content
    
    # Expected save calls: many now
    assert len(save_calls) >= 5
