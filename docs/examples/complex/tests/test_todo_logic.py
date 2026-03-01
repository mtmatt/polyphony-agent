import pytest
import os
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from pydantic import ValidationError
from todo_cli import Task, TaskList, load_tasks, save_tasks, TASKS_FILE

@pytest.fixture
def mock_tasks_file(tmp_path, monkeypatch):
    """Fixture to mock TASKS_FILE with a temporary path."""
    test_file = tmp_path / "tasks.json"
    monkeypatch.setattr("todo_cli.TASKS_FILE", test_file)
    return test_file

def test_task_creation():
    """Test creating a single task."""
    task = Task(id=1, description="Test task")
    assert task.id == 1
    assert task.description == "Test task"
    assert task.completed is False

def test_task_created_at_is_valid_datetime():
    """Verify that 'created_at' is a valid, non-null datetime object upon Task creation."""
    task = Task(id=1, description="Test task")
    assert task.metadata.created_at is not None
    assert isinstance(task.metadata.created_at, datetime)

def test_task_mark_completed():
    """Test marking a task as completed."""
    task = Task(id=1, description="Test task")
    task.mark_completed()
    assert task.completed is True

def test_task_list_add():
    """Test adding a task to TaskList."""
    tl = TaskList()
    start_time = datetime.now(timezone.utc)
    task = tl.add_task("Buy milk")
    assert len(tl.tasks) == 1
    assert task.id == 1
    assert task.description == "Buy milk"
    # Verify valid created_at timestamp
    assert isinstance(task.metadata.created_at, datetime)
    assert task.metadata.created_at >= start_time
    
    task2 = tl.add_task("Buy eggs")
    assert task2.id == 2
    assert task2.metadata.created_at >= task.metadata.created_at

def test_task_list_add_multiple_and_verify_id_timestamp():
    """Verify that multiple added tasks receive unique, incrementing IDs and valid timestamps."""
    tl = TaskList()
    descriptions = ["Task A", "Task B", "Task C"]
    tasks = []
    
    start_time = datetime.now(timezone.utc)
    
    for i, desc in enumerate(descriptions, 1):
        task = tl.add_task(desc)
        tasks.append(task)
        
        # Verify unique incrementing ID
        assert task.id == i
        
        # Verify valid created_at timestamp
        assert isinstance(task.metadata.created_at, datetime)
        assert task.metadata.created_at >= start_time
        # Ensure it's not in the future (allowing for tiny clock drift/precision if needed, but usually fine)
        assert task.metadata.created_at <= datetime.now(timezone.utc)

    # Double check uniqueness across the list
    ids = [task.id for task in tl.tasks]
    assert len(ids) == 3
    assert len(ids) == len(set(ids))
    assert ids == [1, 2, 3]

def test_task_list_get():
    """Test getting a task by ID."""
    tl = TaskList()
    tl.add_task("Task 1")
    task = tl.get_task(1)
    assert task is not None
    assert task.description == "Task 1"
    
    assert tl.get_task(99) is None

def test_task_list_remove():
    """Test removing a task."""
    tl = TaskList()
    tl.add_task("Task 1")
    assert tl.remove_task(1) is True
    assert len(tl.tasks) == 0
    assert tl.remove_task(1) is False

def test_task_list_add_with_id():
    """Test adding a task with a specific ID."""
    tl = TaskList()
    task = tl.add_task("Specific ID task", task_id=10)
    assert task.id == 10
    assert tl.last_id == 10
    
    # Next automatic ID should be 11
    next_task = tl.add_task("Next automatic task")
    assert next_task.id == 11
    assert tl.last_id == 11

def test_get_completed_pending():
    """Test filtering completed and pending tasks."""
    tl = TaskList()
    t1 = tl.add_task("Task 1")
    t2 = tl.add_task("Task 2")
    t1.mark_completed()
    
    completed = tl.get_completed_tasks()
    pending = tl.get_pending_tasks()
    
    assert len(completed) == 1
    assert completed[0].description == "Task 1"
    assert len(pending) == 1
    assert pending[0].description == "Task 2"

def test_task_validation():
    """Test Pydantic validation for Task model."""
    # Test valid task
    task = Task(id=1, description="Valid task")
    assert task.description == "Valid task"
    assert task.completed is False

    # Test invalid description (empty string)
    with pytest.raises(ValidationError):
        Task(id=1, description="")

    # Test missing id
    with pytest.raises(ValidationError):
        Task(description="Missing ID")

    # Test invalid id type (non-numeric string)
    with pytest.raises(ValidationError):
        Task(id="abc", description="Invalid ID type")

    # Test invalid completed type (not a boolean or coercible)
    with pytest.raises(ValidationError):
        Task(id=1, description="Invalid completed", completed="not-a-bool")

