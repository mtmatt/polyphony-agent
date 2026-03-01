import pytest
import asyncio
import os
import shutil
from unittest.mock import MagicMock, patch
from polyphony.engine import Orchestrator
from polyphony.agent import BaseAgent, AgentTask, AgentResult, AgentAction
from polyphony.checkpoint import RunCheckpoint

class MockAgent(BaseAgent):
    def __init__(self, name="mock"):
        super().__init__()
        self._name = name
        self.context = ""
    @property
    def model_name(self): return self._name
    @model_name.setter
    def model_name(self, v): pass
    @property
    def pro_model_name(self): return self._name
    @property
    def flash_model_name(self): return None
    
    def receive_context(self, ctx): self.context = ctx
    
    def execute_task(self, task, progress=None):
        return AgentResult(task_id=task.id, success=True, output=f"Completed {task.id}")
    
    def decompose_goal(self, goal):
        return [
            AgentTask(id="t1", description="task 1"),
            AgentTask(id="t2", description="task 2")
        ]
    
    def classify_goal(self, goal): return "complex"

def test_orchestrator_resume_with_history(tmp_path):
    async def run():
        checkpoint_dir = str(tmp_path / "checkpoints")
        os.makedirs(checkpoint_dir)
        
        agent = MockAgent()
        orchestrator = Orchestrator(planner=agent, checkpoint_dir=checkpoint_dir, run_id="test-resume")
        
        # 1. Run first task only
        # We'll mock decompose_goal to return two tasks
        with patch.object(MockAgent, 'decompose_goal', return_value=[
            AgentTask(id="t1", description="task 1"),
            AgentTask(id="t2", description="task 2")
        ]):
            # Mock execute_task to fail on t2 but succeed on t1
            def side_effect(task, progress=None):
                if task.id == "t1":
                    return AgentResult(task_id="t1", success=True, output="Output 1")
                else:
                    return AgentResult(task_id="t2", success=False, error="Simulated failure")
            
            with patch.object(MockAgent, 'execute_task', side_effect=side_effect):
                await orchestrator.run_goal("goal")
        
        # Checkpoint should exist and t1 should be completed
        checkpoint = RunCheckpoint.load("test-resume", checkpoint_dir)
        assert checkpoint is not None
        tasks = checkpoint.tasks_by_goal["goal"]
        assert tasks[0].id == "t1"
        assert tasks[0].status == "completed"
        assert tasks[1].id == "t2"
        assert tasks[1].status == "failed"
        
        # 2. Resume and check if t2 receives history of t1
        orchestrator2 = Orchestrator(planner=agent, checkpoint_dir=checkpoint_dir, run_id="test-resume")
        
        # We want to verify that when t2 is executed, its context contains "Output 1"
        captured_contexts = []
        def side_effect2(task, progress=None):
            captured_contexts.append(task.context)
            return AgentResult(task_id=task.id, success=True, output="Output 2")
        
        with patch.object(MockAgent, 'execute_task', side_effect=side_effect2):
            await orchestrator2.run_goal("goal")
        
        # Find the context for t2 (it might have been executed if we resumed)
        assert len(captured_contexts) > 0
        has_history = any("Output 1" in ctx for ctx in captured_contexts if ctx)
        assert has_history, f"Context did not contain history of previous tasks: {captured_contexts}"

    asyncio.run(run())

if __name__ == "__main__":
    pytest.main([__file__])
