import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from .logging import get_logger

logger = get_logger(__name__)

@dataclass
class TaskMetric:
    task_id: str
    goal: str
    start_time: float
    end_time: Optional[float] = None
    success: bool = False
    model: Optional[str] = None
    duration: float = 0.0
    tokens_prompt: int = 0
    tokens_completion: int = 0

class MetricsCollector:
    def __init__(self):
        self.tasks: Dict[str, TaskMetric] = {}
        self.start_time = time.time()

    def start_task(self, task_id: str, goal: str, model: Optional[str] = None):
        self.tasks[task_id] = TaskMetric(
            task_id=task_id,
            goal=goal,
            start_time=time.time(),
            model=model
        )
        logger.info("task_started", task_id=task_id, goal=goal, model=model)

    def end_task(self, task_id: str, success: bool, tokens_prompt: int = 0, tokens_completion: int = 0):
        if task_id in self.tasks:
            metric = self.tasks[task_id]
            metric.end_time = time.time()
            metric.duration = metric.end_time - metric.start_time
            metric.success = success
            metric.tokens_prompt = tokens_prompt
            metric.tokens_completion = tokens_completion
            
            logger.info(
                "task_finished", 
                task_id=task_id, 
                success=success, 
                duration=metric.duration,
                tokens_prompt=tokens_prompt,
                tokens_completion=tokens_completion,
                total_tokens=tokens_prompt + tokens_completion
            )

    def get_summary(self) -> Dict[str, Any]:
        total_tasks = len(self.tasks)
        successful_tasks = sum(1 for t in self.tasks.values() if t.success)
        total_duration = sum(t.duration for t in self.tasks.values() if t.end_time)
        total_tokens = sum(t.tokens_prompt + t.tokens_completion for t in self.tasks.values())
        
        return {
            "total_tasks": total_tasks,
            "successful_tasks": successful_tasks,
            "success_rate": successful_tasks / total_tasks if total_tasks > 0 else 0,
            "total_duration": total_duration,
            "total_tokens": total_tokens,
            "avg_task_duration": total_duration / total_tasks if total_tasks > 0 else 0
        }

# Global collector
collector = MetricsCollector()
