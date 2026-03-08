import subprocess
import os
import re
import ast
import json
import inspect
from .token_estimation import estimate_tokens

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

def run_command(command: str, sandbox: bool = False) -> str:
    """
    Runs a shell command and returns output.
    If sandbox is True, it will attempt to run in a restricted environment if supported.
    """
    if sandbox:
        raise NotImplementedError("Secure sandboxing is not yet implemented. Use sandbox=False for now.")
    
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
    Also identifies parent directories of filenames mentioned in the text.
    """
    relevant = set()
    try:
        # Get all directories and files (excluding hidden and __pycache__)
        all_dirs = []
        all_files = {} # name -> rel_path
        
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            rel_root = os.path.relpath(root, path)
            
            if rel_root != '.':
                all_dirs.append(rel_root)
            
            for f in files:
                if not f.startswith('.'):
                    rel_f = os.path.join(rel_root, f) if rel_root != '.' else f
                    if f not in all_files:
                        all_files[f] = []
                    all_files[f].append(rel_f)
        
        text_lower = text.lower()
        
        # 1. Match directory names directly
        for d in all_dirs:
            if d.lower() in text_lower or os.path.basename(d).lower() in text_lower:
                relevant.add(d)
        
        # 2. Match filenames and add their parent directories
        for f_name, paths in all_files.items():
            if f_name.lower() in text_lower:
                for p in paths:
                    parent = os.path.dirname(p)
                    if parent and parent != '.':
                        relevant.add(parent)
                    elif not parent or parent == '.':
                        # If it's in root, we might want to include root (which is always included in map usually)
                        pass

        # 3. Common keyword mappings
        kw_map = {
            "test": ["tests", "test", "__tests__", "spec"],
            "doc": ["docs", "doc", "documentation", "wiki"],
            "src": ["src", "lib", "app", "cmd", "pkg", "internal"],
            "requirement": ["docs", "requirements.txt", "package.json", "go.mod", "Cargo.toml", "pom.xml"],
            "config": ["config", "settings", "options", "env"],
            "web": ["web", "frontend", "ui", "public", "static", "assets"],
            "api": ["api", "server", "backend", "routes", "controllers"]
        }
        
        for kw, targets in kw_map.items():
            if kw in text_lower:
                for target in targets:
                    for d in all_dirs:
                        if target in d.lower() or target in os.path.basename(d).lower():
                            relevant.add(d)
                            
    except Exception:
        pass
    return list(relevant)

def extract_json(text: str) -> Optional[dict]:
    """
    Robustly extracts a JSON object from text that may contain other content.
    Handles markdown code blocks and introductory/concluding text.
    """
    # 1. Try to find content within triple backticks
    json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # 2. Try to find anything between { and }
    # Use non-greedy match and find all to handle multiple JSON-like objects
    # but we usually want the largest/outermost one if possible.
    # A simple approach is finding the first '{' and the last '}'
    start = text.find('{')
    end = text.rfind('}') + 1
    if start != -1 and end != -1:
        json_str = text[start:end]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # If direct parsing fails, try to clean it up (e.g., stripping markdown if any)
            # This is a fallback for very messy outputs
            cleaned = re.sub(r"```[a-zA-Z]*", "", json_str).strip()
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                pass
    
    return None

from .ast_parsing import get_file_symbols

def get_repo_map(path: str = ".", include_only: Optional[List[str]] = None) -> str:
    """
    Returns a string representation of the project structure, including key symbols for multiple languages.
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
                    if rel_root == pattern or rel_root.startswith(pattern + os.sep) or pattern.startswith(rel_root + os.sep):
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
                
                # Extract symbols using the multi-language parser
                symbols = get_file_symbols(file_path)
                if symbols:
                    symbol_indent = ' ' * 4 * (level + 2)
                    for sym in symbols:
                        repo_map.append(f"{symbol_indent}{sym}")
        
        return "\n".join(repo_map)
    except Exception as e:
        return f"Error generating repo map: {e}"
