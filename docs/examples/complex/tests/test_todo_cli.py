import subprocess
import os
import json
import pytest
from pathlib import Path

# Path to the script
CLI_SCRIPT = Path(__file__).parent.parent / "todo_cli.py"

@pytest.fixture
def clean_tasks_file(tmp_path):
    """Fixture to ensure tasks.json is clean for each test."""
    tasks_file = tmp_path / "tasks.json"
    # The script currently hardcodes "tasks.json" in its current directory.
    return tasks_file

def run_cli(*args, cwd=None):
    """Helper to run the CLI and return output."""
    cmd = ["python3", str(CLI_SCRIPT)] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)

def test_add_task(tmp_path):
    """Test 'add' command adds a task."""
    result = run_cli("add", "Buy milk", cwd=tmp_path)
    # Check for success
    assert result.returncode == 0
    tasks_file = tmp_path / "tasks.json"
    assert tasks_file.exists()
    with open(tasks_file, "r") as f:
        data = json.load(f)
        assert any(t["description"] == "Buy milk" for t in data["tasks"])

def test_list_tasks(tmp_path):
    """Test 'list' command displays tasks."""
    # First add a task
    run_cli("add", "Buy milk", cwd=tmp_path)
    result = run_cli("list", cwd=tmp_path)
    assert result.returncode == 0
    # Check for output
    assert "Buy milk" in result.stdout
    assert "ID" in result.stdout or "id" in result.stdout

def test_done_task(tmp_path):
    """Test 'done' command marks task as complete."""
    run_cli("add", "Buy milk", cwd=tmp_path)
    # Assuming ID 1 for the first task
    result = run_cli("done", "1", cwd=tmp_path)
    assert result.returncode == 0
    tasks_file = tmp_path / "tasks.json"
    with open(tasks_file, "r") as f:
        data = json.load(f)
        task = next(t for t in data["tasks"] if t["id"] == 1)
        assert task["completed"] is True

def test_remove_task(tmp_path):
    """Test 'remove' command deletes a task."""
    run_cli("add", "Buy milk", cwd=tmp_path)
    result = run_cli("remove", "1", cwd=tmp_path)
    assert result.returncode == 0
    tasks_file = tmp_path / "tasks.json"
    with open(tasks_file, "r") as f:
        data = json.load(f)
        assert len(data["tasks"]) == 0

def test_missing_json_creation(tmp_path):
    """Test that tasks.json is created if missing when running list."""
    tasks_file = tmp_path / "tasks.json"
    if tasks_file.exists():
        os.remove(tasks_file)
    run_cli("list", cwd=tmp_path)
    assert tasks_file.exists()
