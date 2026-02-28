import errno
import pytest
import sys
from unittest.mock import patch
from todo_cli import main

def test_disk_full_simulation(capsys):
    """
    Simulate a disk full error (ENOSPC) during the task save operation.
    
    Identified function: models.TaskList.save_to_file
    Target for patch: models.TaskList.save_to_file
    """
    # Simulate adding a task via CLI arguments
    with patch.object(sys, "argv", ["todo_cli", "add", "Simulated Task"]):
        # Mock the save_to_file method to raise Disk Full error
        with patch("models.TaskList.save_to_file") as mock_save:
            mock_save.side_effect = OSError(errno.ENOSPC, "No space left on device")
            
            # Verify that the CLI exits gracefully with SystemExit(1)
            with pytest.raises(SystemExit) as excinfo:
                main()
            
            # Assert exit code is 1 (failure)
            assert excinfo.value.code == 1
            
            # Verify that the error message was printed
            captured = capsys.readouterr()
            assert "Error saving tasks" in captured.out
            assert "No space left on device" in captured.out

if __name__ == "__main__":
    pytest.main([__file__])