def test_task_list_validation():
    """Test Pydantic validation for TaskList model."""
    # Test valid TaskList with dictionary objects (should be coerced to Task objects)
    tl = TaskList(tasks=[{"id": 1, "description": "Task 1", "completed": True}])
    assert len(tl.tasks) == 1
    assert isinstance(tl.tasks[0], Task)
    assert tl.tasks[0].id == 1
    assert tl.tasks[0].completed is True

    # Test invalid tasks list item (wrong type)
    with pytest.raises(ValidationError):
        TaskList(tasks=["Not a task object"])

    # Test invalid tasks list item (missing required field in task)
    with pytest.raises(ValidationError):
        TaskList(tasks=[{"id": 1}]) # Missing description

    # Test invalid tasks type (not a list)
    with pytest.raises(ValidationError):
        TaskList(tasks="Not a list")

def test_json_serialization_direct():
    """Test direct JSON serialization and deserialization of TaskList."""
    tl = TaskList()
    tl.add_task("Serialization test")
    
    # Dump to JSON
    json_str = tl.model_dump_json()
    assert '"description":"Serialization test"' in json_str
    
    # Validate from JSON
    new_tl = TaskList.model_validate_json(json_str)
    assert len(new_tl.tasks) == 1
    assert new_tl.tasks[0].description == "Serialization test"

def test_save_tasks_creates_parent_dir(tmp_path, monkeypatch):
    """Test that save_tasks creates the parent directory if it doesn't exist."""
    nested_dir = tmp_path / "subdir"
    test_file = nested_dir / "tasks.json"
    monkeypatch.setattr("todo_cli.TASKS_FILE", test_file)
    
    assert not nested_dir.exists()
    
    tl = TaskList()
    save_tasks(tl)
    
    assert nested_dir.exists()
    assert test_file.exists()

def test_save_load_tasks(mock_tasks_file):
    """Test saving and loading tasks to/from JSON."""
    tl = TaskList()
    tl.add_task("Save me")
    save_tasks(tl)
    
    assert mock_tasks_file.exists()
    
    loaded_tl = load_tasks()
    assert len(loaded_tl.tasks) == 1
    assert loaded_tl.tasks[0].description == "Save me"
    assert loaded_tl.tasks[0].id == 1

def test_load_nonexistent_file(mock_tasks_file):
    """Test loading from a file that doesn't exist."""
    assert not mock_tasks_file.exists()
    
    tl = load_tasks()
    assert isinstance(tl, TaskList)
    assert len(tl.tasks) == 0
    assert mock_tasks_file.exists() # load_tasks should create it if missing

def test_load_invalid_json(mock_tasks_file):
    """Test loading from a file with invalid JSON content."""
    mock_tasks_file.write_text("invalid json content", encoding="utf-8")
    
    tl = load_tasks()
    assert isinstance(tl, TaskList)
    assert len(tl.tasks) == 0

def test_load_empty_file(mock_tasks_file):
    """Test loading from an empty (0 byte) file."""
    mock_tasks_file.write_text("", encoding="utf-8")
    
    tl = load_tasks()
    assert isinstance(tl, TaskList)
    assert len(tl.tasks) == 0

def test_task_mark_incomplete():
    """Test marking a completed task as incomplete."""
    task = Task(id=1, description="Test task", completed=True)
    task.mark_incomplete()
    assert task.completed is False

def test_task_list_add_non_sequential():
    """Test add_task when existing task IDs are not sequential."""
    tl = TaskList()
    tl.tasks.append(Task(id=5, description="High ID task"))
    new_task = tl.add_task("Next task")
    assert new_task.id == 6

def test_task_list_remove_empty():
    """Test removing a task from an empty TaskList."""
    tl = TaskList()
    assert tl.remove_task(1) is False

def test_load_tasks_valid_json_invalid_model(mock_tasks_file):
    """Test loading from a file that is valid JSON but not a valid TaskList model."""
    # Write JSON that fails TaskList validation (e.g., tasks is not a list)
    mock_tasks_file.write_text('{"tasks": "not a list"}', encoding="utf-8")
    
    tl = load_tasks()
    assert isinstance(tl, TaskList)
    assert len(tl.tasks) == 0

