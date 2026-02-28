import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from .agent import AgentTask, AgentResult, AgentAction

class RunSummary:
    def __init__(self, goal: str):
        self.goal = goal
        self.results: List[AgentResult] = []
        self.tasks: List[AgentTask] = []
        self.start_time = datetime.now()
        self.end_time = None

    def add_result(self, task: AgentTask, result: AgentResult):
        self.results.append(result)
        self.tasks.append(task)

    def finalize(self):
        self.end_time = datetime.now()

    def to_markdown(self) -> str:
        duration = self.end_time - self.start_time if self.end_time else "N/A"
        
        md = f"# Polyphony Agent Run Summary\n\n"
        md += f"**Goal:** {self.goal}\n"
        md += f"**Start Time:** {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        md += f"**Duration:** {duration}\n\n"
        
        md += "## Execution Overview\n\n"
        total_tasks = len(self.tasks)
        successful_tasks = sum(1 for r in self.results if r.success)
        md += f"- **Total Tasks:** {total_tasks}\n"
        md += f"- **Successful Tasks:** {successful_tasks}\n"
        md += f"- **Status:** {'✅ Success' if successful_tasks == total_tasks and total_tasks > 0 else '❌ Partial/Failure'}\n\n"
        
        md += "## Task Breakdown\n\n"
        for i, (task, result) in enumerate(zip(self.tasks, self.results)):
            status_emoji = "✅" if result.success else "❌"
            md += f"### {i+1}. {task.description} ({task.id}) {status_emoji}\n\n"
            
            if result.error:
                md += f"**Error:** {result.error}\n\n"
            
            if result.history:
                md += "#### Process History\n\n"
                for action in result.history:
                    if action.action_type == "thought":
                        md += f"> **Thought:** {action.content}\n\n"
                    elif action.action_type == "tool_call":
                        args_str = json.dumps(action.metadata, indent=2) if action.metadata else ""
                        md += f"🛠 **Tool Call:** `{action.content}`\n"
                        if args_str:
                            md += f"```json\n{args_str}\n```\n"
                    elif action.action_type == "tool_result":
                        md += f"📥 **Tool Result:**\n```\n{action.content}\n```\n\n"
            
            if result.verification_output:
                md += "#### Verification Output\n\n"
                md += f"```\n{result.verification_output}\n```\n\n"
                
            md += "---\n\n"
            
        return md

    def save(self, directory: str = "."):
        self.finalize()
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        slug = self.goal.lower().replace(" ", "-")[:30]
        filename = f"polyphony-run-{slug}-{timestamp}.md"
        path = os.path.join(directory, filename)
        
        with open(path, "w") as f:
            f.write(self.to_markdown())
        
        return path
