import pytest
import os
import json
from pathlib import Path
from datetime import datetime, timezone
from todo_cli import Task, TaskList, load_tasks, save_tasks, TASKS_FILE

@pytest.fixture
def mock_tasks_file(tmp_path, monkeypatch):
    """Fixture to mock TASKS_FILE with a temporary path."""
    test_file = tmp_path / "tasks.json"
    monkeypatch.setattr("todo_cli.TASKS_FILE", test_file)
    return test_file

def test_timezone_aware_created_at():
    """Test that TaskMetadata.created_at is timezone-aware (UTC)."""
    from models import TaskMetadata
    metadata = TaskMetadata()
    assert metadata.created_at.tzinfo is not None
    assert metadata.created_at.tzinfo == timezone.utc

def test_load_tasks_backup_corrupted(mock_tasks_file):
    """Test that load_tasks backs up a corrupted file."""
    mock_tasks_file.write_text("not json", encoding="utf-8")
    backup_file = mock_tasks_file.with_suffix(".json.bak")
    
    assert not backup_file.exists()
    
    tl = load_tasks()
    assert len(tl.tasks) == 0
    assert backup_file.exists()
    assert backup_file.read_text(encoding="utf-8") == "not json"

def test_atomic_save_preserves_permissions(mock_tasks_file):
    """Test that save_tasks preserves file permissions."""
    # Create file and set specific permissions (e.g., read-only for user)
    mock_tasks_file.write_text("{}", encoding="utf-8")
    os.chmod(mock_tasks_file, 0o644)
    
    tl = TaskList()
    tl.add_task("Test task")
    save_tasks(tl)
    
    # Check permissions (on some systems, permissions might be masked by umask, 
    # but we want to see if it's at least not the default 0600 from mkstemp)
    mode = os.stat(mock_tasks_file).st_mode & 0o777
    assert mode == 0o644

def test_rich_table_includes_created_at():
    """Test that the rich table includes the 'Created At' column."""
    tl = TaskList()
    tl.add_task("Task 1")
    table = tl.to_rich_table()
    
    # Check column names
    column_names = [c.header for c in table.columns]
    assert "Created At" in column_names
