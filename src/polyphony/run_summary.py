import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from .agent import AgentTask, AgentResult, AgentAction
from .cost import CostTracker

class RunSummary:
    def __init__(self, goal: str):
        self.goal = goal
        self.results: List[AgentResult] = []
        self.tasks: List[AgentTask] = []
        self.start_time = datetime.now()
        self.end_time = None
        self.cost_tracker = CostTracker()

    def add_result(self, task: AgentTask, result: AgentResult):
        self.results.append(result)
        self.tasks.append(task)

    def get_task_stats(self) -> Dict[str, int]:
        """Calculates task-based statistics (unique tasks)."""
        unique_task_ids = set()
        completed_task_ids = set()
        
        for task, result in zip(self.tasks, self.results):
            unique_task_ids.add(task.id)
            if result.success:
                completed_task_ids.add(task.id)
        
        return {
            "total": len(unique_task_ids),
            "successful": len(completed_task_ids)
        }

    def finalize(self):
        self.end_time = datetime.now()

    def to_markdown(self) -> str:
        duration = self.end_time - self.start_time if self.end_time else "N/A"

        md = f"# Polyphony Agent Run Summary\n\n"
        md += f"**Goal:** {self.goal}\n"
        md += f"**Start Time:** {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        md += f"**Duration:** {duration}\n\n"

        md += "## Execution Overview\n\n"
        stats = self.get_task_stats()
        total_tasks = stats["total"]
        successful_tasks = stats["successful"]
        md += f"- **Total Unique Tasks:** {total_tasks}\n"
        md += f"- **Successful Tasks:** {successful_tasks}\n"
        md += f"- **Total Attempts:** {len(self.results)}\n"
        md += f"- **Status:** {'[SUCCESS]' if successful_tasks == total_tasks and total_tasks > 0 else '[FAILED]'}\n"
        md += f"- **Total Cost:** ${self.cost_tracker.total_cost:.4f}\n\n"

        if self.cost_tracker.usage_by_model:
            md += "### Usage Breakdown\n\n"
            for model, usage in self.cost_tracker.usage_by_model.items():
                pricing = self.cost_tracker.get_pricing(model)
                model_cost = 0
                if pricing:
                    model_cost = (usage.prompt_tokens / 1_000_000.0 * pricing.input_1m) + \
                                 (usage.completion_tokens / 1_000_000.0 * pricing.output_1m)
                
                md += f"- **{model}:** {usage.prompt_tokens:,} input, {usage.completion_tokens:,} output (${model_cost:.4f})\n"
            md += "\n"

        md += "## Task Breakdown\n\n"
        for i, (task, result) in enumerate(zip(self.tasks, self.results)):
            status_marker = "[PASS]" if result.success else "[FAIL]"
            md += f"### {i+1}. {task.description} ({task.id}) {status_marker}\n\n"

            # Show task context if present (useful for understanding simple tasks)
            if task.context:
                md += f"**Context:** {task.context}\n"
            
            md += f"**Agent Model:** `{result.agent_model}`\n"
            if result.usage:
                md += f"**Tokens:** {result.usage.prompt_tokens:,} input, {result.usage.completion_tokens:,} output\n"
            
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
        stats = self.get_task_stats()
        total_tasks = stats["total"]
        successful_tasks = stats["successful"]
        duration = self.end_time - self.start_time if self.end_time else "N/A"
        
        summary = f"### Run: {self.goal}\n\n"
        summary += f"- **Date:** {self.start_time.strftime('%Y-%m-%d')}\n"
        summary += f"- **Duration:** {duration}\n"
        summary += f"- **Status:** {'[SUCCESS]' if successful_tasks == total_tasks and total_tasks > 0 else '[FAILED]'}\n"
        summary += f"- **Total Cost:** ${self.cost_tracker.total_cost:.4f}\n"
        summary += f"- **Tasks Completed:** {successful_tasks}/{total_tasks}\n\n"
        
        if successful_tasks == total_tasks and total_tasks > 0:
            summary += "**Completed Tasks:**\n"
            seen_descriptions = set()
            for task in self.tasks:
                if task.description not in seen_descriptions:
                    seen_descriptions.add(task.description)
                    summary += f"- {task.description}\n"
        
        return summary

    def update_documentation(self, base_dir: str = "."):
        """Documentation update is currently disabled to avoid cluttering README.md and GEMINI.md."""
        pass

    def to_json(self) -> Dict[str, Any]:
        duration = (self.end_time - self.start_time).total_seconds() if self.end_time else None
        stats = self.get_task_stats()
        total_tasks = stats["total"]
        successful_tasks = stats["successful"]
        
        return {
            "goal": self.goal,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration": duration,
            "total_cost": self.cost_tracker.total_cost,
            "tasks": [t.model_dump() for t in self.tasks],
            "results": [r.model_dump() for r in self.results],
            "usage_by_model": {m: u.model_dump() for m, u in self.cost_tracker.usage_by_model.items()},
            "status": "success" if successful_tasks == total_tasks and total_tasks > 0 else "failed",
            "task_stats": stats
        }

    def save(self, directory: str = "."):
        self.finalize()
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        import re
        # Sanitize slug: keep only alphanumeric and hyphens, replace others with hyphens
        slug = re.sub(r'[^a-z0-9\-]', '-', self.goal.lower())
        slug = re.sub(r'-+', '-', slug).strip('-')[:30]
        
        # Create logs directory if it doesn't exist
        logs_dir = os.path.join(directory, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        
        # Save Markdown summary
        md_filename = f"polyphony-run-{slug}-{timestamp}.md"
        md_path = os.path.join(logs_dir, md_filename)
        with open(md_path, "w") as f:
            f.write(self.to_markdown())
            
        # Save JSON summary
        json_filename = f"polyphony-run-{slug}-{timestamp}.json"
        json_path = os.path.join(logs_dir, json_filename)
        with open(json_path, "w") as f:
            json.dump(self.to_json(), f, indent=2)
        
        # Update documentation after successful runs
        self.update_documentation(directory)
        
        return md_path
