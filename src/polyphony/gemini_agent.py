import subprocess
import json
from typing import List, Optional, Any
from pydantic import BaseModel
from .agent import BaseAgent, AgentTask, AgentResult
from .utils import extract_json

from .config import MCPServerConfig

class Plan(BaseModel):
    tasks: List[AgentTask]

class GeminiAgent(BaseAgent):
    def __init__(self, model_name: str = "gemini-3-flash-preview", flash_model_name: Optional[str] = None, mcp_servers: Optional[List[MCPServerConfig]] = None):
        self._model_name = model_name
        self._pro_model_name = model_name
        self._flash_model_name = flash_model_name
        self.context = ""
        self.mcp_servers = mcp_servers or []

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
        """
        Calls gemini to classify a goal as 'simple' or 'complex'.
        """
        prompt = (
            f"Classify the following goal as 'simple' (one-off action, direct query, or single-step task) "
            f"or 'complex' (multi-step task, requires planning, file modifications, or research). "
            f"Goal: '{goal}'. Output only the word 'simple' or 'complex'."
        )
        
        try:
            # Call gemini with non-interactive mode and YOLO mode
            result = subprocess.run(
                ["gemini", "--model", self.model_name, "-y", "-o", "json", "-p", prompt],
                capture_output=True,
                text=True,
                check=True
            )
            
            output = result.stdout
            outer_json = extract_json(output)
            if outer_json:
                model_response = outer_json.get('response', '').strip().lower()
                if "complex" in model_response:
                    return "complex"
                return "simple"
            else:
                return "simple" # Default to simple on error

        except Exception:
            return "simple" # Default to simple on error

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
            # Call gemini with non-interactive mode, json output format, and YOLO mode
            result = subprocess.run(
                ["gemini", "--model", self.model_name, "-y", "-o", "json", "-p", prompt],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Extract JSON from output. gemini outputs logs and then the JSON.
            output = result.stdout
            outer_json = extract_json(output)
            
            if outer_json:
                # The actual response from the model is in outer_json['response']
                model_response = outer_json.get('response', '')
                
                # The model response should contain the tasks JSON.
                # Use extract_json again to be safe.
                task_data = extract_json(model_response)
                if task_data and "tasks" in task_data:
                    plan = Plan.model_validate(task_data)
                    return plan.tasks
                else:
                    raise ValueError(f"Could not find JSON in model response: {model_response}")
            else:
                raise ValueError(f"Could not find JSON in gemini output: {output}")

        except subprocess.CalledProcessError as e:
            print(f"Error calling gemini: {e.stderr}")
            return []
        except Exception as e:
            print(f"Error decomposing goal: {e}")
            return []

    def execute_task(self, task: AgentTask, progress: Optional[Any] = None) -> AgentResult:
        """
        Calls gemini to perform a specific task.
        """
        print(f"GeminiAgent executing task: {task.description}")
        
        # Formulate a prompt for gemini to perform the task
        prompt = (
            f"Task: {task.description}\n"
            f"Additional Context: {task.context}\n"
            f"System Context: {self.context}\n"
            "Please perform this task. You have access to shell tools. "
            "Use them to read, write, or modify files as needed to achieve the goal. "
            "Output the final result or a summary of your actions."
        )
        
        try:
            # Call gemini with non-interactive mode, json output format, and YOLO mode
            result = subprocess.run(
                ["gemini", "--model", self.model_name, "-y", "-o", "json", "-p", prompt],
                capture_output=True,
                text=True,
                check=True
            )
            
            output = result.stdout
            outer_json = extract_json(output)
            if outer_json:
                model_response = outer_json.get('response', '')
                return AgentResult(task_id=task.id, success=True, output=model_response)
            else:
                return AgentResult(task_id=task.id, success=False, error="No JSON found in gemini output")

        except subprocess.CalledProcessError as e:
            return AgentResult(task_id=task.id, success=False, error=str(e.stderr))
        except Exception as e:
            return AgentResult(task_id=task.id, success=False, error=str(e))

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
                capture_output=True,
                text=True,
                check=True
            )
            
            output = sub_result.stdout
            outer_json = extract_json(output)
            if outer_json:
                model_response = outer_json.get('response', '').strip()
                return model_response
            else:
                return super().generate_commit_message(result)

        except Exception:
            return super().generate_commit_message(result)
