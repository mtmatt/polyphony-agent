import json
import os
from typing import List, Dict, Any, Optional, Tuple
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from .mcp_client import MCPClient
from .config import MCPServerConfig
from .utils import write_file, replace_text, run_command
from .logging import get_logger
from .agent import AgentAction

logger = get_logger(__name__)
console = Console()

# Base tools that all agents should have access to
BASE_TOOLS = [
    {
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
    },
    {
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
    },
    {
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
]

class ToolExecutor:
    """
    Consolidated tool execution and MCP management.
    Provides a consistent interface for all agent types.
    """
    def __init__(self, mcp_servers: Optional[List[MCPServerConfig]] = None, sandbox: bool = False):
        self.sandbox = sandbox
        self.mcp_clients: List[MCPClient] = [MCPClient(cfg) for cfg in (mcp_servers or [])]
        self.mcp_tool_map: Dict[str, Dict[str, Any]] = {} # name -> tool_definition
        self.mcp_client_map: Dict[str, MCPClient] = {} # tool_name -> client
        self.base_tool_funcs = {
            "write_file": write_file,
            "replace_text": replace_text,
            "run_command": run_command
        }
        self.started = False

    def start(self):
        """Starts all MCP clients and builds the tool map."""
        if self.started:
            return
        for client in self.mcp_clients:
            try:
                client.start()
                tools = client.list_tools()
                for tool in tools:
                    name = tool.get("name")
                    if name:
                        self.mcp_tool_map[name] = tool
                        self.mcp_client_map[name] = client
                logger.info("mcp_server_started", command=client.config.command, tool_count=len(tools))
            except Exception as e:
                console.print(f"[bold red]Error starting MCP server {client.config.command}: {e}[/bold red]")
                logger.error("mcp_server_start_failed", command=client.config.command, error=str(e))
        self.started = True

    def stop(self):
        """Stops all MCP clients."""
        for client in self.mcp_clients:
            try:
                client.stop()
            except Exception as e:
                logger.error("mcp_server_stop_failed", command=client.config.command, error=str(e))
        self.started = False
        self.mcp_tool_map = {}
        self.mcp_client_map = {}

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Returns all tool definitions (base + MCP)."""
        definitions = []
        # Add base tools
        for tool in BASE_TOOLS:
            definitions.append(tool)
            
        # Add MCP tools
        for name, tool in self.mcp_tool_map.items():
            definitions.append({
                "name": name,
                "description": tool.get("description", ""),
                "parameters": tool.get("inputSchema", {"type": "object", "properties": {}})
            })
        return definitions

    def get_provider_tools(self, provider: str = "openai") -> List[Dict[str, Any]]:
        """
        Get tool definitions in the format required by the provider.
        Supported providers: 'openai', 'ollama', 'anthropic', 'gemini'.
        """
        if not self.started:
            self.start()
        definitions = self.get_tool_definitions()
        
        if provider in ("openai", "ollama", "anthropic"):
            return [
                {
                    "type": "function",
                    "function": tool
                } for tool in definitions
            ]
        elif provider == "gemini":
            return definitions
        return definitions

    def execute(self, name: str, arguments: Any) -> Tuple[str, bool, AgentAction]:
        """
        Executes a tool by name with given arguments.
        Returns a tuple of (result_string, success, AgentAction).
        """
        # Ensure arguments is a dict
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                error_msg = f"Error: Could not parse tool arguments as JSON: {arguments}"
                return error_msg, False, AgentAction(action_type="tool_call", content=name, metadata={"raw": arguments})

        action = AgentAction(action_type="tool_call", content=name, metadata=arguments)
        logger.debug("executing_tool", name=name, arguments=arguments)
        
        success = True
        try:
            if name in self.base_tool_funcs:
                # Visualization and Execution
                if name == "write_file":
                    path = arguments.get("path")
                    content = arguments.get("content", "")
                    
                    # Detect language for syntax highlighting
                    from pathlib import Path
                    ext = Path(path).suffix.lstrip('.')
                    lang_map = {
                        "py": "python",
                        "js": "javascript",
                        "ts": "typescript",
                        "tsx": "typescript",
                        "jsx": "javascript",
                        "yml": "yaml",
                        "yaml": "yaml",
                        "md": "markdown",
                        "json": "json",
                        "sh": "bash",
                        "bash": "bash"
                    }
                    lang = lang_map.get(ext, ext if ext else "python")
                    
                    console.print(Panel(Syntax(content, lang, theme="monokai", line_numbers=True), title=f"Writing to {path}", border_style="cyan"))
                    result = self.base_tool_funcs[name](**arguments)
                elif name == "replace_text":
                    path = arguments.get("path")
                    old = arguments.get("old")
                    new = arguments.get("new")
                    console.print(Panel(f"[bold red]- {old}[/bold red]\n[bold green]+ {new}[/bold green]", title=f"Updating {path}", border_style="yellow"))
                    result = self.base_tool_funcs[name](**arguments)
                elif name == "run_command":
                    cmd = arguments.get("command")
                    console.print(f"  [dim][tool][/dim] Running: [bold cyan]{cmd}[/bold cyan] [dim](sandbox={self.sandbox})[/dim]")
                    result = self.base_tool_funcs[name](command=cmd, sandbox=self.sandbox)
                else:
                    result = self.base_tool_funcs[name](**arguments)
                
            elif name in self.mcp_client_map:
                client = self.mcp_client_map[name]
                console.print(f"  [dim][mcp tool][/dim] {name} from {os.path.basename(client.config.command)}")
                try:
                    mcp_result = client.call_tool(name, arguments)
                    # Extract content from MCP result
                    result_content = []
                    for content_block in mcp_result.get("content", []):
                        if content_block.get("type") == "text":
                            result_content.append(content_block.get("text"))
                        elif content_block.get("type") == "image":
                            result_content.append("[Image data omitted]")
                    result = "\n".join(result_content) if result_content else "Success"
                except Exception as e:
                    logger.error("mcp_tool_execution_failed", name=name, error=str(e))
                    result = f"Error calling MCP tool {name}: {e}"
            else:
                logger.warning("unknown_tool", name=name)
                result = f"Error: Unknown tool {name}"
                
            # Improved success/failure detection
            # We check if the result string starts with "Error" or "Error:"
            if result.startswith("Error") or "Error (" in result:
                success = False
                console.print(f"  [bold red][tool result][/bold red] {result}")
            else:
                console.print(f"  [dim][tool result][/dim] {result}")
                
            return result, success, action
            
        except Exception as e:
            error_msg = f"Error executing tool {name}: {e}"
            console.print(f"  [bold red][tool error][/bold red] {error_msg}")
            return error_msg, False, action
