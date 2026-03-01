import errno
import pytest
from unittest.mock import patch
from todo_cli import main

def test_add_task_disk_full_repro(tmp_path, capsys, monkeypatch):
    """
    Reproduction of Disk Full error (ENOSPC) crashing the CLI with a traceback.
    In the current unpatched state, the application raises OSError when 
    disk space is full during the atomic save operation (os.fsync).
    """
    # Use a temporary tasks file for isolation
    tasks_file = tmp_path / "tasks.json"
    
    # Mock CLI arguments: todo_cli.py add "Repro Task"
    monkeypatch.setattr("sys.argv", ["todo_cli.py", "add", "Repro Task"])
    
    # Patch TASKS_FILE in todo_cli to use our temporary path
    with patch("todo_cli.TASKS_FILE", tasks_file):
        # Patch models.os.fsync to simulate ENOSPC
        with patch("models.os.fsync") as mock_fsync:
            mock_fsync.side_effect = OSError(errno.ENOSPC, "No space left on device")
            
            # Verify that the CLI now exits gracefully with SystemExit
            # instead of crashing with a traceback.
            with pytest.raises(SystemExit) as excinfo:
                main()
            
            assert excinfo.value.code == 1
            
            # In the current state, it prints the error but then re-raises it
            captured = capsys.readouterr()
            assert "Error saving tasks" in captured.out
            assert "No space left on device" in captured.out
