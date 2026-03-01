from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import List, Optional, Any, Dict

class AgentTask(BaseModel):
    id: str
    description: str
    context: Optional[str] = None
    agent_type: Optional[str] = "executor" # executor, planner, etc.
    complexity: Optional[str] = None # simple, complex
    status: str = "pending" # pending, in-progress, completed, failed
    verification_command: Optional[str] = None # e.g., "pytest" or "python my_script.py"
    retry_count: int = 0
    max_retries: int = 2

class AgentAction(BaseModel):
    action_type: str  # thought, tool_call, tool_result
    content: str
    metadata: Optional[Dict[str, Any]] = None

class AgentResult(BaseModel):
    task_id: str
    success: bool
    agent_model: Optional[str] = None
    output: Optional[str] = None
    error: Optional[str] = None
    history: List[AgentAction] = []
    verification_output: Optional[str] = None
    duration: Optional[float] = None
    commit_hash: Optional[str] = None
    files_changed: List[str] = []

class BaseAgent(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str:
        pass

    @model_name.setter
    @abstractmethod
    def model_name(self, value: str):
        pass

    @property
    @abstractmethod
    def pro_model_name(self) -> str:
        pass

    @property
    @abstractmethod
    def flash_model_name(self) -> Optional[str]:
        pass

    @abstractmethod
    def execute_task(self, task: AgentTask, progress: Optional[Any] = None) -> AgentResult:
        pass

    @abstractmethod
    def receive_context(self, context: str):
        pass

    @abstractmethod
    def decompose_goal(self, goal: str) -> List[AgentTask]:
        pass

    @abstractmethod
    def classify_goal(self, goal: str) -> str:
        """
        Classifies a goal as 'simple' or 'complex'.
        Simple goals skip the decomposition phase.
        """
        pass

    def generate_commit_message(self, result: AgentResult) -> str:
        """
        Generates a descriptive commit message based on the task result.
        Default implementation returns a simple message.
        """
        return f"Task {result.task_id} completed"

AgentTask.model_rebuild()
AgentAction.model_rebuild()
AgentResult.model_rebuild()
