from polyphony.agent import AgentTask, AgentResult

def test_agent_task_creation():
    task = AgentTask(id="task1", description="Test task", agent_type="executor")
    assert task.id == "task1"
    assert task.description == "Test task"
    assert task.agent_type == "executor"
    assert task.status == "pending"

def test_agent_result_creation():
    result = AgentResult(task_id="task1", success=True, output="All good")
    assert result.task_id == "task1"
    assert result.success is True
    assert result.output == "All good"
    assert result.error is None
