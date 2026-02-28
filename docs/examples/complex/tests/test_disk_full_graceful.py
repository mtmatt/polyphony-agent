import errno
import pytest
from unittest.mock import patch
from todo_cli import main
import sys

def test_disk_full_graceful_exit(capsys):
    """
    Test that the CLI exits gracefully with an error message and status code 1
    when the disk is full (ENOSPC), instead of crashing with a traceback.
    """
    # Mock sys.argv to simulate 'add' command
    with patch.object(sys, 'argv', ["todo_cli", "add", "Test Task"]):
        # Mock models.os.fsync to raise ENOSPC
        with patch("models.os.fsync") as mock_fsync:
            mock_fsync.side_effect = OSError(errno.ENOSPC, "No space left on device")
            
            # The CLI should call sys.exit(1) on save error
            with pytest.raises(SystemExit) as excinfo:
                main()
            
            # Verify exit code is 1
            assert excinfo.value.code == 1
            
            # Verify error message was printed to stderr (or stdout via rich)
            captured = capsys.readouterr()
            assert "Error saving tasks" in captured.out
            assert "No space left on device" in captured.out

def test_write_failure_graceful_exit(capsys):
    """
    Test that the CLI exits gracefully when write itself fails.
    """
    with patch.object(sys, 'argv', ["todo_cli", "add", "Test Task"]):
        # Mocking the write method of the file object returned by fdopen
        with patch("models.os.fdopen") as mock_fdopen:
            mock_file = mock_fdopen.return_value.__enter__.return_value
            mock_file.write.side_effect = OSError(errno.EIO, "I/O error")
            
            with pytest.raises(SystemExit) as excinfo:
                main()
            
            assert excinfo.value.code == 1
            captured = capsys.readouterr()
            assert "Error saving tasks" in captured.out
            assert "I/O error" in captured.out
