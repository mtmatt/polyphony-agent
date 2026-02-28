import subprocess
import json
from typing import List, Optional
from pydantic import BaseModel
from .agent import BaseAgent, AgentTask, AgentResult

class Plan(BaseModel):
    tasks: List[AgentTask]

class GeminiAgent(BaseAgent):
    def __init__(self, model_name: str = "gemini-3-flash-preview"):
        self.model_name = model_name
        self.context = ""

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
                ["gemini", "-y", "-o", "json", "-p", prompt],
                capture_output=True,
                text=True,
                check=True
            )
            
            output = result.stdout
            start = output.find('{')
            end = output.rfind('}') + 1
            if start != -1 and end != -1:
                outer_json_data = output[start:end]
                outer_json = json.loads(outer_json_data)
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
            "{\"tasks\": [{\"id\": \"task1\", \"description\": \"...\", \"context\": \"...\", \"agent_type\": \"...\", \"verification_command\": \"...\"}]}. "
            "agent_type should be 'planner' if the task is complex and needs its own sub-tasks, or 'executor' if it's a direct action. "
            "verification_command should be a shell command (e.g., 'pytest', 'python my_script.py', 'ls -R') that can be run to verify the task's success. "
            "Be aggressive in using 'planner' for any task that has multiple steps. "
            "Only output the JSON object, nothing else."
        )
        
        try:
            # Call gemini with non-interactive mode, json output format, and YOLO mode
            result = subprocess.run(
                ["gemini", "-y", "-o", "json", "-p", prompt],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Extract JSON from output. gemini outputs logs and then the JSON.
            output = result.stdout
            start = output.find('{')
            end = output.rfind('}') + 1
            if start != -1 and end != -1:
                outer_json_data = output[start:end]
                outer_json = json.loads(outer_json_data)
                
                # The actual response from the model is in outer_json['response']
                model_response = outer_json.get('response', '')
                
                # The model response should contain the tasks JSON.
                # Extract it again in case the model added some text around it.
                task_start = model_response.find('{')
                task_end = model_response.rfind('}') + 1
                if task_start != -1 and task_end != -1:
                    task_json_data = model_response[task_start:task_end]
                    plan = Plan.model_validate_json(task_json_data)
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
                ["gemini", "-y", "-o", "json", "-p", prompt],
                capture_output=True,
                text=True,
                check=True
            )
            
            output = result.stdout
            start = output.find('{')
            end = output.rfind('}') + 1
            if start != -1 and end != -1:
                outer_json_data = output[start:end]
                outer_json = json.loads(outer_json_data)
                model_response = outer_json.get('response', '')
                return AgentResult(task_id=task.id, success=True, output=model_response)
            else:
                return AgentResult(task_id=task.id, success=False, error="No JSON found in gemini output")

        except subprocess.CalledProcessError as e:
            return AgentResult(task_id=task.id, success=False, error=str(e.stderr))
        except Exception as e:
            return AgentResult(task_id=task.id, success=False, error=str(e))
