import json
import os
from typing import List, Optional, Any
from pydantic import BaseModel
from openai import OpenAI
from rich.console import Console

from .agent import BaseAgent, AgentTask, AgentResult, AgentAction, TokenUsage, CollaborativePlan, PlanReview, AgentRole, ReviewComment
from .tool_executor import ToolExecutor
from .config import MCPServerConfig
from .logging import get_logger

logger = get_logger(__name__)
console = Console()

class Plan(BaseModel):
    tasks: List[AgentTask]

class OpenAIAgent(BaseAgent):
    def __init__(self, model_name: str = "gpt-4o", flash_model_name: Optional[str] = None, base_url: Optional[str] = None, api_key: Optional[str] = None, mcp_servers: Optional[List[MCPServerConfig]] = None, sandbox: bool = False):
        super().__init__()
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self._model_name = model_name
        self._pro_model_name = model_name
        self._flash_model_name = flash_model_name
        self.sandbox = sandbox
        self.context = ""
        self.tool_executor = ToolExecutor(mcp_servers, sandbox)

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

    def classify_goal(self, goal: str) -> str:
        prompt = (
            f"Classify the following goal as 'simple' (one-off action, direct query, or single-step task) "
            f"or 'complex' (multi-step task, requires planning, file modifications, or research). "
            f"Goal: '{goal}'. Output only the word 'simple' or 'complex'."
        )
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}]
            )
            self._update_usage(response.usage)
            content = response.choices[0].message.content.strip().lower()
            if "complex" in content:
                return "complex"
            return "simple"

        except Exception:
            return "simple"

    def decompose_goal(self, goal: str) -> List[AgentTask]:
        prompt = (
            f"Given the goal: '{goal}', decompose it into a sequence of sub-tasks. "
            f"Current context: '{self.context}'. "
            "Output the tasks in a JSON format matching this structure: "
            "{\"tasks\": [{\"id\": \"task1\", \"description\": \"...\", \"context\": \"...\", \"agent_type\": \"...\", \"verification_command\": \"...\", \"depends_on\": [\"task_id_1\"]}]}. "
            "agent_type should be 'planner' if the task is complex and needs its own sub-tasks, or 'executor' if it's a direct action. "
            "verification_command should be a shell command (e.g., 'pytest', 'python my_script.py', 'ls -R') that can be run to verify the task's success. "
            "depends_on should be a list of task IDs that must be completed before the current task can start. "
            "Be aggressive in using 'planner' for any task that has multiple steps. "
            "Only output the JSON object, nothing else."
        )
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            self._update_usage(response.usage)
            content = response.choices[0].message.content
            if content:
                plan = Plan.model_validate_json(content)
                return plan.tasks
            return []

        except Exception as e:
            logger.error("decomposition_failed", error=str(e))
            return []

    def _update_usage(self, response_usage: Any):
        if response_usage:
            model_name = self.model_name
            if model_name not in self.usage_by_model:
                self.usage_by_model[model_name] = TokenUsage()
            
            usage = self.usage_by_model[model_name]
            usage.prompt_tokens += response_usage.prompt_tokens
            usage.completion_tokens += response_usage.completion_tokens
            usage.total_tokens += response_usage.total_tokens

    def execute_task(self, task: AgentTask, progress: Optional[Any] = None) -> AgentResult:
        logger.info("openai_agent_executing", task_id=task.id, sandbox=self.sandbox)
        history: List[AgentAction] = []
        total_usage = TokenUsage()
        
        def update_progress(p: int):
            if progress and callable(progress):
                progress(p)

        self.tool_executor.start()
        current_tools = self.tool_executor.get_provider_tools("openai")

        system_content = (
            f"You are an expert software engineer. System Context:\n{self.context}\n"
            "Always verify that your actions were successful. If you write a file, you should run it or check its existence. "
            "After you have completed all actions and verifications, provide a concise final summary of what you achieved. "
            "Do not end with trailing thoughts about what you will do next; actually do them or finish."
        )
        if self.sandbox:
            system_content += "\nIMPORTANT: You are running in a SECURE SANDBOX. You may have restricted access to system resources or network."

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": f"Task: {task.description}\nAdditional Context: {task.context}"}
        ]
        
        try:
            # Tool calling loop
            for i in range(10): # Max 10 tool calls per task
                update_progress(10 + i*8) # Progress through steps
                
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    tools=current_tools,
                    tool_choice="auto"
                )
                
                if response.usage:
                    self._update_usage(response.usage)
                    total_usage.prompt_tokens += response.usage.prompt_tokens
                    total_usage.completion_tokens += response.usage.completion_tokens
                    total_usage.total_tokens += response.usage.total_tokens
                
                message = response.choices[0].message
                messages.append(message)
                
                if message.content:
                    thought = message.content.strip()
                    history.append(AgentAction(action_type="thought", content=thought))
                    console.print(f"  [dim][thought][/dim] {thought}")
                
                if not message.tool_calls:
                    update_progress(100)
                    return AgentResult(
                        task_id=task.id, 
                        success=True, 
                        output=message.content.strip() if message.content else "Task completed.",
                        history=history,
                        usage=total_usage
                    )
                
                for tool_call in message.tool_calls:
                    func_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)
                    
                    result, success, action = self.tool_executor.execute(func_name, args)
                    history.append(action)
                    history.append(AgentAction(action_type="tool_result", content=result))
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": func_name,
                        "content": result
                    })
            
            update_progress(100)
            return AgentResult(task_id=task.id, success=True, output="Max tool calls reached.", history=history, usage=total_usage)

        except Exception as e:
            update_progress(100)
            return AgentResult(task_id=task.id, success=False, error=str(e), history=history, usage=total_usage)
        finally:
            self.tool_executor.stop()

    def generate_commit_message(self, result: AgentResult) -> str:
        """
        Calls OpenAI to generate a descriptive commit message based on the task result.
        """
        prompt = (
            f"Generate a concise, descriptive Git commit message for the following task output.\n"
            f"Task Output: {result.output}\n"
            f"Verification Output: {result.verification_output}\n"
            "Output only the commit message, nothing else."
        )
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}]
            )
            self._update_usage(response.usage)
            content = response.choices[0].message.content.strip()
            return content

        except Exception:
            return super().generate_commit_message(result)

    def review_plan(self, plan: CollaborativePlan, role: AgentRole) -> PlanReview:
        """
        Calls OpenAI to review a collaborative plan from the perspective of a given role.
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
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            self._update_usage(response.usage)
            import json
            review_data = json.loads(response.choices[0].message.content)
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
