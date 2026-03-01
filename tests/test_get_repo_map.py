import os
import shutil
import pytest
from polyphony.utils import get_repo_map, extract_relevant_dirs

@pytest.fixture
def temp_project(tmp_path):
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    
    # Create structure
    src_dir = project_dir / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("class Main:\n    def run(self):\n        pass\n\ndef helper():\n    pass")
    
    tests_dir = project_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_main.py").write_text("def test_run():\n    pass")
    
    docs_dir = project_dir / "docs"
    docs_dir.mkdir()
    (docs_dir / "index.md").write_text("# Hello")
    
    return project_dir

def test_get_repo_map_basic(temp_project):
    repo_map = get_repo_map(str(temp_project))
    # print(repo_map)
    assert "src/" in repo_map
    assert "main.py" in repo_map
    assert "Classes: Main" in repo_map
    assert "Functions: run, helper" in repo_map
    assert "tests/" in repo_map
    assert "test_main.py" in repo_map
    assert "Functions: test_run" in repo_map
    assert "docs/" in repo_map
    assert "index.md" in repo_map

def test_get_repo_map_filtering(temp_project):
    repo_map = get_repo_map(str(temp_project), include_only=["src"])
    # print(repo_map)
    assert "src/" in repo_map
    assert "main.py" in repo_map
    assert "tests/" not in repo_map
    assert "docs/" not in repo_map

def test_get_repo_map_ast_symbols(temp_project):
    repo_map = get_repo_map(str(temp_project))
    # print(repo_map)
    # AST should find 'run' even though it's indented
    assert "Functions: run, helper" in repo_map

def test_extract_relevant_dirs(temp_project):
    # Test matching directory name
    relevant = extract_relevant_dirs("Fix something in src directory", str(temp_project))
    assert "src" in relevant
    
    # Test matching file path parts
    relevant = extract_relevant_dirs("Update tests/test_main.py", str(temp_project))
    assert "tests" in relevant

    # Test no match
    relevant = extract_relevant_dirs("Hello world", str(temp_project))
    assert relevant == []
