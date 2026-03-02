import json
import os
from typing import List, Optional
from .agent import AgentTask

class WorkflowTemplate:
    def __init__(self, name: str, description: str, tasks: List[AgentTask]):
        self.name = name
        self.description = description
        self.tasks = tasks

    @classmethod
    def load_from_file(cls, path: str) -> "WorkflowTemplate":
        with open(path, "r") as f:
            data = json.load(f)
            tasks = [AgentTask.model_validate(t) for t in data.get("tasks", [])]
            return cls(
                name=data.get("name", "Unnamed Workflow"),
                description=data.get("description", ""),
                tasks=tasks
            )

def list_templates(directory: Optional[str] = None) -> List[str]:
    if directory is None:
        directory = os.path.join(os.path.dirname(__file__), "templates")
    
    if not os.path.exists(directory):
        return []
    
    return [os.path.splitext(f)[0] for f in os.listdir(directory) if f.endswith(".json")]

def get_template(name: str, directory: Optional[str] = None) -> Optional[WorkflowTemplate]:
    if directory is None:
        directory = os.path.join(os.path.dirname(__file__), "templates")
    
    path = os.path.join(directory, f"{name}.json")
    if os.path.exists(path):
        return WorkflowTemplate.load_from_file(path)
    return None
