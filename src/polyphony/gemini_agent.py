import subprocess
import json
from typing import List, Optional, Any, Dict
from pydantic import BaseModel
from .agent import BaseAgent, AgentTask, AgentResult, TokenUsage, CollaborativePlan, PlanReview, AgentRole, ReviewComment
from .utils import extract_json

from .config import MCPServerConfig

from .logging import get_logger

logger = get_logger(__name__)

class Plan(BaseModel):
    tasks: List[AgentTask]

class GeminiAgent(BaseAgent):
    def __init__(self, model_name: str = "gemini-3-flash-preview", flash_model_name: Optional[str] = None, mcp_servers: Optional[List[MCPServerConfig]] = None, sandbox: bool = False):
        super().__init__()
        self._model_name = model_name
        self._pro_model_name = model_name
        self._flash_model_name = flash_model_name
        self.context = ""
        self.mcp_servers = mcp_servers or []
        self.sandbox = sandbox

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

    def _get_base_command(self) -> List[str]:
        cmd = ["gemini", "--model", self.model_name]
        if self.sandbox:
            cmd.append("--sandbox")
        return cmd

    def receive_context(self, context: str):
        self.context = context

    def classify_goal(self, goal: str) -> str:
        """
        Calls gemini to classify a goal as 'simple' or 'complex'.
        """
        prompt = (
            f"Classify the following goal as 'simple' (one-off action, direct query, or single-step task) "
            f"or 'complex' (multi-step task, requires planning, file modifications, or research). "
            f"Goal: '{goal}'. Output only the word 'simple' or 'complex'."
        )
        
        try:
            cmd = self._get_base_command() + ["-y", "-o", "json", "-p", prompt]
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=True
            )
            
            output = result.stdout
            outer_json = extract_json(output)
            if outer_json:
                self._extract_usage(outer_json)
                model_response = outer_json.get('response', '').strip().lower()
                if "complex" in model_response:
                    return "complex"
                return "simple"
            else:
                logger.error("classification_failed_no_json", output=output)
                return "simple" 

        except subprocess.CalledProcessError as e:
            logger.error("classification_failed_subprocess", stderr=e.stderr, model=self.model_name)
            # Default to complex if classification fails to be safe
            return "complex"
        except Exception as e:
            logger.error("classification_failed_unknown", error=str(e))
            return "complex"

    def decompose_goal(self, goal: str) -> List[AgentTask]:
        """
        Calls gemini to decompose a goal into sub-tasks.
        """
        prompt = (
            f"Given the goal: '{goal}', decompose it into a sequence of sub-tasks. "
            f"Current context: '{self.context}'. "
            "Output the tasks in a JSON format matching this structure: "
            "{\"tasks\": [{\"id\": \"task1\", \"description\": \"...\", \"context\": \"...\", \"agent_type\": \"...\", \"verification_command\": \"...\", \"depends_on\": [\"task_id_1\"]}]}. "
            "agent_type should be 'planner' if the task is highly complex and requires its own structured sub-tasks, "
            "or 'executor' if it's a specific action or a complex task that a single agent can handle with multiple tool calls. "
            "verification_command should be a shell command (e.g., 'pytest', 'python my_script.py', 'ls -R') that can be run to verify the task's success. "
            "depends_on should be a list of task IDs that must be completed before the current task can start. "
            "Be conservative in using 'planner' – only use it for very large goals that genuinely need hierarchy. "
            "Prefer 'executor' for most technical tasks as the executor is already capable of multi-step tool use. "
            "Only output the JSON object, nothing else."
        )
        
        try:
            cmd = self._get_base_command() + ["-y", "-o", "json", "-p", prompt]
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=True
            )
            
            output = result.stdout
            outer_json = extract_json(output)
            
            if outer_json:
                self._extract_usage(outer_json)
                model_response = outer_json.get('response', '')
                task_data = extract_json(model_response)
                if task_data and "tasks" in task_data:
                    plan = Plan.model_validate(task_data)
                    return plan.tasks
                else:
                    raise ValueError(f"Could not find JSON in model response: {model_response}")
            else:
                raise ValueError(f"Could not find JSON in gemini output: {output}")

        except subprocess.CalledProcessError as e:
            logger.error("decomposition_failed_subprocess", stderr=e.stderr)
            raise RuntimeError(f"Failed to decompose goal with Gemini: {e.stderr}")
        except Exception as e:
            logger.error("decomposition_failed_unknown", error=str(e))
            return []

    def _extract_usage(self, outer_json: Dict[str, Any]) -> Optional[TokenUsage]:
        stats = outer_json.get("stats", {})
        models = stats.get("models", {})
        model_stats = models.get(self.model_name)
        if not model_stats:
            # Try to find any model if the name doesn't match exactly
            if models:
                # Return the one with the most tokens or just the first one
                model_stats = list(models.values())[0]
        
        if model_stats:
            tokens = model_stats.get("tokens", {})
            usage = TokenUsage(
                prompt_tokens=tokens.get("prompt", 0) or tokens.get("input", 0),
                completion_tokens=tokens.get("candidates", 0) or tokens.get("output", 0),
                total_tokens=tokens.get("total", 0)
            )
            
            # Update usage by model
            model_name = self.model_name
            if model_name not in self.usage_by_model:
                self.usage_by_model[model_name] = TokenUsage()
            
            self.usage_by_model[model_name].prompt_tokens += usage.prompt_tokens
            self.usage_by_model[model_name].completion_tokens += usage.completion_tokens
            self.usage_by_model[model_name].total_tokens += usage.total_tokens
            return usage
        return None

    def execute_task(self, task: AgentTask, progress: Optional[Any] = None) -> AgentResult:
        """
        Calls gemini to perform a specific task, capturing history from stream-json.
        """
        logger.info("gemini_agent_executing", task_id=task.id, sandbox=self.sandbox)
        
        # Formulate a prompt for gemini to perform the task
        prompt = (
            f"Task: {task.description}\n"
            f"Additional Context: {task.context}\n"
            f"System Context: {self.context}\n"
            "Please perform this task. You have access to shell tools. "
            "Use them to read, write, or modify files as needed to achieve the goal. "
            "Output the final result or a summary of your actions."
        )
        
        history: List[AgentAction] = []
        full_response = []
        
        try:
            # Call gemini with stream-json output format
            cmd = self._get_base_command() + ["-y", "-o", "stream-json", "-p", prompt]
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True
            )
            
            total_usage = TokenUsage()
            
            # Read stdout line by line
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    msg_type = data.get("type")
                    
                    if msg_type == "message":
                        content = data.get("content", "")
                        role = data.get("role")
                        if role == "assistant":
                            full_response.append(content)
                            history.append(AgentAction(action_type="thought", content=content))
                    elif msg_type == "tool_use":
                        history.append(AgentAction(
                            action_type="tool_call", 
                            content=data.get("tool_name", ""),
                            metadata=data.get("parameters")
                        ))
                    elif msg_type == "tool_result":
                        history.append(AgentAction(
                            action_type="tool_result",
                            content=data.get("output", "")
                        ))
                    elif msg_type == "result":
                        stats = data.get("stats", {})
                        total_usage.prompt_tokens = stats.get("input_tokens", 0)
                        total_usage.completion_tokens = stats.get("output_tokens", 0)
                        total_usage.total_tokens = stats.get("total_tokens", 0)
                except json.JSONDecodeError:
                    continue
            
            process.wait()
            
            if process.returncode == 0:
                # Update usage
                if self.model_name not in self.usage_by_model:
                    self.usage_by_model[self.model_name] = TokenUsage()
                
                self.usage_by_model[self.model_name].prompt_tokens += total_usage.prompt_tokens
                self.usage_by_model[self.model_name].completion_tokens += total_usage.completion_tokens
                self.usage_by_model[self.model_name].total_tokens += total_usage.total_tokens
                
                return AgentResult(
                    task_id=task.id, 
                    success=True, 
                    output="".join(full_response), 
                    usage=total_usage,
                    history=history
                )
            else:
                return AgentResult(task_id=task.id, success=False, error=f"Gemini process exited with {process.returncode}", history=history)

        except Exception as e:
            return AgentResult(task_id=task.id, success=False, error=str(e), history=history)

    def generate_commit_message(self, result: AgentResult) -> str:
        """
        Calls gemini to generate a descriptive commit message based on the task result.
        """
        prompt = (
            f"Generate a concise, descriptive Git commit message for the following task output.\n"
            f"Task Output: {result.output}\n"
            f"Verification Output: {result.verification_output}\n"
            "Output only the commit message, nothing else."
        )
        
        try:
            # Call gemini with non-interactive mode, json output format, and YOLO mode
            sub_result = subprocess.run(
                ["gemini", "--model", self.model_name, "-y", "-o", "json", "-p", prompt],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=True
            )
            
            output = sub_result.stdout
            outer_json = extract_json(output)
            if outer_json:
                self._extract_usage(outer_json)
                model_response = outer_json.get('response', '').strip()
                return model_response
            else:
                return super().generate_commit_message(result)

        except Exception:
            return super().generate_commit_message(result)

    def review_plan(self, plan: CollaborativePlan, role: AgentRole) -> PlanReview:
        """
        Calls gemini to review a collaborative plan from the perspective of a given role.
        """
        tasks_summary = "\n".join(
            f"- [{t.id}] {t.description}" for t in plan.tasks
        )
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
            cmd = self._get_base_command() + ["-y", "-o", "json", "-p", prompt]
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=True,
            )
            outer_json = extract_json(result.stdout)
            if outer_json:
                self._extract_usage(outer_json)
                review_data = extract_json(outer_json.get("response", ""))
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

        # Fallback: approve with neutral confidence
        return PlanReview(
            original_plan_id=plan.goal,
            reviewers=[role],
            comments=[],
            approved=True,
            confidence_score=0.5,
        )
