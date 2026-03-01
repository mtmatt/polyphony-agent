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
        md += f"- **Status:** {'[SUCCESS]' if successful_tasks == total_tasks and total_tasks > 0 else '[FAILED]'}\n\n"

        md += "## Task Breakdown\n\n"
        for i, (task, result) in enumerate(zip(self.tasks, self.results)):
            status_marker = "[PASS]" if result.success else "[FAIL]"
            md += f"### {i+1}. {task.description} ({task.id}) {status_marker}\n\n"

            # Show task context if present (useful for understanding simple tasks)
            if task.context:
                md += f"**Context:** {task.context}\n"
            
            md += f"**Agent Model:** `{result.agent_model}`\n"
            if result.duration:
                md += f"**Task Duration:** {result.duration:.2f}s\n"

            if result.commit_hash:
                md += f"**Commit Hash:** `{result.commit_hash[:7]}`\n"

            if result.files_changed:
                md += "**Files Modified:**\n"
                for f in result.files_changed:
                    md += f"- `{f}`\n"
                md += "\n"

            if result.error:
                md += f"**Error:** {result.error}\n\n"

            # Always show output if present
            if result.output:
                md += "#### Output\n\n"
                md += f"```\n{result.output}\n```\n\n"

            if result.history:
                md += "<details>\n<summary><b>Process History</b></summary>\n\n"
                for action in result.history:
                    if action.action_type == "thought":
                        md += f"> **Thought:** {action.content}\n\n"
                    elif action.action_type == "tool_call":
                        args_str = json.dumps(action.metadata, indent=2) if action.metadata else ""
                        md += f"[TOOL] **Tool Call:** `{action.content}`\n"
                        if args_str:
                            md += f"```json\n{args_str}\n```\n"
                    elif action.action_type == "tool_result":
                        md += f"[RESULT] **Tool Result:**\n```\n{action.content[:500]}{'...' if len(action.content) > 500 else ''}\n```\n\n"
                md += "</details>\n\n"

            if result.verification_output:
                md += "#### Verification Output\n\n"
                md += f"```\n{result.verification_output}\n```\n\n"

            md += "---\n\n"

        return md

    def generate_summary(self) -> str:
        """Generate a brief summary of the run for documentation updates."""
        total_tasks = len(self.tasks)
        successful_tasks = sum(1 for r in self.results if r.success)
        duration = self.end_time - self.start_time if self.end_time else "N/A"
        
        summary = f"### Run: {self.goal}\n\n"
        summary += f"- **Date:** {self.start_time.strftime('%Y-%m-%d')}\n"
        summary += f"- **Duration:** {duration}\n"
        summary += f"- **Status:** {'[SUCCESS]' if successful_tasks == total_tasks and total_tasks > 0 else '[FAILED]'}\n"
        summary += f"- **Tasks Completed:** {successful_tasks}/{total_tasks}\n\n"
        
        if successful_tasks == total_tasks and total_tasks > 0:
            summary += "**Completed Tasks:**\n"
            for task in self.tasks:
                summary += f"- {task.description}\n"
        
        return summary

    def update_documentation(self, base_dir: str = "."):
        """Update GEMINI.md and README.md with run summary."""
        import re
        
        total_tasks = len(self.tasks)
        successful_tasks = sum(1 for r in self.results if r.success)
        
        # Only update docs for fully successful runs with meaningful tasks
        if successful_tasks != total_tasks or total_tasks == 0:
            return
        
        summary = self.generate_summary()
        
        # Update GEMINI.md
        gemini_path = os.path.join(base_dir, "GEMINI.md")
        if os.path.exists(gemini_path):
            with open(gemini_path, "r") as f:
                content = f.read()
            
            # Look for a "Recent Runs" or similar section, or create one
            if "# Recent Runs" in content:
                # Append to existing section
                content = re.sub(
                    r"(# Recent Runs.*?\n\n)",
                    r"\1" + summary + "\n",
                    content,
                    flags=re.DOTALL
                )
            else:
                # Add section at the end
                content += f"\n\n# Recent Runs\n\n{summary}"
            
            with open(gemini_path, "w") as f:
                f.write(content)
        
        # Update README.md - just note the latest execution
        readme_path = os.path.join(base_dir, "README.md")
        if os.path.exists(readme_path):
            with open(readme_path, "r") as f:
                content = f.read()
            
            # Look for a "Recent Activity" section
            recent_note = f"_Last successful run: {self.start_time.strftime('%Y-%m-%d')} - {self.goal}_\n"
            
            if "## Recent Activity" in content:
                content = re.sub(
                    r"## Recent Activity\n\n.*?(?=\n##|$)",
                    f"## Recent Activity\n\n{recent_note}",
                    content,
                    flags=re.DOTALL
                )
            else:
                # Add at the end
                content += f"\n\n## Recent Activity\n\n{recent_note}"
            
            with open(readme_path, "w") as f:
                f.write(content)

    def save(self, directory: str = "."):
        self.finalize()
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        import re
        # Sanitize slug: keep only alphanumeric and hyphens, replace others with hyphens
        slug = re.sub(r'[^a-z0-9\-]', '-', self.goal.lower())
        slug = re.sub(r'-+', '-', slug).strip('-')[:30]
        filename = f"polyphony-run-{slug}-{timestamp}.md"
        
        # Create logs directory if it doesn't exist
        logs_dir = os.path.join(directory, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        
        path = os.path.join(logs_dir, filename)
        
        with open(path, "w") as f:
            f.write(self.to_markdown())
        
        # Update documentation after successful runs
        self.update_documentation(directory)
        
        return path
