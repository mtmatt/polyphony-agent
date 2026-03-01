import json
from typing import List, Optional
from pydantic import BaseModel
from openai import OpenAI
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from .agent import BaseAgent, AgentTask, AgentResult
from .utils import write_file, replace_text, run_command

console = Console()

class Plan(BaseModel):
    tasks: List[AgentTask]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write or overwrite a file with given content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to the file."},
                    "content": {"type": "string", "description": "Complete file content."}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "replace_text",
            "description": "Surgically replace text in a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to the file."},
                    "old": {"type": "string", "description": "The exact text to find."},
                    "new": {"type": "string", "description": "The text to replace it with."}
                },
                "required": ["path", "old", "new"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command and return the result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The command to run."}
                },
                "required": ["command"]
            }
        }
    }
]

class OpenAIAgent(BaseAgent):
    def __init__(self, model_name: str = "gpt-4o", base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model_name = model_name
        self.context = ""

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

    def execute_task(self, task: AgentTask, progress: Optional[Any] = None) -> AgentResult:
        history: List[AgentAction] = []
        
        def update_progress(p: int):
            if progress and callable(progress):
                progress(p)

        messages = [
            {"role": "system", "content": (
                f"You are an expert software engineer. System Context:\n{self.context}\n"
                "Always verify that your actions were successful. If you write a file, you should run it or check its existence. "
                "After you have completed all actions and verifications, provide a concise final summary of what you achieved. "
                "Do not end with trailing thoughts about what you will do next; actually do them or finish."
            )},
            {"role": "user", "content": f"Task: {task.description}\nAdditional Context: {task.context}"}
        ]
        
        try:
            # Tool calling loop
            for i in range(5): # Max 5 tool calls per task
                update_progress(10 + i*15) # Progress through steps
                
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto"
                )
                
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
                        history=history
                    )
                
                for tool_call in message.tool_calls:
                    func_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)
                    
                    history.append(AgentAction(action_type="tool_call", content=func_name, metadata=args))
                    
                    # Better tool call visualization
                    if func_name == "write_file":
                        path = args.get("path")
                        content = args.get("content", "")
                        console.print(Panel(Syntax(content, "python", theme="monokai", line_numbers=True), title=f"Writing to {path}", border_style="cyan"))
                        result = write_file(**args)
                    elif func_name == "replace_text":
                        path = args.get("path")
                        old = args.get("old")
                        new = args.get("new")
                        console.print(Panel(f"[bold red]- {old}[/bold red]\n[bold green]+ {new}[/bold green]", title=f"Updating {path}", border_style="yellow"))
                        result = replace_text(**args)
                    elif func_name == "run_command":
                        cmd = args.get("command")
                        console.print(f"  [dim][tool][/dim] Running: [bold cyan]{cmd}[/bold cyan]")
                        result = run_command(**args)
                    else:
                        result = f"Error: Unknown tool {func_name}"
                    
                    history.append(AgentAction(action_type="tool_result", content=result))
                    
                    if "Error" in result:
                        console.print(f"  [bold red][tool result][/bold red] {result}")
                    else:
                        console.print(f"  [dim][tool result][/dim] {result}")
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": func_name,
                        "content": result
                    })
            
            update_progress(100)
            return AgentResult(task_id=task.id, success=True, output="Max tool calls reached.", history=history)

        except Exception as e:
            update_progress(100)
            return AgentResult(task_id=task.id, success=False, error=str(e), history=history)

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
            
            content = response.choices[0].message.content.strip()
            return content

        except Exception:
            return super().generate_commit_message(result)
