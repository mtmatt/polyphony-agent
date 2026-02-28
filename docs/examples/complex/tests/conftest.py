import sys
from pathlib import Path

# Add the project root to sys.path for test modules to find todo_cli
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
