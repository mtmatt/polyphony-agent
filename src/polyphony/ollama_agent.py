"""Ollama agent implementation with tool-calling and MCP support."""

import json
import httpx
import re
import os
from typing import Optional, Any, List, Dict
from pydantic import BaseModel
from rich.console import Console

from .agent import (
    AgentTask,
    AgentResult,
    BaseAgent,
    AgentAction,
    AgentRole,
    ReviewComment,
    PlanReview,
    CollaborativePlan,
    ConsensusVote,
    TokenUsage
)
from .tool_executor import ToolExecutor
from .logging import get_logger
from .utils import extract_json
from .token_estimation import estimate_tokens, estimate_messages_tokens

logger = get_logger(__name__)
console = Console()

class OllamaAgent(BaseAgent):
    """Agent that uses a local Ollama server for inference with tool-calling support."""

    def __init__(
        self,
        model_name: str = "llama3.1",
        pro_model_name: Optional[str] = None,
        flash_model_name: Optional[str] = None,
        base_url: str = "http://localhost:11434",
        mcp_servers: Optional[list] = None,
        sandbox: bool = False,
        **kwargs
    ):
        super().__init__()
        self._model_name = model_name
        self._pro_model_name = pro_model_name or model_name
        self._flash_model_name = flash_model_name or model_name
        self.base_url = base_url.rstrip("/")
        self.sandbox = sandbox
        self.tool_executor = ToolExecutor(mcp_servers, sandbox)
        self.context = ""

        logger.info(
            "OllamaAgent initialized",
            model=model_name,
            base_url=base_url,
            sandbox=sandbox,
        )

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
    def flash_model_name(self) -> str:
        return self._flash_model_name

    def _chat_with_tools(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        format: Optional[str] = None,
        temperature: float = 0.7,
    ) -> dict:
        """Send a chat request to Ollama with optional tool support and structured output."""
        url = f"{self.base_url}/api/chat"
        
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }

        if tools:
            payload["tools"] = tools
        
        if format:
            payload["format"] = format

        with httpx.Client() as client:
            response = client.post(url, json=payload, timeout=300.0)
            response.raise_for_status()
            result = response.json()
            self._extract_usage(result, messages)
            return result

    def _extract_usage(self, response: dict, messages: list[dict]):
        """Extract or estimate token usage from Ollama response."""
        prompt_tokens = response.get("prompt_eval_count", 0)
        completion_tokens = response.get("eval_count", 0)

        # Estimate prompt tokens if not provided
        if prompt_tokens == 0:
            prompt_tokens = estimate_messages_tokens(messages)
            logger.debug("Estimated prompt tokens", tokens=prompt_tokens)
        
        # Estimate completion tokens if not provided
        if completion_tokens == 0:
            content = response.get("message", {}).get("content", "")
            completion_tokens = estimate_tokens(content)
            logger.debug("Estimated completion tokens", tokens=completion_tokens)

        total_tokens = prompt_tokens + completion_tokens
        logger.debug("Total tokens usage", total=total_tokens, model=self.model_name)

        if self.model_name not in self.usage_by_model:
            self.usage_by_model[self.model_name] = TokenUsage()
        
        self.usage_by_model[self.model_name].prompt_tokens += prompt_tokens
        self.usage_by_model[self.model_name].completion_tokens += completion_tokens
        self.usage_by_model[self.model_name].total_tokens += total_tokens

    def receive_context(self, context: str):
        """Receive and store context for the next task."""
        logger.debug("Received context", context_length=len(context))
        self.context = context

    def classify_goal(self, goal: str) -> str:
        """Classify the goal type."""
        prompt = (
            f"Classify the following goal as 'simple' (one-off action, direct query, or single-step task) "
            f"or 'complex' (multi-step task, requires planning, file modifications, or research). "
            f"Goal: '{goal}'. "
            "Output your answer in JSON format: {\"classification\": \"simple\"} or {\"classification\": \"complex\"}."
        )
        
        try:
            response = self._chat_with_tools(
                messages=[{"role": "user", "content": prompt}],
                format="json"
            )
            content = response.get("message", {}).get("content", "").strip()
            data = json.loads(content)
            classification = data.get("classification", "simple").lower()
            if "complex" in classification:
                return "complex"
            return "simple"
        except Exception as e:
            logger.error("classification_failed", error=str(e))
            return "simple"

    def decompose_goal(self, goal: str) -> list[AgentTask]:
        """Decompose a goal into tasks."""
        prompt = (
            f"Given the goal: '{goal}', decompose it into a sequence of sub-tasks. "
            f"Current context: '{self.context}'. "
            "Output the tasks in a JSON format matching this structure: "
            "{\"tasks\": [{\"id\": \"task1\", \"description\": \"...\", \"context\": \"...\", \"agent_type\": \"...\", \"verification_command\": \"...\", \"depends_on\": [\"task_id_1\"]}]}. "
            "agent_type should be 'planner' or 'executor'. "
            "Only output the JSON object, nothing else."
        )
        
        try:
            response = self._chat_with_tools(
                messages=[{"role": "user", "content": prompt}],
                format="json"
            )
            content = response.get("message", {}).get("content", "")
            task_data = json.loads(content)
            return [AgentTask(**t) for t in task_data.get("tasks", [])]
        except Exception as e:
            logger.error("decomposition_failed", error=str(e))
            return []

    def execute_task(
        self,
        task: AgentTask,
        progress: Optional[Any] = None,
    ) -> AgentResult:
        """Execute a task using Ollama with tool-calling support."""
        self.tool_executor.start()
        available_tools = self.tool_executor.get_provider_tools("ollama")

        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        f"You are a helpful assistant. System Context:\n{self.context}\n"
                        "Think step by step and use tools as needed to accomplish the goal."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Task: {task.description}\nContext: {task.context}",
                },
            ]

            max_iterations = 10
            iteration = 0
            history = []

            while iteration < max_iterations:
                iteration += 1

                try:
                    response = self._chat_with_tools(
                        messages=messages,
                        tools=available_tools if available_tools else None,
                    )
                except Exception as e:
                    logger.error("Ollama API error", error=str(e))
                    return AgentResult(
                        task_id=task.id,
                        success=False,
                        error=f"Ollama API error: {e}",
                        history=history,
                    )

                message = response.get("message", {})
                content = message.get("content", "")
                tool_calls = message.get("tool_calls", [])

                if content:
                    history.append(AgentAction(action_type="thought", content=content))

                # If there are tool calls, execute them and continue the conversation
                if tool_calls:
                    messages.append(message)

                    for tool_call in tool_calls:
                        func_name = tool_call.get("function", {}).get("name", "unknown")
                        args = tool_call.get("function", {}).get("arguments", {})
                        
                        tool_result, success, action = self.tool_executor.execute(func_name, args)
                        history.append(action)
                        history.append(AgentAction(action_type="tool_result", content=tool_result))

                        messages.append({
                            "role": "tool",
                            "name": func_name,
                            "content": tool_result,
                        })

                    continue

                return AgentResult(
                    task_id=task.id,
                    success=True,
                    output=content,
                    history=history,
                    usage=self.usage_by_model.get(self.model_name)
                )

            return AgentResult(
                task_id=task.id,
                success=False,
                output="Maximum number of tool call iterations reached.",
                history=history,
            )

        finally:
            self.tool_executor.stop()

    def generate_commit_message(self, result: AgentResult) -> str:
        """Generates a descriptive commit message based on the task result."""
        prompt = (
            f"Generate a concise, descriptive Git commit message for the following task output.\n"
            f"Task Output: {result.output}\n"
            f"Verification Output: {result.verification_output}\n"
            "Output only the commit message in a JSON object: {\"commit_message\": \"...\"}."
        )
        
        try:
            response = self._chat_with_tools(
                messages=[{"role": "user", "content": prompt}],
                format="json"
            )
            content = response.get("message", {}).get("content", "").strip()
            data = json.loads(content)
            return data.get("commit_message", f"Task {result.task_id} completed")
        except Exception:
            return super().generate_commit_message(result)

    def review_plan(self, plan: CollaborativePlan, role: AgentRole) -> PlanReview:
        """Review a plan from a specific role perspective."""
        tasks_summary = "\n".join(f"- [{t.id}] {t.description}" for t in plan.tasks)
        prompt = (
            f"You are a {role.value} reviewing an engineering plan.\n"
            f"Goal: {plan.goal}\n\n"
            f"Tasks:\n{tasks_summary}\n\n"
            "Review the plan from your specialized perspective. "
            "Output a JSON object with this structure:\n"
            '{"approved": true/false, "confidence_score": 0.0-1.0, '
            '"comments": [{"comment": "...", "severity": "info|warning|error|suggestion", '
            '"target_task_id": "task_id_or_null", "suggested_changes": "..._or_null"}]}\n'
            "Only output the JSON object, nothing else."
        )

        try:
            response = self._chat_with_tools(
                messages=[{"role": "user", "content": prompt}],
                format="json"
            )
            content = response.get("message", {}).get("content", "")
            review_data = json.loads(content)
            
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
        except Exception as e:
            logger.error("review_plan_failed", error=str(e))

        return PlanReview(
            original_plan_id=plan.goal,
            reviewers=[role],
            comments=[],
            approved=True,
            confidence_score=0.5,
        )
