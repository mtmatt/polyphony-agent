import errno
import pytest
import sys
from unittest.mock import patch
from todo_cli import main

def test_save_to_file_disk_full_graceful(capsys):
    """
    Identified save function: models.TaskList.save_to_file
    
    Simulation:
    1. Mock models.TaskList.save_to_file to raise OSError(errno.ENOSPC)
    2. Invoke todo_cli.main with 'add' command
    3. Verify SystemExit(1) is raised
    4. Verify error message is printed
    """
    # Mock sys.argv for 'add' command
    with patch.object(sys, 'argv', ["todo_cli", "add", "Mocked Task"]):
        # The path for patch is 'models.TaskList.save_to_file' 
        # because todo_cli imports TaskList from models.
        # Alternatively, we could patch 'todo_cli.TaskList.save_to_file'.
        with patch("models.TaskList.save_to_file") as mock_save:
            mock_save.side_effect = OSError(errno.ENOSPC, "No space left on device")
            
            # todo_cli.save_tasks should catch this and call sys.exit(1)
            with pytest.raises(SystemExit) as excinfo:
                main()
            
            assert excinfo.value.code == 1
            
            captured = capsys.readouterr()
            # todo_cli.save_tasks prints "[red]Error saving tasks: {e}[/]"
            assert "Error saving tasks" in captured.out
            assert "No space left on device" in captured.out

if __name__ == "__main__":
    pytest.main([__file__])
