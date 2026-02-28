import errno
import pytest
from unittest.mock import patch
from todo_cli import main
from models import TaskList

def test_disk_full_graceful_exit(tmp_path, monkeypatch, capsys):
    """
    Verify that OSError(errno.ENOSPC) during task saving results in a graceful SystemExit(1).
    """
    # 1. Setup: Create a temporary tasks file path
    test_tasks_file = tmp_path / "tasks.json"
    
    # 2. Setup: Mock CLI arguments for an 'add' command
    # This will trigger a call to save_tasks()
    monkeypatch.setattr("sys.argv", ["todo_cli.py", "add", "Test Task"])
    
    # 3. Patch: Redirect TASKS_FILE in todo_cli to our temp file
    # and patch TaskList.save_to_file to raise ENOSPC
    with patch("todo_cli.TASKS_FILE", test_tasks_file):
        with patch("models.TaskList.save_to_file") as mock_save:
            mock_save.side_effect = OSError(errno.ENOSPC, "No space left on device")
            
            # 4. Act & Assert: Run the CLI and expect SystemExit(1)
            with pytest.raises(SystemExit) as excinfo:
                main()
            
            # Verify it's a graceful exit (exit code 1) and not a crash
            assert excinfo.value.code == 1
            
            # 5. Verify: Check that a helpful error message was printed
            captured = capsys.readouterr()
            assert "Error saving tasks" in captured.out
            assert "No space left on device" in captured.out
            # Ensure no traceback is leaked to the user
            assert "Traceback" not in captured.out
            assert "Traceback" not in captured.err

if __name__ == "__main__":
    pytest.main([__file__])
