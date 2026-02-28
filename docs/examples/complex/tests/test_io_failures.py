import os
import errno
import pytest
from unittest.mock import patch
from pathlib import Path
from models import TaskList
from todo_cli import save_tasks, main

def test_save_tasks_no_space_message(tmp_path, capsys):
    """
    Test that save_tasks prints a meaningful error message when ENOSPC occurs.
    """
    tl = TaskList()
    tl.add_task("Test task")
    
    tasks_file = tmp_path / "tasks.json"
    
    # Patch models.os.fsync to raise ENOSPC
    with patch("models.os.fsync") as mock_fsync:
        mock_fsync.side_effect = OSError(errno.ENOSPC, "No space left on device")
        
        # Patch todo_cli.TASKS_FILE to use our temp file
        with patch("todo_cli.TASKS_FILE", tasks_file):
            # save_tasks now calls sys.exit(1)
            with pytest.raises(SystemExit) as excinfo:
                save_tasks(tl)
            
            assert excinfo.value.code == 1
            
            captured = capsys.readouterr()
            assert "Error saving tasks" in captured.out
            assert "No space left on device" in captured.out

def test_cli_no_crash_on_io_failure(tmp_path, capsys, monkeypatch):
    """
    Test that the CLI exits gracefully instead of crashing with a traceback
    when an I/O error occurs during saving.
    """
    tasks_file = tmp_path / "tasks.json"
    # Create an empty tasks file first
    tasks_file.write_text('{"tasks": [], "last_id": 0}', encoding="utf-8")
    
    # Set up command line arguments for 'add'
    monkeypatch.setattr("sys.argv", ["todo_cli.py", "add", "New Task"])
    
    # Patch models.os.fsync to raise ENOSPC
    with patch("models.os.fsync") as mock_fsync:
        mock_fsync.side_effect = OSError(errno.ENOSPC, "No space left on device")
        
        # Patch todo_cli.TASKS_FILE
        with patch("todo_cli.TASKS_FILE", tasks_file):
            # If it crashes with traceback, main() will raise OSError
            # If it exits gracefully with sys.exit(1), main() will raise SystemExit
            with pytest.raises(SystemExit) as excinfo:
                main()
            
            assert excinfo.value.code == 1
            
            captured = capsys.readouterr()
            assert "Error saving tasks" in captured.out
            assert "No space left on device" in captured.out

def test_enospc_failure(tmp_path, capsys, monkeypatch):
    """
    Test that the CLI handles ENOSPC (Disk Full) gracefully.
    """
    tasks_file = tmp_path / "tasks.json"
    # Ensure a clean state
    if tasks_file.exists():
        tasks_file.unlink()
    
    # Set up command line arguments for 'add'
    monkeypatch.setattr("sys.argv", ["todo_cli.py", "add", "Task that fails due to disk full"])
    
    # Patch models.os.fsync to raise ENOSPC
    with patch("models.os.fsync") as mock_fsync:
        mock_fsync.side_effect = OSError(errno.ENOSPC, "No space left on device")
        
        # Patch todo_cli.TASKS_FILE to use our temp path
        with patch("todo_cli.TASKS_FILE", tasks_file):
            # The CLI should exit with code 1
            with pytest.raises(SystemExit) as excinfo:
                main()
            
            assert excinfo.value.code == 1
            
            captured = capsys.readouterr()
            # Assert that a graceful error message is printed
            assert "Error saving tasks" in captured.out
            assert "No space left on device" in captured.out
