import pytest
from datetime import datetime, timezone, timedelta
from models import TaskList, Task

def test_multiple_tasks_sequence_verification():
    """
    Verify that multiple tasks added in sequence receive unique IDs 
     and valid 'created_at' timestamps that are set automatically.
    """
    tl = TaskList()
    num_tasks = 10
    tasks = []
    
    # Record start time for comparison
    start_time = datetime.now(timezone.utc)
    
    # Add tasks in sequence
    for i in range(num_tasks):
        desc = f"Task {i+1}"
        task = tl.add_task(desc)
        tasks.append(task)
    
    # 1. Verify Unique IDs and Sequentiality
    ids = [task.id for task in tasks]
    assert len(ids) == num_tasks, "Should have added exactly num_tasks"
    assert len(set(ids)) == num_tasks, "All IDs must be unique"
    
    for i, task_id in enumerate(ids):
        assert task_id == i + 1, f"Task ID should be {i+1}, got {task_id}"
    
    # 2. Verify Valid Timestamps
    for task in tasks:
        # Check that created_at is automatically populated and is a datetime
        assert task.metadata.created_at is not None, f"Task {task.id} has no timestamp"
        assert isinstance(task.metadata.created_at, datetime), f"Task {task.id} timestamp is not a datetime"
        
        # Check that it's set to UTC (as per models.py implementation)
        assert task.metadata.created_at.tzinfo == timezone.utc, f"Task {task.id} timestamp should be in UTC"
        
        # Check that it's within a reasonable range (after start_time and before now)
        assert task.metadata.created_at >= start_time, f"Task {task.id} timestamp {task.metadata.created_at} is before start_time {start_time}"
        assert task.metadata.created_at <= datetime.now(timezone.utc) + timedelta(seconds=1), f"Task {task.id} timestamp is in the future"

    # 3. Verify monotonic increase of timestamps (tasks added later should have >= timestamp)
    for i in range(1, len(tasks)):
        assert tasks[i].metadata.created_at >= tasks[i-1].metadata.created_at, \
            f"Task {tasks[i].id} timestamp should be >= Task {tasks[i-1].id} timestamp"

if __name__ == "__main__":
    # Allow running this script directly for manual verification
    try:
        test_multiple_tasks_sequence_verification()
        print("Verification SUCCESSFUL: Multiple tasks received unique IDs and valid timestamps.")
    except Exception as e:
        print(f"Verification FAILED: {e}")
        exit(1)
