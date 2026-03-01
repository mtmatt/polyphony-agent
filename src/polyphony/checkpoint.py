from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime
import json
import os
from .agent import AgentTask, AgentResult
from .cost import CostTracker

class RunCheckpoint(BaseModel):
    run_id: str
    goal: str
    context: str
    tasks_by_goal: Dict[str, List[AgentTask]] = Field(default_factory=dict)
    results: List[AgentResult] = Field(default_factory=list)
    result_tasks: List[AgentTask] = Field(default_factory=list)
    cost_tracker: CostTracker
    start_time: datetime
    is_simple: bool = False
    last_updated: datetime = Field(default_factory=datetime.now)
    config_overrides: Dict[str, Any] = Field(default_factory=dict)

    def save(self, directory: str = ".polyphony/checkpoints") -> str:
        os.makedirs(directory, exist_ok=True)
        filename = f"checkpoint-{self.run_id}.json"
        path = os.path.join(directory, filename)
        
        # Update last_updated before saving
        self.last_updated = datetime.now()
        
        with open(path, "w") as f:
            f.write(self.model_dump_json(indent=2))
        return path

    @classmethod
    def load(cls, run_id: str, directory: str = ".polyphony/checkpoints") -> Optional["RunCheckpoint"]:
        filename = f"checkpoint-{run_id}.json"
        path = os.path.join(directory, filename)
        if not os.path.exists(path):
            return None
        with open(path, "r") as f:
            return cls.model_validate_json(f.read())

    @classmethod
    def list_checkpoints(cls, directory: str = ".polyphony/checkpoints") -> List[Dict[str, Any]]:
        if not os.path.exists(directory):
            return []
        
        checkpoints = []
        for filename in os.listdir(directory):
            if filename.startswith("checkpoint-") and filename.endswith(".json"):
                run_id = filename[len("checkpoint-"):-len(".json")]
                path = os.path.join(directory, filename)
                try:
                    with open(path, "r") as f:
                        data = json.load(f)
                        # Count total completed tasks across all goals
                        tasks_completed = 0
                        tasks_by_goal = data.get("tasks_by_goal", {})
                        for tasks in tasks_by_goal.values():
                            tasks_completed += sum(1 for t in tasks if t.get("status") == "completed")
                        
                        checkpoints.append({
                            "run_id": run_id,
                            "goal": data.get("goal", "Unknown"),
                            "last_updated": data.get("last_updated", "Unknown"),
                            "tasks_completed": tasks_completed
                        })
                except Exception:
                    continue
        
        # Sort by last_updated descending
        checkpoints.sort(key=lambda x: x["last_updated"], reverse=True)
        return checkpoints
