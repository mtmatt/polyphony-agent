from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import List, Optional, Any

class AgentTask(BaseModel):
    id: str
    description: str
    context: Optional[str] = None
    agent_type: Optional[str] = "executor" # executor, planner, etc.
    status: str = "pending" # pending, in-progress, completed, failed
    verification_command: Optional[str] = None # e.g., "pytest" or "python my_script.py"
    retry_count: int = 0
    max_retries: int = 2

class AgentResult(BaseModel):
    task_id: str
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None

class BaseAgent(ABC):
    @abstractmethod
    def execute_task(self, task: AgentTask) -> AgentResult:
        pass

    @abstractmethod
    def receive_context(self, context: str):
        pass

    @abstractmethod
    def decompose_goal(self, goal: str) -> List[AgentTask]:
        pass
