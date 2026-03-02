import json
import requests
from typing import List, Optional, Any, Dict
from .agent import BaseAgent, AgentTask, AgentResult, TokenUsage, AgentAction, CollaborativePlan, PlanReview, AgentRole, ReviewComment
from .utils import extract_json

class OllamaAgent(BaseAgent):
    """Agent that uses a local Ollama server for inference."""
    
    def __init__(self, model_name: str = "llama3", base_url: str = "http://localhost:11434"):
        super().__init__()
        self._model_name = model_name
        self._pro_model_name = model_name
        self._flash_model_name = model_name
        self.base_url = base_url
        self.context = ""

    @property
    def model_name(self) -> str:
        return self._model_name

    @model_name.setter
    def model_name(self, value: str):
        self._model_name = value

    @property
    def pro_model_name(self) -> str:
        return self._pro_model_name

    @property
    def flash_model_name(self) -> Optional[str]:
        return self._flash_model_name

    def receive_context(self, context: str):
        self.context = context

    def _call_ollama(self, prompt: str, system: Optional[str] = None) -> str:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False
        }
        if system:
            payload["system"] = system
            
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        return response.json().get("response", "")

    def classify_goal(self, goal: str) -> str:
        prompt = (
            f"Classify the following goal as 'simple' or 'complex'. "
            f"Goal: '{goal}'. Output only the word 'simple' or 'complex'."
        )
        try:
            response = self._call_ollama(prompt, system="You are a helpful assistant.")
            if "complex" in response.lower():
                return "complex"
            return "simple"
        except Exception:
            return "simple"

    def decompose_goal(self, goal: str) -> List[AgentTask]:
        prompt = (
            f"Decompose the goal: '{goal}' into a JSON list of tasks. "
            'JSON structure: {"tasks": [{"id": "task1", "description": "..."}]}'
        )
        try:
            response = self._call_ollama(prompt)
            data = extract_json(response)
            if data and "tasks" in data:
                return [AgentTask.model_validate(t) for t in data["tasks"]]
        except Exception:
            pass
        return []

    def execute_task(self, task: AgentTask, progress: Optional[Any] = None) -> AgentResult:
        prompt = f"""Perform task: {task.description}
Context: {task.context or ''}
Repo: {self.context}"""
        try:
            response = self._call_ollama(prompt)
            return AgentResult(
                task_id=task.id,
                success=True,
                output=response,
                agent_model=self.model_name,
                history=[AgentAction(action_type="thought", content=response)]
            )
        except Exception as e:
            return AgentResult(
                task_id=task.id,
                success=False,
                error=str(e),
                agent_model=self.model_name,
                history=[AgentAction(action_type="thought", content=f"Error calling Ollama: {str(e)}")]
            )

    def review_plan(self, plan: CollaborativePlan, role: AgentRole) -> PlanReview:
        tasks_summary = "\n".join(f"- [{t.id}] {t.description}" for t in plan.tasks)
        prompt = (
            f"You are a {role.value} reviewing an engineering plan.\n"
            f"Goal: {plan.goal}\n\nTasks:\n{tasks_summary}\n\n"
            "Output a JSON object: "
            '{"approved": true/false, "confidence_score": 0.0-1.0, '
            '"comments": [{"comment": "...", "severity": "info|warning|error|suggestion", '
            '"target_task_id": null, "suggested_changes": null}]}'
        )
        try:
            response = self._call_ollama(prompt)
            review_data = extract_json(response)
            if review_data:
                comments = [
                    ReviewComment(
                        reviewer_role=role,
                        comment=c.get("comment", ""),
                        severity=c.get("severity", "suggestion"),
                        target_task_id=c.get("target_task_id"),
                        suggested_changes=c.get("suggested_changes"),
                    )
                    for c in review_data.get("comments", [])
                ]
                return PlanReview(
                    original_plan_id=plan.goal,
                    reviewers=[role],
                    comments=comments,
                    approved=review_data.get("approved", False),
                    confidence_score=float(review_data.get("confidence_score", 0.5)),
                )
        except Exception:
            pass
        return PlanReview(
            original_plan_id=plan.goal,
            reviewers=[role],
            comments=[],
            approved=True,
            confidence_score=0.5,
        )
