import errno
import pytest
import sys
from unittest.mock import patch
from todo_cli import main

def test_disk_full_graceful_exit_confirmed(tmp_path, capsys, monkeypatch):
    """
    Test that the Todo CLI handles a 'Disk Full' (ENOSPC) error gracefully 
    during the 'add' command.
    
    This test patches the 'models.TaskList.save_to_file' method, which is the 
    core function responsible for saving tasks to disk.
    """
    # 1. Setup temporary tasks file path
    tasks_file = tmp_path / "tasks.json"
    
    # 2. Mock CLI arguments: todo_cli.py add "New Task"
    monkeypatch.setattr(sys, "argv", ["todo_cli.py", "add", "New Task"])
    
    # 3. Patch TASKS_FILE in todo_cli to use our temporary path
    # and patch models.TaskList.save_to_file to raise OSError(errno.ENOSPC)
    with patch("todo_cli.TASKS_FILE", tasks_file):
        # The exact function responsible for saving tasks to disk is models.TaskList.save_to_file
        with patch("models.TaskList.save_to_file") as mock_save:
            # Configure the mock to raise a "Disk Full" error
            mock_save.side_effect = OSError(errno.ENOSPC, "No space left on device")
            
            # 4. Invoke the CLI 'main' entry point. 
            # We use pytest.raises(SystemExit) to verify that the CLI exits gracefully.
            with pytest.raises(SystemExit) as excinfo:
                main()
            
            # 5. Assertions
            # Verify exit code is 1 (failure)
            assert excinfo.value.code == 1
            
            captured = capsys.readouterr()
            # Verify the CLI prints a clean error message and not a traceback
            assert "Error saving tasks" in captured.out
            assert "No space left on device" in captured.out
            assert "Traceback" not in captured.out
