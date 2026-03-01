import json
import subprocess
import threading
from typing import List, Dict, Any, Optional
from .config import MCPServerConfig

class MCPClient:
    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self.id_counter = 0
        self.lock = threading.Lock()

    def start(self):
        if self.process:
            return

        self.process = subprocess.Popen(
            [self.config.command] + self.config.args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.config.env,
            bufsize=1
        )
        
        # Mandatory handshake
        self._initialize()

    def _initialize(self):
        # 1. initialize request
        self.call_method("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "polyphony-agent", "version": "0.1.0"}
        })
        
        # 2. initialized notification
        self.send_notification("notifications/initialized")

    def call_method(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        with self.lock:
            self.id_counter += 1
            request_id = self.id_counter
            
            request = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params or {}
            }
            
            self.process.stdin.write(json.dumps(request) + "\n")
            self.process.stdin.flush()
            
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError("MCP server closed connection")
            
            response = json.loads(line)
            if response.get("id") != request_id:
                # Basic handling for out-of-order responses or notifications
                # In a real implementation we'd need a more robust dispatcher
                while response.get("id") != request_id:
                    line = self.process.stdout.readline()
                    if not line:
                        raise RuntimeError("MCP server closed connection")
                    response = json.loads(line)
            
            if "error" in response:
                raise RuntimeError(f"MCP error: {response['error']}")
            
            return response.get("result")

    def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None):
        with self.lock:
            notification = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params or {}
            }
            self.process.stdin.write(json.dumps(notification) + "\n")
            self.process.stdin.flush()

    def list_tools(self) -> List[Dict[str, Any]]:
        result = self.call_method("tools/list")
        return result.get("tools", [])

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        result = self.call_method("tools/call", {
            "name": name,
            "arguments": arguments
        })
        return result

    def stop(self):
        if self.process:
            self.process.terminate()
            self.process = None
