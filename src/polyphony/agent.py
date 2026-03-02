from abc import ABC, abstractmethod
from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Any, Dict, Literal, Union
from enum import Enum
from .cost import TokenUsage


class AgentRole(str, Enum):
    """Specialized agent roles for collaborative multi-agent planning."""
    EXECUTOR = "executor"
    PLANNER = "planner"
    SECURITY_ARCHITECT = "security_architect"
    QA_SPECIALIST = "qa_specialist"
    SENIOR_DEVELOPER = "senior_developer"
    PERFORMANCE_EXPERT = "performance_expert"


class AgentTask(BaseModel):
    id: str
    description: str
    context: Optional[str] = None
    agent_type: Optional[str] = "executor"  # executor, planner, etc.
    agent_role: Optional[AgentRole] = Field(default=AgentRole.EXECUTOR, description="Specialized role for this task")
    complexity: Optional[str] = None  # simple, complex
    status: str = "pending"  # pending, in-progress, completed, failed
    verification_command: Optional[str] = None  # e.g., "pytest" or "python my_script.py"
    retry_count: int = 0
    max_retries: int = 2
    depends_on: List[str] = []  # List of task IDs that must be completed before this task
    dependencies: List[str] = []  # Backward compatibility

    @model_validator(mode="after")
    def sync_dependencies(self) -> "AgentTask":
        """Sync depends_on and dependencies."""
        if not self.depends_on and self.dependencies:
            self.depends_on = self.dependencies
        elif self.depends_on and not self.dependencies:
            self.dependencies = self.depends_on
        return self


class AgentAction(BaseModel):
    action_type: str  # thought, tool_call, tool_result
    content: str
    metadata: Optional[Dict[str, Any]] = None
    agent_role: Optional[AgentRole] = None  # Track which role performed this action


class ReviewComment(BaseModel):
    """A comment/review from a specialized agent on a plan or task."""
    reviewer_role: AgentRole
    comment: str
    severity: Literal["info", "warning", "error", "suggestion"] = "suggestion"
    target_task_id: Optional[str] = None
    suggested_changes: Optional[str] = None


class PlanReview(BaseModel):
    """Results of collaborative review on a plan."""
    original_plan_id: str
    reviewers: List[AgentRole]
    comments: List[ReviewComment]
    approved: bool = False
    confidence_score: float = Field(ge=0.0, le=1.0, default=0.0)
    consensus_reached: bool = False
    revision_count: int = 0


class AgentResult(BaseModel):
    task_id: str
    success: bool
    agent_model: Optional[str] = None
    output: Optional[str] = None
    error: Optional[str] = None
    history: List[AgentAction] = []
    verification_output: Optional[str] = None
    duration: Optional[float] = None
    usage: Optional[TokenUsage] = None
    commit_hash: Optional[str] = None
    files_changed: List[str] = []


class CollaborativePlan(BaseModel):
    """A plan that has been created and reviewed by multiple specialized agents."""
    goal: str
    tasks: List[AgentTask]
    reviews: List[PlanReview] = []
    reviewer_assignments: Dict[AgentRole, List[str]] = {}  # Maps roles to task IDs they should review
    final_approved: bool = False
    created_at: Optional[str] = None


class ConsensusVote(BaseModel):
    """A vote from an agent role during consensus building."""
    role: AgentRole
    approved: bool
    confidence: float = Field(ge=0.0, le=1.0)
    justification: Optional[str] = None


class BaseAgent(ABC):
    def __init__(self):
        self.usage_by_model: Dict[str, TokenUsage] = {}

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

    @abstractmethod
    def review_plan(self, plan: CollaborativePlan, role: AgentRole) -> PlanReview:
        """
        Review a plan for a specific specialized role (e.g., Security Architect, QA Specialist).
        Returns a PlanReview with comments and approval status.
        """
        pass

    def generate_commit_message(self, result: AgentResult) -> str:
        """Generates a descriptive commit message based on the task result.
        Default implementation returns a simple message.
        """
        return f"Task {result.task_id} completed"


class SpecializedAgent(BaseAgent):
    """A specialized agent that focuses on a specific role in collaborative planning."""
    
    def __init__(self, role: AgentRole):
        super().__init__()
        self.role = role

    def review_task(self, task: AgentTask) -> ReviewComment:
        """Review a specific task within a plan based on the agent's specialization."""
        comments_by_role = {
            AgentRole.SECURITY_ARCHITECT: "Reviewing for security vulnerabilities...",
            AgentRole.QA_SPECIALIST: "Checking test coverage and verification steps...",
            AgentRole.SENIOR_DEVELOPER: "Evaluating architectural soundness...",
            AgentRole.PERFORMANCE_EXPERT: "Analyzing performance implications...",
        }
        return ReviewComment(
            reviewer_role=self.role,
            comment=comments_by_role.get(self.role, "General review completed."),
            severity="suggestion",
            target_task_id=task.id
        )

    def should_participate(self, goal: str, tasks: List[AgentTask]) -> bool:
        """Determine if this specialized agent should participate in the planning."""
        participation_keywords = {
            AgentRole.SECURITY_ARCHITECT: ["security", "auth", "password", "encrypt", "token"],
            AgentRole.QA_SPECIALIST: ["test", "verify", "validate", "quality"],
            AgentRole.SENIOR_DEVELOPER: ["refactor", "architecture", "design", "complex"],
            AgentRole.PERFORMANCE_EXPERT: ["performance", "optimize", "cache", "load", "slow"],
        }
        keywords = participation_keywords.get(self.role, [])
        text = goal.lower()
        return any(kw in text for kw in keywords)


# Rebuild models
AgentTask.model_rebuild()
AgentAction.model_rebuild()
AgentResult.model_rebuild()
ReviewComment.model_rebuild()
PlanReview.model_rebuild()
CollaborativePlan.model_rebuild()
ConsensusVote.model_rebuild()
