import errno
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from todo_cli import main, TASKS_FILE
from models import TaskList

def test_disk_full_on_add(tmp_path, capsys, monkeypatch):
    """
    Test that the application handles a disk full error (ENOSPC) gracefully
    when attempting to save tasks after adding a new one.
    """
    # Use a temporary tasks file for this test
    test_tasks_file = tmp_path / "tasks.json"
    
    # Mock command line arguments: todo_cli.py add "New Task"
    monkeypatch.setattr("sys.argv", ["todo_cli.py", "add", "New Task"])
    
    # Patch TASKS_FILE in todo_cli to use our temporary path
    with patch("todo_cli.TASKS_FILE", test_tasks_file):
        # Patch models.os.fsync to simulate disk full at the point of flushing to disk
        with patch("models.os.fsync") as mock_fsync:
            mock_fsync.side_effect = OSError(errno.ENOSPC, "No space left on device")
            
            # The application should call sys.exit(1) on failure
            with pytest.raises(SystemExit) as excinfo:
                main()
            
            # Verify exit code
            assert excinfo.value.code == 1
            
            # Verify error message is printed to console
            captured = capsys.readouterr()
            assert "Error saving tasks" in captured.out
            assert "No space left on device" in captured.out
            
            # Ensure no traceback was printed (stderr should be empty in this case as we used rich console)
            # Actually rich might print to stdout by default unless configured otherwise.
            # todo_cli.py uses console = Console() which defaults to stdout.
            assert "Traceback" not in captured.out
            assert "Traceback" not in captured.err

def test_disk_full_on_done(tmp_path, capsys, monkeypatch):
    """
    Test that the application handles a disk full error gracefully when marking a task as done.
    """
    test_tasks_file = tmp_path / "tasks.json"
    # Create a task list with one task
    tl = TaskList()
    tl.add_task("Existing Task")
    test_tasks_file.write_text(tl.to_json())
    
    monkeypatch.setattr("sys.argv", ["todo_cli.py", "done", "1"])
    
    with patch("todo_cli.TASKS_FILE", test_tasks_file):
        with patch("models.os.fsync") as mock_fsync:
            mock_fsync.side_effect = OSError(errno.ENOSPC, "No space left on device")
            
            with pytest.raises(SystemExit) as excinfo:
                main()
            
            assert excinfo.value.code == 1
            captured = capsys.readouterr()
            assert "Error saving tasks" in captured.out
            assert "No space left on device" in captured.out
            assert "Traceback" not in captured.out
