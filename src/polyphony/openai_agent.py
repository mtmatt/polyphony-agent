import json
from typing import List, Optional
from pydantic import BaseModel
from openai import OpenAI
from .agent import BaseAgent, AgentTask, AgentResult

class Plan(BaseModel):
    tasks: List[AgentTask]

class OpenAIAgent(BaseAgent):
    def __init__(self, model_name: str = "gpt-4o", base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model_name = model_name
        self.context = ""

    def receive_context(self, context: str):
        self.context = context

    def decompose_goal(self, goal: str) -> List[AgentTask]:
        prompt = (
            f"Given the goal: '{goal}', decompose it into a sequence of sub-tasks. "
            f"Current context: '{self.context}'. "
            "Output the tasks in a JSON format matching this structure: "
            "{\"tasks\": [{\"id\": \"task1\", \"description\": \"...\", \"context\": \"...\", \"agent_type\": \"...\", \"verification_command\": \"...\"}]}. "
            "agent_type should be 'planner' if the task is complex and needs its own sub-tasks, or 'executor' if it's a direct action. "
            "verification_command should be a shell command (e.g., 'pytest', 'python my_script.py', 'ls -R') that can be run to verify the task's success. "
            "Be aggressive in using 'planner' for any task that has multiple steps. "
            "Only output the JSON object, nothing else."
        )
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            if content:
                plan = Plan.model_validate_json(content)
                return plan.tasks
            return []

        except Exception as e:
            print(f"Error decomposing goal with OpenAI: {e}")
            return []

    def execute_task(self, task: AgentTask) -> AgentResult:
        print(f"OpenAIAgent executing task: {task.description}")
        
        prompt = (
            f"Task: {task.description}\n"
            f"Additional Context: {task.context}\n"
            f"System Context: {self.context}\n"
            "Please perform this task. Output the result clearly."
        )
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.choices[0].message.content
            return AgentResult(task_id=task.id, success=True, output=content)

        except Exception as e:
            return AgentResult(task_id=task.id, success=False, error=str(e))
