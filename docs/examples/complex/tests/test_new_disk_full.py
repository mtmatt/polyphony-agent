import errno
import pytest
from unittest.mock import patch
from todo_cli import main

def test_add_task_disk_full_handled(tmp_path, capsys, monkeypatch):
    """
    Test that the Todo CLI handles a 'Disk Full' (ENOSPC) error gracefully 
    during the 'add' command.
    
    This test patches the custom save method 'models.TaskList.save_to_file'.
    """
    # 1. Use a temporary tasks file for isolation
    tasks_file = tmp_path / "tasks.json"
    
    # 2. Mock CLI arguments: todo_cli.py add "Buy milk"
    monkeypatch.setattr("sys.argv", ["todo_cli.py", "add", "Buy milk"])
    
    # 3. Patch TASKS_FILE in todo_cli to use our temporary path
    # and patch models.TaskList.save_to_file to raise OSError(errno.ENOSPC)
    with patch("todo_cli.TASKS_FILE", tasks_file):
        with patch("models.TaskList.save_to_file") as mock_save:
            # Configure the mock to raise a "Disk Full" error
            mock_save.side_effect = OSError(errno.ENOSPC, "No space left on device")
            
            # 4. Invoke the CLI 'add' command. 
            # The application is expected to catch the error, print it, and exit with code 1.
            with pytest.raises(SystemExit) as excinfo:
                main()
            
            # 5. Assertions
            assert excinfo.value.code == 1
            
            captured = capsys.readouterr()
            # Verify the CLI handles the error gracefully and prints a relevant message
            assert "Error saving tasks" in captured.out
            assert "No space left on device" in captured.out
            assert "Traceback" not in captured.out
