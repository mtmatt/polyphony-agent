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
        subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True, text=True)
        # Check if there are changes to commit
        status = subprocess.run(["git", "status", "--porcelain"], cwd=path, capture_output=True, text=True, check=True)
        if not status.stdout.strip():
            return "No changes to commit."
        
        # Commit
        subprocess.run(["git", "commit", "-m", message], cwd=path, check=True, capture_output=True, text=True)
        return f"Committed: {message}"
    except subprocess.CalledProcessError as e:
        return f"Git error: {e.stderr or e.stdout or str(e)}"
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
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            return f"Output:\n{result.stdout}"
        else:
            return f"Error ({result.returncode}):\n{result.stderr or result.stdout}"
    except Exception as e:
        return f"Error running command: {e}"

import re

def get_repo_map(path: str = ".") -> str:
    """
    Returns a string representation of the project structure, including key symbols for Python files.
    """
    repo_map = []
    try:
        for root, dirs, files in os.walk(path):
            # Exclude hidden directories and __pycache__
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            
            level = root.replace(path, '').count(os.sep)
            indent = ' ' * 4 * level
            repo_map.append(f"{indent}{os.path.basename(root)}/")
            
            sub_indent = ' ' * 4 * (level + 1)
            for f in files:
                if f.startswith('.') or f.endswith('.pyc'):
                    continue
                
                file_path = os.path.join(root, f)
                repo_map.append(f"{sub_indent}{f}")
                
                # If it's a Python file, extract symbols
                if f.endswith('.py'):
                    try:
                        with open(file_path, 'r') as file_content:
                            content = file_content.read()
                            # Find classes and functions
                            classes = re.findall(r'^class\s+([a-zA-Z_][a-zA-Z0-9_]*)', content, re.MULTILINE)
                            functions = re.findall(r'^def\s+([a-zA-Z_][a-zA-Z0-9_]*)', content, re.MULTILINE)
                            
                            if classes or functions:
                                symbol_indent = ' ' * 4 * (level + 2)
                                if classes:
                                    repo_map.append(f"{symbol_indent}Classes: {', '.join(classes)}")
                                if functions:
                                    repo_map.append(f"{symbol_indent}Functions: {', '.join(functions)}")
                    except Exception:
                        pass # Skip if file cannot be read
        
        return "\n".join(repo_map)
    except Exception as e:
        return f"Error generating repo map: {e}"
