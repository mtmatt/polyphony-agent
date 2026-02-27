import subprocess
import os
from typing import Optional

def is_git_repo(path: str = ".") -> bool:
    try:
        subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=path,
            capture_output=True,
            check=True
        )
        return True
    except subprocess.CalledProcessError:
        return False

def git_commit(message: str, path: str = ".") -> Optional[str]:
    """
    Stages all changes and commits with the given message.
    """
    try:
        # Stage all changes
        subprocess.run(["git", "add", "."], cwd=path, check=True)
        # Check if there are changes to commit
        status = subprocess.run(["git", "status", "--porcelain"], cwd=path, capture_output=True, text=True, check=True)
        if not status.stdout.strip():
            return "No changes to commit."
        
        # Commit
        subprocess.run(["git", "commit", "-m", message], cwd=path, check=True, capture_output=True)
        return f"Committed: {message}"
    except subprocess.CalledProcessError as e:
        return f"Git error: {e.stderr}"
    except Exception as e:
        return f"Error during git commit: {e}"

def get_repo_map(path: str = ".") -> str:
    """
    Returns a simple string representation of the project structure.
    """
    try:
        # Use 'find' or similar to get a file list, excluding some common directories
        result = subprocess.run(
            ["find", ".", "-maxdepth", "3", "-not", "-path", "*/.*"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except Exception as e:
        return f"Error generating repo map: {e}"
