"""
Agent implementation that drives the Claude CLI (`claude`).

The `claude` CLI (Claude Code) is invoked in non-interactive print mode:
    claude -p "<prompt>" --model <model> --output-format stream-json \
           --dangerously-skip-permissions

Stream-JSON lines follow the Messages API event shapes:
  {"type": "assistant", "message": {"content": [...], "usage": {...}}}
  {"type": "tool_result", "tool_use_id": "...", "content": "..."}
  {"type": "result",  "subtype": "success", "result": "...",
   "usage": {"input_tokens": N, "output_tokens": N}}
"""

import subprocess
import json
from typing import List, Optional, Any, Dict
from pydantic import BaseModel

from .agent import (
    BaseAgent, AgentTask, AgentResult, AgentAction, TokenUsage,
    CollaborativePlan, PlanReview, AgentRole, ReviewComment,
)
from .utils import extract_json
from .config import MCPServerConfig
from .logging import get_logger

logger = get_logger(__name__)


class Plan(BaseModel):
    tasks: List[AgentTask]


class ClaudeAgent(BaseAgent):
    """Agent that drives the Anthropic `claude` CLI."""

    def __init__(
        self,
        model_name: str = "claude-opus-4-5",
        flash_model_name: Optional[str] = None,
        mcp_servers: Optional[List[MCPServerConfig]] = None,
        sandbox: bool = False,
    ):
        super().__init__()
        self._model_name = model_name
        self._flash_model_name = flash_model_name
        self.mcp_servers = mcp_servers or []
        self.sandbox = sandbox
        self.context = ""

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def model_name(self) -> str:
        return self._model_name

    @model_name.setter
    def model_name(self, value: str):
        self._model_name = value

    @property
    def pro_model_name(self) -> str:
        return self._model_name

    @property
    def flash_model_name(self) -> Optional[str]:
        return self._flash_model_name

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _base_cmd(self, output_format: str = "stream-json") -> List[str]:
        """Build the base claude CLI command."""
        cmd = [
            "claude",
            "--model", self.model_name,
            "--output-format", output_format,
            "--dangerously-skip-permissions",
        ]
        return cmd

    def _run_prompt(self, prompt: str) -> str:
        """
        Run a short non-streaming prompt and return the raw text response.
        Uses `--output-format json` for simple request/response calls.
        """
        cmd = self._base_cmd(output_format="json") + ["-p", prompt]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
        )
        data = extract_json(result.stdout)
        if data:
            # Top-level "result" key in JSON mode
            return data.get("result", result.stdout).strip()
        return result.stdout.strip()

    def _accumulate_usage(self, usage_dict: Dict[str, Any]) -> TokenUsage:
        u = TokenUsage(
            prompt_tokens=usage_dict.get("input_tokens", 0),
            completion_tokens=usage_dict.get("output_tokens", 0),
            total_tokens=usage_dict.get("input_tokens", 0) + usage_dict.get("output_tokens", 0),
        )
        bucket = self.usage_by_model.setdefault(self.model_name, TokenUsage())
        bucket.prompt_tokens += u.prompt_tokens
        bucket.completion_tokens += u.completion_tokens
        bucket.total_tokens += u.total_tokens
        return u

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    def receive_context(self, context: str):
        self.context = context

    def classify_goal(self, goal: str) -> str:
        prompt = (
            f"Classify the following goal as 'simple' (one-off action, direct query, "
            f"or single-step task) or 'complex' (multi-step task, requires planning, "
            f"file modifications, or research). "
            f"Goal: '{goal}'. Output only the word 'simple' or 'complex'."
        )
        try:
            response = self._run_prompt(prompt).lower()
            return "complex" if "complex" in response else "simple"
        except subprocess.CalledProcessError as e:
            logger.error("classification_failed_subprocess", model=self.model_name, returncode=e.returncode)
            return "complex"
        except Exception as e:
            logger.error("classification_failed_unknown", error=str(e))
            return "complex"

    def decompose_goal(self, goal: str) -> List[AgentTask]:
        prompt = (
            f"Given the goal: '{goal}', decompose it into a sequence of sub-tasks. "
            f"Current context: '{self.context}'. "
            "Output the tasks in a JSON format matching this structure: "
            '{"tasks": [{"id": "task1", "description": "...", "context": "...", '
            '"agent_type": "...", "verification_command": "...", "depends_on": ["task_id_1"]}]}. '
            "agent_type should be 'planner' for highly complex hierarchical tasks, "
            "or 'executor' for most tasks a single agent can handle with tool calls. "
            "verification_command is a shell command to verify success. "
            "depends_on lists task IDs that must complete first. "
            "Only output the JSON object, nothing else."
        )
        try:
            response = self._run_prompt(prompt)
            task_data = extract_json(response)
            if task_data and "tasks" in task_data:
                return Plan.model_validate(task_data).tasks
            raise ValueError(f"No tasks JSON in response: {response}")
        except subprocess.CalledProcessError as e:
            logger.error("decomposition_failed_subprocess", returncode=e.returncode)
            raise RuntimeError(f"Failed to decompose goal with Claude: {e}")
        except Exception as e:
            logger.error("decomposition_failed_unknown", error=str(e))
            return []

    def execute_task(self, task: AgentTask, progress: Optional[Any] = None) -> AgentResult:
        """
        Execute a task via the claude CLI in stream-json mode, capturing the
        full tool-use history and token usage.
        """
        logger.info("claude_agent_executing", task_id=task.id, model=self.model_name)

        prompt = (
            f"Task: {task.description}\n"
            f"Additional Context: {task.context}\n"
            f"System Context: {self.context}\n"
            "Please perform this task. You have access to shell tools. "
            "Use them to read, write, or modify files as needed to achieve the goal. "
            "Output the final result or a summary of your actions."
        )

        history: List[AgentAction] = []
        full_response: List[str] = []
        total_usage = TokenUsage()

        try:
            cmd = self._base_cmd("stream-json") + ["-p", prompt]
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )

            for raw_line in process.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                etype = event.get("type")

                if etype == "assistant":
                    msg = event.get("message", {})
                    for block in msg.get("content", []):
                        btype = block.get("type")
                        if btype == "text":
                            text = block.get("text", "")
                            full_response.append(text)
                            history.append(AgentAction(action_type="thought", content=text))
                        elif btype == "tool_use":
                            history.append(AgentAction(
                                action_type="tool_call",
                                content=block.get("name", ""),
                                metadata=block.get("input"),
                            ))
                    usage = msg.get("usage", {})
                    if usage:
                        total_usage = self._accumulate_usage(usage)

                elif etype == "tool_result":
                    content = event.get("content", "")
                    if isinstance(content, list):
                        content = " ".join(
                            c.get("text", "") for c in content if isinstance(c, dict)
                        )
                    history.append(AgentAction(action_type="tool_result", content=str(content)))

                elif etype == "result":
                    usage = event.get("usage", {})
                    if usage:
                        total_usage = self._accumulate_usage(usage)
                    # Prefer the top-level result text if no assistant text was collected
                    if not full_response:
                        result_text = event.get("result", "")
                        if result_text:
                            full_response.append(result_text)

            process.wait()

            if process.returncode == 0:
                return AgentResult(
                    task_id=task.id,
                    success=True,
                    output="".join(full_response),
                    agent_model=self.model_name,
                    usage=total_usage,
                    history=history,
                )
            else:
                return AgentResult(
                    task_id=task.id,
                    success=False,
                    error=f"Claude process exited with {process.returncode}",
                    agent_model=self.model_name,
                    history=history,
                )

        except Exception as e:
            return AgentResult(
                task_id=task.id,
                success=False,
                error=str(e),
                agent_model=self.model_name,
                history=history,
            )

    def generate_commit_message(self, result: AgentResult) -> str:
        prompt = (
            f"Generate a concise, descriptive Git commit message for the following task output.\n"
            f"Task Output: {result.output}\n"
            f"Verification Output: {result.verification_output}\n"
            "Output only the commit message, nothing else."
        )
        try:
            return self._run_prompt(prompt)
        except Exception:
            return super().generate_commit_message(result)

    def review_plan(self, plan: CollaborativePlan, role: AgentRole) -> PlanReview:
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
            response = self._run_prompt(prompt)
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
        except Exception as e:
            logger.warning("review_plan_failed", role=role.value, error=str(e))

        return PlanReview(
            original_plan_id=plan.goal,
            reviewers=[role],
            comments=[],
            approved=True,
            confidence_score=0.5,
        )
