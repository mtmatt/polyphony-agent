import subprocess
import os
import re
import ast
from typing import Optional, List

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

def git_commit(message: str, path: str = ".") -> Dict[str, Any]:
    """
    Stages all changes and commits with the given message.
    Returns a dictionary with success, message, and optionally commit_hash.
    """
    try:
        # Stage all changes
        subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True, text=True)
        # Check if there are changes to commit
        status = subprocess.run(["git", "status", "--porcelain"], cwd=path, capture_output=True, text=True, check=True)
        if not status.stdout.strip():
            return {"success": True, "message": "No changes to commit."}
        
        # Commit
        subprocess.run(["git", "commit", "-m", message], cwd=path, check=True, capture_output=True, text=True)
        
        # Get the commit hash
        rev_res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True, check=True)
        commit_hash = rev_res.stdout.strip()
        
        return {
            "success": True, 
            "message": f"Committed: {message}",
            "commit_hash": commit_hash
        }
    except subprocess.CalledProcessError as e:
        return {
            "success": False, 
            "message": f"Git error: {e.stderr or e.stdout or str(e)}"
        }
    except Exception as e:
        return {
            "success": False, 
            "message": f"Error during git commit: {e}"
        }

def git_get_modified_files(path: str = ".") -> List[str]:
    """
    Returns a list of files modified in the current working tree.
    """
    try:
        # Use git status to get staged and unstaged changes
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True
        )
        files = []
        for line in res.stdout.splitlines():
            # Line format is 'XY path' where X is staged and Y is unstaged
            # Extract path, which starts at index 3
            files.append(line[3:].strip())
        return list(set(files))
    except Exception:
        return []

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

def extract_relevant_dirs(text: str, path: str = ".") -> List[str]:
    """
    Extracts potential directory names from text that exist in the given path.
    """
    relevant = []
    try:
        # Get all directories (excluding hidden and __pycache__)
        all_dirs = []
        for root, dirs, _ in os.walk(path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            rel_root = os.path.relpath(root, path)
            if rel_root != '.':
                all_dirs.append(rel_root)
        
        text_lower = text.lower()
        for d in all_dirs:
            # Check if the directory name or the full relative path is in the text
            if d.lower() in text_lower or os.path.basename(d).lower() in text_lower:
                relevant.append(d)
    except Exception:
        pass
    return relevant

def get_repo_map(path: str = ".", include_only: Optional[List[str]] = None) -> str:
    """
    Returns a string representation of the project structure, including key symbols for Python files.
    """
    repo_map = []
    try:
        for root, dirs, files in os.walk(path):
            # Exclude hidden directories and __pycache__
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            
            rel_root = os.path.relpath(root, path)
            
            # Task-based directory filtering
            if include_only and rel_root != '.':
                is_relevant = False
                for pattern in include_only:
                    if rel_root.startswith(pattern) or pattern.startswith(rel_root):
                        is_relevant = True
                        break
                if not is_relevant:
                    dirs[:] = []
                    continue

            level = 0 if rel_root == '.' else rel_root.count(os.sep) + 1
            indent = ' ' * 4 * level
            display_name = os.path.basename(root) if rel_root != '.' else os.path.basename(os.path.abspath(path))
            repo_map.append(f"{indent}{display_name}/")
            
            sub_indent = ' ' * 4 * (level + 1)
            for f in files:
                if f.startswith('.') or f.endswith('.pyc'):
                    continue
                
                file_path = os.path.join(root, f)
                repo_map.append(f"{sub_indent}{f}")
                
                # If it's a Python file, extract symbols using AST
                if f.endswith('.py'):
                    try:
                        with open(file_path, 'r', encoding='utf-8') as file_content:
                            tree = ast.parse(file_content.read())
                            
                            classes = []
                            functions = []
                            
                            for node in tree.body:
                                if isinstance(node, ast.ClassDef):
                                    classes.append(node.name)
                                    # Include methods in the same functions list for simplicity in repo map
                                    for subnode in node.body:
                                        if isinstance(subnode, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                            functions.append(subnode.name)
                                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                    functions.append(node.name)
                            
                            if classes or functions:
                                symbol_indent = ' ' * 4 * (level + 2)
                                if classes:
                                    repo_map.append(f"{symbol_indent}Classes: {', '.join(classes)}")
                                if functions:
                                    repo_map.append(f"{symbol_indent}Functions: {', '.join(functions)}")
                    except Exception:
                        pass # Skip if file cannot be read or parsed
        
        return "\n".join(repo_map)
    except Exception as e:
        return f"Error generating repo map: {e}"
