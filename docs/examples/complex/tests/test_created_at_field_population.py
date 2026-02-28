from datetime import datetime, timezone
from models import Task

def test_created_at_is_auto_populated():
    """
    Verifies that the 'created_at' field is automatically populated
    with a valid, non-null datetime object upon Task creation.
    """
    # 1. Capture time before creation
    start_time = datetime.now(timezone.utc)
    
    # 2. Create a new Task
    # By default, metadata.created_at is populated via default_factory
    task = Task(id=1, description="Testing auto-population of created_at")
    
    # 3. Capture time after creation
    end_time = datetime.now(timezone.utc)
    
    # 4. Verify 'created_at' is non-null
    assert task.metadata.created_at is not None
    
    # 5. Verify 'created_at' is a datetime object
    assert isinstance(task.metadata.created_at, datetime)
    
    # 6. Verify it has timezone info (since models.py uses datetime.now(timezone.utc))
    assert task.metadata.created_at.tzinfo == timezone.utc
    
    # 7. Verify 'created_at' is within the expected range
    assert task.metadata.created_at >= start_time
    assert task.metadata.created_at <= end_time
