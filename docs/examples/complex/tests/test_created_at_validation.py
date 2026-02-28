from datetime import datetime
from models import Task, TaskMetadata

def test_task_created_at_auto_population():
    """Verify that 'created_at' is automatically populated with a valid datetime."""
    # Create a task without explicitly providing metadata or created_at
    task = Task(id=1, description="Test task")
    
    # Check that metadata exists
    assert task.metadata is not None
    assert isinstance(task.metadata, TaskMetadata)
    
    # Check that created_at is populated and is a datetime object
    assert task.metadata.created_at is not None
    assert isinstance(task.metadata.created_at, datetime)
    
    # Verify it's a recent timestamp (within the last few seconds)
    now = datetime.now(task.metadata.created_at.tzinfo)
    delta = now - task.metadata.created_at
    assert delta.total_seconds() < 5  # Should be very close to 'now'

def test_task_metadata_explicit_population():
    """Verify that 'created_at' can still be manually provided if needed."""
    custom_time = datetime(2025, 1, 1)
    metadata = TaskMetadata(created_at=custom_time)
    task = Task(id=2, description="Manual task", metadata=metadata)
    
    assert task.metadata.created_at == custom_time
