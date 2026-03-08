import os
import subprocess
import shutil
import pytest
from polyphony.utils import git_commit, is_git_repo

@pytest.fixture
def temp_repo(tmp_path):
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    
    # Initialize a git repo
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True, capture_output=True)
    
    return repo_dir

def test_is_git_repo(temp_repo):
    assert is_git_repo(str(temp_repo)) is True
    
    non_repo = temp_repo.parent / "non_repo"
    non_repo.mkdir()
    # Note: if the temp directory is inside a git repo, this might still be true.
    # But tmp_path usually is not.
    # To be sure, we can check if it's truly not a repo.
    # Actually, is_git_repo uses --is-inside-work-tree which is true if any parent is a repo.
    # pytest's tmp_path is usually in /tmp or similar, which shouldn't be a git repo.
    assert is_git_repo(str(non_repo)) == (subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=non_repo, capture_output=True).returncode == 0)

def test_git_commit_success(temp_repo):
    file_path = temp_repo / "test.txt"
    file_path.write_text("content")
    
    result = git_commit("Test commit", path=str(temp_repo))
    assert result["success"] is True
    assert "Committed: Test commit" in result["message"]
    
    # Verify commit
    log = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=temp_repo, capture_output=True, text=True, check=True)
    assert log.stdout.strip() == "Test commit"

def test_git_commit_no_changes(temp_repo):
    result = git_commit("No changes", path=str(temp_repo))
    assert result["success"] is True
    assert "No changes to commit." in result["message"]

def test_git_commit_error(tmp_path):
    # Directory that is NOT a git repo
    non_repo = tmp_path / "not_a_repo"
    non_repo.mkdir()
    
    # We need to make sure this directory is NOT inside a parent git repo.
    # tmp_path should be safe.
    
    result = git_commit("Failing commit", path=str(non_repo))
    assert result["success"] is False
    assert "Git error:" in result["message"]
    assert "not a git repository" in result["message"]

def test_run_command_sandbox_not_implemented():
    """Verify that sandbox=True raises NotImplementedError (Issue 4)."""
    from polyphony.utils import run_command
    with pytest.raises(NotImplementedError) as excinfo:
        run_command("ls", sandbox=True)
    assert "Secure sandboxing is not yet implemented" in str(excinfo.value)

def test_run_command_normal():
    """Verify that run_command works without sandbox."""
    from polyphony.utils import run_command
    result = run_command("echo 'hello'")
    assert "hello" in result
    assert "Output:" in result

def test_estimate_tokens_fallback():
    """Verify that estimate_tokens is still available and working."""
    from polyphony.utils import estimate_tokens
    tokens = estimate_tokens("hello world")
    assert tokens > 0