def test_save_load_multiple_tasks(mock_tasks_file):
    """Test saving and loading multiple tasks."""
    tl = TaskList()
    tl.add_task("Task 1")
    tl.add_task("Task 2")
    tl.get_task(1).mark_completed()
    save_tasks(tl)
    
    loaded_tl = load_tasks()
    assert len(loaded_tl.tasks) == 2
    assert loaded_tl.get_task(1).completed is True
    assert loaded_tl.get_task(2).completed is False

def test_task_list_to_rich_table():
    """Test to_rich_table method of TaskList."""
    from rich.table import Table
    tl = TaskList()
    tl.add_task("Task 1")
    tl.add_task("Task 2")
    tl.get_task(1).mark_completed()
    
    table = tl.to_rich_table()
    assert isinstance(table, Table)
    assert table.title == "Todo Tasks"
    # rich Table doesn't easily expose rows for simple assertion, 
    # but we've verified it returns a Table object.

def test_task_list_save_to_file(tmp_path):
    """Test save_to_file method of TaskList."""
    test_file = tmp_path / "manual_save.json"
    tl = TaskList()
    tl.add_task("Manual save test")
    
    tl.save_to_file(test_file)
    assert test_file.exists()
    
    content = test_file.read_text(encoding="utf-8")
    assert '"description": "Manual save test"' in content
    
    # Verify we can load it back
    new_tl = TaskList.model_validate_json(content)
    assert len(new_tl.tasks) == 1
    assert new_tl.tasks[0].description == "Manual save test"

def test_task_metadata_created_at():
    """Test that a task metadata has a created_at timestamp."""
    task = Task(id=1, description="Task with timestamp")
    assert task.metadata.created_at is not None
    assert isinstance(task.metadata.created_at, datetime)
    # Since it defaults to now, it should be close to now
    now = datetime.now(timezone.utc)
    # Check that it's within a reasonable range (e.g., 5 seconds)
    delta = abs((now - task.metadata.created_at).total_seconds())
    assert delta < 5

def test_task_list_id_incrementing_behavior():
    """Test that TaskList increments IDs and updates last_id correctly without reuse."""
    tl = TaskList()
    t1 = tl.add_task("Task 1")
    assert t1.id == 1
    assert tl.last_id == 1
    
    t2 = tl.add_task("Task 2")
    assert t2.id == 2
    assert tl.last_id == 2
    
    tl.remove_task(2)
    # If we want monotonic increase, the next ID should be 3, not 2 again.
    t3 = tl.add_task("Task 3")
    assert t3.id == 3
    assert tl.last_id == 3

def test_task_id_and_timestamp_initialization():
    """Verify that Task IDs are unique and sequential, and created_at timestamps are initialized correctly."""
    tl = TaskList()
    
    # Check initial state
    assert tl.last_id == 0
    assert len(tl.tasks) == 0
    
    start_time = datetime.now(timezone.utc)
    
    # Add first task
    task1 = tl.add_task("Task 1")
    assert task1.id == 1
    assert tl.last_id == 1
    assert isinstance(task1.metadata.created_at, datetime)
    assert task1.metadata.created_at >= start_time
    assert task1.metadata.created_at.tzinfo == timezone.utc
    
    # Add second task
    task2 = tl.add_task("Task 2")
    assert task2.id == 2
    assert tl.last_id == 2
    assert task2.metadata.created_at >= task1.metadata.created_at
    
    # Add third task
    task3 = tl.add_task("Task 3")
    assert task3.id == 3
    assert tl.last_id == 3
    assert task3.metadata.created_at >= task2.metadata.created_at
    
    # Verify uniqueness
    ids = [t.id for t in tl.tasks]
    assert len(set(ids)) == 3
    assert ids == [1, 2, 3]
    
    # Verify that removing a task doesn't reset the next ID
    tl.remove_task(2)
    task4 = tl.add_task("Task 4")
    assert task4.id == 4
    assert tl.last_id == 4
    assert [t.id for t in tl.tasks] == [1, 3, 4]

def test_task_list_id_persistence_after_reload(tmp_path):
    """Test that last_id is preserved after saving and loading."""
    tl = TaskList()
    tl.add_task("Task 1")
    tl.add_task("Task 2")
    tl.remove_task(2)
    
    json_str = tl.to_json()
    new_tl = TaskList.from_json(json_str)
    
    assert new_tl.last_id == 2
    t3 = new_tl.add_task("Task 3")
    assert t3.id == 3

