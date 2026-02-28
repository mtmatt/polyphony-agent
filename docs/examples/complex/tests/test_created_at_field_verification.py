from datetime import datetime, timezone
from models import Task

def test_created_at_field_is_automatically_populated():
    """
    Verify that the 'created_at' field is automatically populated 
    with a valid, non-null datetime object upon Task creation.
    """
    # 1. Capture time before creation
    start_time = datetime.now(timezone.utc)
    
    # 2. Create a new Task (without passing metadata)
    task = Task(id=1, description="Test task for created_at")
    
    # 3. Capture time after creation
    end_time = datetime.now(timezone.utc)
    
    # 4. Verify 'created_at' is non-null
    assert task.metadata.created_at is not None
    
    # 5. Verify 'created_at' is a valid datetime object
    assert isinstance(task.metadata.created_at, datetime)
    
    # 6. Verify 'created_at' is within the expected range
    # It should be >= start_time and <= end_time
    assert task.metadata.created_at >= start_time
    assert task.metadata.created_at <= end_time
    
    # 7. Verify it has timezone info (UTC)
    assert task.metadata.created_at.tzinfo == timezone.utc
