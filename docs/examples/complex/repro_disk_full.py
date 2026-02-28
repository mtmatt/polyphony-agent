import errno
import sys
from unittest.mock import patch
from todo_cli import main

# Set up CLI arguments: add "Test Task"
sys.argv = ["todo_cli.py", "add", "Test Task"]

# Patch models.os.fsync to raise ENOSPC
with patch("models.os.fsync") as mock_fsync:
    mock_fsync.side_effect = OSError(errno.ENOSPC, "No space left on device")
    try:
        main()
    except SystemExit as e:
        print(f"Exited with code: {e.code}")
    except Exception as e:
        print(f"Caught exception: {e}")
