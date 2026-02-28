import errno
import pytest
from unittest.mock import patch
from todo_cli import main, save_tasks
from models import TaskList

"""
Identification:
- In 'models.py': The 'TaskList.save_to_file' method handles the atomic write operation to disk.
- In 'todo_cli.py': The 'save_tasks' function is the caller that manages this operation and handles exceptions.

Mocking 'models.TaskList.save_to_file' allows us to simulate a failure during the identified save operation.
"""

def test_disk_full_graceful_exit_mock_method(capsys):
    """
    Simulate a disk full error by mocking TaskList.save_to_file.
    This test verifies that the CLI raises SystemExit instead of a raw OSError traceback.
    """
    # Simulate adding a task
    with patch("sys.argv", ["todo_cli.py", "add", "Test Disk Full"]):
        # Mock the identified save method
        with patch("models.TaskList.save_to_file") as mock_save:
            mock_save.side_effect = OSError(errno.ENOSPC, "No space left on device")
            
            # The test must assert if the CLI raises 'SystemExit' (graceful)
            with pytest.raises(SystemExit) as excinfo:
                main()
            
            # Assert the exit code is 1 (failure)
            assert excinfo.value.code == 1
            
            # Verify the output contains the error message but no traceback
            captured = capsys.readouterr()
            assert "Error saving tasks" in captured.out
            assert "No space left on device" in captured.out
            assert "Traceback" not in captured.out

def test_disk_full_graceful_exit_mock_low_level(capsys):
    """
    Simulate a disk full error by mocking os.fsync within models.py.
    This provides more granular control over where the error occurs during the save operation.
    """
    with patch("sys.argv", ["todo_cli.py", "add", "Test Disk Full Low Level"]):
        # Mock os.fsync inside models module
        with patch("models.os.fsync") as mock_fsync:
            mock_fsync.side_effect = OSError(errno.ENOSPC, "No space left on device")
            
            # The CLI should still handle this gracefully
            with pytest.raises(SystemExit) as excinfo:
                main()
            
            assert excinfo.value.code == 1
            
            captured = capsys.readouterr()
            assert "Error saving tasks" in captured.out
            assert "No space left on device" in captured.out
            assert "Traceback" not in captured.out