def test_task_ids_increment_sequentially():
    """Verify that multiple added tasks receive IDs that increment exactly by one."""
    tl = TaskList()
    t1 = tl.add_task("First task")
    t2 = tl.add_task("Second task")
    t3 = tl.add_task("Third task")
    
    assert t2.id == t1.id + 1
    assert t3.id == t2.id + 1
    
    # Additional verification for clarity
    assert t1.id == 1
    assert t2.id == 2
    assert t3.id == 3

def test_new_tasks_receive_timestamp_and_unique_id():
    """
    Verify that new tasks automatically receive a timestamp and a unique integer ID.
    This fulfills the requirement of ensuring all tasks have these critical fields populated.
    """
    tl = TaskList()
    
    # Task 1
    t1 = tl.add_task("Task 1")
    assert isinstance(t1.id, int)
    assert t1.id > 0
    assert isinstance(t1.metadata.created_at, datetime)
    
    # Task 2
    t2 = tl.add_task("Task 2")
    assert isinstance(t2.id, int)
    assert t2.id == t1.id + 1
    assert t2.id != t1.id
    assert isinstance(t2.metadata.created_at, datetime)
    
    # Ensure they are distinct
    assert t1.id != t2.id

def test_save_to_file_atomic_behavior(tmp_path):
    """
    Verify that save_to_file follows the atomic save protocol:
    1. Create a temporary file in the same directory.
    2. Write JSON data.
    3. Flush and fsync.
    4. Atomic replace.
    5. Cleanup on failure.
    """
    target_path = tmp_path / "tasks.json"
    tl = TaskList()
    tl.add_task("Test task")
    
    # We want to track calls to important functions
    with (
        patch("tempfile.mkstemp") as mock_mkstemp,
        patch("os.fdopen", create=True) as mock_fdopen,
        patch("os.fsync") as mock_fsync,
        patch("os.replace") as mock_replace,
        patch("shutil.copymode") as mock_copymode
    ):
        # Mock mkstemp to return (fd, path)
        temp_fd = 999
        temp_path_str = str(target_path) + ".tmp"
        mock_mkstemp.return_value = (temp_fd, temp_path_str)
        
        # Mock fdopen to return a context manager
        mock_file = MagicMock()
        mock_file.fileno.return_value = temp_fd
        mock_fdopen.return_value.__enter__.return_value = mock_file
        
        tl.save_to_file(target_path)
        
        # 1. Verify mkstemp was called with correct directory
        mock_mkstemp.assert_called_once()
        args, kwargs = mock_mkstemp.call_args
        assert kwargs["dir"] == target_path.parent
        
        # 2. Verify fdopen was called
        mock_fdopen.assert_called_once_with(temp_fd, 'w', encoding='utf-8')
        
        # 3. Verify fsync was called
        mock_fsync.assert_called_once()
        
        # 4. Verify replace was called with (temp, target)
        mock_replace.assert_called_once()
        temp_arg, target_arg = mock_replace.call_args[0]
        assert str(target_arg) == str(target_path)
        
def test_save_to_file_cleanup_on_failure(tmp_path):
    """Verify that the temporary file is cleaned up if a failure occurs before replace."""
    target_path = tmp_path / "tasks.json"
    tl = TaskList()
    tl.add_task("Test task")
    
    # Mocking os.fsync to raise an exception
    with (
        patch("tempfile.mkstemp") as mock_mkstemp,
        patch("os.fdopen") as mock_fdopen,
        patch("os.fsync", side_effect=Exception("Disk full")),
        patch("os.replace") as mock_replace,
        patch("os.path.exists", return_value=True),
        patch("os.remove") as mock_remove
    ):
        temp_fd = 999
        temp_path = str(target_path) + ".tmp"
        mock_mkstemp.return_value = (temp_fd, temp_path)
        
        mock_file = MagicMock()
        mock_file.fileno.return_value = temp_fd
        mock_fdopen.return_value.__enter__.return_value = mock_file
        
        try:
            tl.save_to_file(target_path)
        except Exception as e:
            assert str(e) == "Disk full"
        
        # Verify replace was NEVER called
        mock_replace.assert_not_called()
        
        # Verify temp file was cleaned up
        mock_remove.assert_called_once_with(temp_path)
