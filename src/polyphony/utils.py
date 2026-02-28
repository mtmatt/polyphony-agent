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

def should_include_repo_map(goal: str) -> bool:
    """
    Returns True if the goal seems to require a repo map.
    """
    keywords = ["file", "list", "search", "structure", "find", "read", "write", "modify", "edit", "code", "directory", "folder", "project"]
    goal_lower = goal.lower()
    return any(kw in goal_lower for kw in keywords)

def write_file(path: str, content: str) -> str:
    """
    Writes content to a file.
    """
    try:
        dir_name = os.path.dirname(path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return f"Successfully wrote to {path}"
    except Exception as e:
        return f"Error writing to {path}: {e}"

def replace_text(path: str, old: str, new: str) -> str:
    """
    Replaces old text with new text in a file.
    """
    try:
        with open(path, "r") as f:
            content = f.read()
        
        if old not in content:
            return f"Error: '{old}' not found in {path}"
        
        new_content = content.replace(old, new)
        with open(path, "w") as f:
            f.write(new_content)
        return f"Successfully updated {path}"
    except Exception as e:
        return f"Error updating {path}: {e}"

def run_command(command: str) -> str:
    """
    Runs a shell command and returns output.
    """
    try:
        result = subprocess.run(command.split(), capture_output=True, text=True)
        if result.returncode == 0:
            return f"Output:\n{result.stdout}"
        else:
            return f"Error ({result.returncode}):\n{result.stderr or result.stdout}"
    except Exception as e:
        return f"Error running command: {e}"

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
