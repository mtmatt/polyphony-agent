import pytest
import os
import shutil
import json
from datetime import datetime
from polyphony.checkpoint import RunCheckpoint
from polyphony.agent import AgentTask, AgentResult
from polyphony.cost import CostTracker

@pytest.fixture
def checkpoint_dir(tmp_path):
    d = tmp_path / "checkpoints"
    d.mkdir()
    return str(d)

def test_checkpoint_save_load(checkpoint_dir):
    run_id = "test-run"
    goal = "test goal"
    context = "test context"
    tasks = [AgentTask(id="task1", description="desc1", status="completed")]
    results = [AgentResult(task_id="task1", success=True)]
    cost_tracker = CostTracker()
    cost_tracker.add_usage("gemini-1.5-flash", 100, 50)
    
    checkpoint = RunCheckpoint(
        run_id=run_id,
        goal=goal,
        context=context,
        tasks_by_goal={goal: tasks},
        results=results,
        result_tasks=tasks,
        cost_tracker=cost_tracker,
        start_time=datetime.now()
    )
    
    path = checkpoint.save(checkpoint_dir)
    assert os.path.exists(path)
    
    loaded = RunCheckpoint.load(run_id, checkpoint_dir)
    assert loaded.run_id == run_id
    assert loaded.goal == goal
    assert loaded.context == context
    assert len(loaded.tasks_by_goal[goal]) == 1
    assert loaded.tasks_by_goal[goal][0].id == "task1"
    assert loaded.tasks_by_goal[goal][0].status == "completed"
    assert len(loaded.results) == 1
    assert loaded.results[0].task_id == "task1"
    assert loaded.cost_tracker.total_cost > 0

def test_list_checkpoints(checkpoint_dir):
    for i in range(3):
        goal = f"goal-{i}"
        tasks = [AgentTask(id="t1", description="d1", status="completed" if i == 0 else "pending")]
        cp = RunCheckpoint(
            run_id=f"run-{i}",
            goal=goal,
            context="context",
            tasks_by_goal={goal: tasks},
            results=[],
            cost_tracker=CostTracker(),
            start_time=datetime.now(),
            last_updated=datetime.now()
        )
        cp.save(checkpoint_dir)
    
    checkpoints = RunCheckpoint.list_checkpoints(checkpoint_dir)
    assert len(checkpoints) == 3
    ids = [c["run_id"] for c in checkpoints]
    assert "run-0" in ids
    assert "run-1" in ids
    assert "run-2" in ids
