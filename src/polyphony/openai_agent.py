import json
from typing import List, Optional, Any
from pydantic import BaseModel
from openai import OpenAI
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from .agent import BaseAgent, AgentTask, AgentResult, AgentAction
from .utils import write_file, replace_text, run_command
from .config import MCPServerConfig
from .mcp_client import MCPClient

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
    def __init__(self, model_name: str = "gpt-4o", flash_model_name: Optional[str] = None, base_url: Optional[str] = None, api_key: Optional[str] = None, mcp_servers: Optional[List[MCPServerConfig]] = None):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self._model_name = model_name
        self._pro_model_name = model_name
        self._flash_model_name = flash_model_name
        self.context = ""
        self.mcp_clients = [MCPClient(cfg) for cfg in (mcp_servers or [])]
        for client in self.mcp_clients:
            try:
                client.start()
            except Exception as e:
                console.print(f"[bold red]Error starting MCP server {client.config.command}: {e}[/bold red]")

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

        # Dynamic tools list including MCP tools
        current_tools = list(TOOLS)
        mcp_tool_map = {} # tool_name -> client

        for client in self.mcp_clients:
            try:
                tools = client.list_tools()
                for tool in tools:
                    name = tool.get("name")
                    mcp_tool_map[name] = client
                    current_tools.append({
                        "type": "function",
                        "function": {
                            "name": name,
                            "description": tool.get("description", ""),
                            "parameters": tool.get("inputSchema", {"type": "object", "properties": {}})
                        }
                    })
            except Exception as e:
                console.print(f"[bold red]Error listing tools from MCP server {client.config.command}: {e}[/bold red]")

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
            for i in range(10): # Max 10 tool calls per task to accommodate MCP tool flows
                update_progress(10 + i*8) # Progress through steps
                
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    tools=current_tools,
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
                    elif func_name in mcp_tool_map:
                        client = mcp_tool_map[func_name]
                        console.print(f"  [dim][mcp tool][/dim] {func_name} from {client.config.command}")
                        try:
                            mcp_result = client.call_tool(func_name, args)
                            # MCP tool result is usually a list of content blocks
                            result_content = []
                            for content_block in mcp_result.get("content", []):
                                if content_block.get("type") == "text":
                                    result_content.append(content_block.get("text"))
                                elif content_block.get("type") == "image":
                                    result_content.append("[Image data omitted]")
                            result = "\n".join(result_content) if result_content else "Success"
                        except Exception as e:
                            result = f"Error calling MCP tool {func_name}: {e}"
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
