"""Ollama agent implementation with tool-calling and MCP support."""

import json
import httpx
from typing import Optional
from pydantic import BaseModel

from .agent import (
    AgentTask,
    AgentResult,
    BaseAgent,
    AgentAction,
    AgentRole,
    ReviewComment,
    PlanReview,
    CollaborativePlan,
    ConsensusVote,
)
from .mcp_client import MCPClient
from .logging import get_logger

logger = get_logger(__name__)


class OllamaAgent(BaseAgent):
    """Agent that uses a local Ollama server for inference with tool-calling support."""

    def __init__(
        self,
        model_name: str = "llama3.1",
        base_url: str = "http://localhost:11434",
        mcp_servers: Optional[list] = None,
    ):
        self._model_name = model_name
        self._pro_model_name = model_name
        self._flash_model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.mcp_clients: dict[str, MCPClient] = {}
        self.available_tools: list[dict] = []

        # Initialize MCP clients if provided
        if mcp_servers:
            for server_config in mcp_servers:
                mcp_client = MCPClient(server_config)
                self.mcp_clients[server_config.name] = mcp_client

        logger.info(
            "OllamaAgent initialized",
            model=model_name,
            base_url=base_url,
            mcp_servers=list(self.mcp_clients.keys()),
        )

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
    def flash_model_name(self) -> str:
        return self._flash_model_name

    async def _start_mcp_clients(self):
        """Start all MCP clients and discover available tools."""
        self.available_tools = []

        for name, client in self.mcp_clients.items():
            try:
                await client.start()
                tools = await client.list_tools()
                for tool in tools:
                    # Convert MCP tool format to Ollama-compatible format
                    ollama_tool = {
                        "type": "function",
                        "function": {
                            "name": tool["name"],
                            "description": tool.get("description", ""),
                            "parameters": tool.get("inputSchema", {"type": "object"}),
                        },
                    }
                    self.available_tools.append(ollama_tool)
                logger.info(
                    "MCP client started and tools discovered",
                    client=name,
                    tool_count=len(tools),
                )
            except Exception as e:
                logger.error("Failed to start MCP client", client=name, error=str(e))

    async def _stop_mcp_clients(self):
        """Stop all MCP clients."""
        for name, client in self.mcp_clients.items():
            try:
                await client.stop()
                logger.debug("MCP client stopped", client=name)
            except Exception as e:
                logger.error("Error stopping MCP client", client=name, error=str(e))

    def _call_tool(self, tool_call: dict) -> str:
        """Execute a tool call via MCP client."""
        function_name = tool_call.get("function", {}).get("name", "")
        arguments = tool_call.get("function", {}).get("arguments", {})

        # Parse arguments if they're a string
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                return f"Error: Could not parse tool arguments: {arguments}"

        logger.debug(
            "Calling tool",
            function=function_name,
            arguments=arguments,
        )

        # Try each MCP client until we find one that has this tool
        for client_name, client in self.mcp_clients.items():
            try:
                # MCP client is still async, so we use a helper to run it sync
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                result = loop.run_until_complete(client.call_tool(function_name, arguments))
                
                # Extract content from result
                if isinstance(result, dict):
                    if "content" in result:
                        content = result["content"]
                        if isinstance(content, list):
                            text_parts = [
                                part["text"] for part in content 
                                if part.get("type") == "text"
                            ]
                            return "\n".join(text_parts)
                        return str(content)
                    return json.dumps(result)
                return str(result)
            except Exception as e:
                # Tool not found in this client or error occurred, try next
                continue

        return f"Error: Tool '{function_name}' not found in any MCP client."

    def _chat_with_tools(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
    ) -> dict:
        """Send a chat request to Ollama with optional tool support."""
        url = f"{self.base_url}/api/chat"
        
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }

        if tools:
            payload["tools"] = tools

        with httpx.Client() as client:
            response = client.post(url, json=payload, timeout=300.0)
            response.raise_for_status()
            return response.json()

    def receive_context(self, context: str):
        """Receive and store context for the next task."""
        logger.debug("Received context", context_length=len(context))
        self.context = context

    def classify_goal(self, goal: str) -> str:
        """Classify the goal type."""
        prompt = (
            f"Classify the following goal as 'simple' (one-off action, direct query, or single-step task) "
            f"or 'complex' (multi-step task, requires planning, file modifications, or research). "
            f"Goal: '{goal}'. Output only the word 'simple' or 'complex'."
        )
        
        try:
            response = self._chat_with_tools(
                messages=[{"role": "user", "content": prompt}]
            )
            content = response.get("message", {}).get("content", "").strip().lower()
            if "complex" in content:
                return "complex"
            return "simple"
        except Exception:
            return "simple"

    def decompose_goal(self, goal: str) -> list[AgentTask]:
        """Decompose a goal into tasks."""
        prompt = (
            f"Given the goal: '{goal}', decompose it into a sequence of sub-tasks. "
            f"Current context: '{self.context}'. "
            "Output the tasks in a JSON format matching this structure: "
            "{\"tasks\": [{\"id\": \"task1\", \"description\": \"...\", \"context\": \"...\", \"agent_type\": \"...\", \"verification_command\": \"...\", \"depends_on\": [\"task_id_1\"]}]}. "
            "agent_type should be 'planner' or 'executor'. "
            "Only output the JSON object, nothing else."
        )
        
        try:
            response = self._chat_with_tools(
                messages=[{"role": "user", "content": prompt}]
            )
            content = response.get("message", {}).get("content", "")
            # Try to extract JSON
            import re
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                task_data = json.loads(match.group(0))
                return [AgentTask(**t) for t in task_data.get("tasks", [])]
            return []
        except Exception as e:
            logger.error("decomposition_failed", error=str(e))
            return []

    def execute_task(
        self,
        task: AgentTask,
        progress: Optional[object] = None,
    ) -> AgentResult:
        """Execute a task using Ollama with tool-calling support."""
        # Start MCP clients if available
        if self.mcp_clients:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            loop.run_until_complete(self._start_mcp_clients())

        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        f"You are a helpful assistant. System Context:\n{self.context}\n"
                        "Think step by step and use tools as needed to accomplish the goal."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Task: {task.description}\nContext: {task.context}",
                },
            ]

            max_iterations = 10
            iteration = 0
            history = []

            while iteration < max_iterations:
                iteration += 1

                if progress and hasattr(progress, 'update'):
                    # progress is a callback or an object. Based on orchestrator, it's a callback.
                    pass

                try:
                    response = self._chat_with_tools(
                        messages=messages,
                        tools=self.available_tools if self.available_tools else None,
                    )
                except Exception as e:
                    logger.error("Ollama API error", error=str(e))
                    return AgentResult(
                        task_id=task.id,
                        success=False,
                        error=f"Ollama API error: {e}",
                        history=history,
                    )

                message = response.get("message", {})
                content = message.get("content", "")
                tool_calls = message.get("tool_calls", [])

                if content:
                    history.append(AgentAction(action_type="thought", content=content))

                # If there are tool calls, execute them and continue the conversation
                if tool_calls:
                    messages.append(message)

                    for tool_call in tool_calls:
                        func_name = tool_call.get("function", {}).get("name", "unknown")
                        args = tool_call.get("function", {}).get("arguments", {})
                        history.append(AgentAction(action_type="tool_call", content=func_name, metadata=args))
                        
                        tool_result = self._call_tool(tool_call)
                        history.append(AgentAction(action_type="tool_result", content=tool_result))

                        messages.append({
                            "role": "tool",
                            "name": func_name,
                            "content": tool_result,
                        })

                    continue

                return AgentResult(
                    task_id=task.id,
                    success=True,
                    output=content,
                    history=history,
                )

            return AgentResult(
                task_id=task.id,
                success=False,
                output="Maximum number of tool call iterations reached.",
                history=history,
            )

        finally:
            # Clean up MCP clients
            if self.mcp_clients:
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                loop.run_until_complete(self._stop_mcp_clients())

    def review_plan(self, plan: CollaborativePlan, role: AgentRole) -> PlanReview:
        """Review a plan from a specific role perspective."""
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
            response = self._chat_with_tools(
                messages=[{"role": "user", "content": prompt}]
            )
            content = response.get("message", {}).get("content", "")
            
            # Try to extract JSON
            import re
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                review_data = json.loads(match.group(0))
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
            logger.error("review_plan_failed", error=str(e))

        return PlanReview(
            original_plan_id=plan.goal,
            reviewers=[role],
            comments=[],
            approved=True,
            confidence_score=0.5,
        )
