import os
import tempfile
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Self
from pydantic import BaseModel, Field, model_validator


class TaskMetadata(BaseModel):
    """Additional metadata for a task."""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tags: list[str] = Field(default_factory=list)
    priority: str = Field(default="medium", pattern="^(low|medium|high)$")
    extra: dict[str, Any] = Field(default_factory=dict)


class Task(BaseModel):
    """Represents a single todo task with unique ID, description, and metadata."""
    id: int = Field(..., description="Unique identifier for the task")
    description: str = Field(..., min_length=1, description="Description of the task")
    completed: bool = Field(default=False, description="Whether the task is completed")
    metadata: TaskMetadata = Field(default_factory=TaskMetadata, description="Task metadata")

    def mark_completed(self) -> None:
        """Mark task as completed."""
        self.completed = True

    def mark_incomplete(self) -> None:
        """Mark task as incomplete."""
        self.completed = False


class TaskList(BaseModel):
    """Represents a collection of tasks."""
    tasks: list[Task] = Field(default_factory=list, description="List of tasks")
    last_id: int = Field(default=0, description="The last ID used for a task to guarantee uniqueness")

    @model_validator(mode="after")
    def validate_last_id(self) -> "TaskList":
        """Ensure last_id is at least as large as the max task ID in the list."""
        if self.tasks:
            max_id = max(task.id for task in self.tasks)
            if self.last_id < max_id:
                self.last_id = max_id
        return self

    def add_task(self, description: str, priority: str = "medium", tags: list[str] | None = None, task_id: int | None = None) -> Task:
        """Add a new task to the list with a guaranteed unique, monotonically increasing ID."""
        if task_id is None:
            # Ensure last_id is at least the max current ID
            if self.tasks:
                max_current = max(t.id for t in self.tasks)
                if self.last_id < max_current:
                    self.last_id = max_current
            task_id = self.last_id + 1
        
        # Update last_id to reflect the newly used ID
        if task_id > self.last_id:
            self.last_id = task_id
        
        metadata = TaskMetadata(priority=priority, tags=tags or [])
        task = Task(id=task_id, description=description, metadata=metadata)
        self.tasks.append(task)
        return task

    def get_task(self, task_id: int) -> Task | None:
        """Get a task by ID."""
        return next((task for task in self.tasks if task.id == task_id), None)

    def remove_task(self, task_id: int) -> bool:
        """Remove a task by ID. Returns True if removed, False if not found."""
        initial_count = len(self.tasks)
        self.tasks = [task for task in self.tasks if task.id != task_id]
        return len(self.tasks) < initial_count

    def get_completed_tasks(self) -> list[Task]:
        """Get all completed tasks."""
        return [task for task in self.tasks if task.completed]

    def get_pending_tasks(self) -> list[Task]:
        """Get all pending (incomplete) tasks."""
        return [task for task in self.tasks if not task.completed]

    def to_rich_table(self):
        """Return a rich Table representation of the tasks."""
        from rich.table import Table
        table = Table(title="Todo Tasks")
        table.add_column("ID", justify="right", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Description", style="white")
        table.add_column("Priority", justify="center")
        table.add_column("Created At", justify="center", style="dim")
        table.add_column("Tags", style="blue")

        for task in self.tasks:
            status = "[green]✓[/]" if task.completed else "[red]○[/]"
            tags = ", ".join(task.metadata.tags) if task.metadata.tags else "-"
            # Format datetime for better readability
            created_str = task.metadata.created_at.strftime("%Y-%m-%d %H:%M")
            table.add_row(
                str(task.id), 
                status, 
                task.description, 
                task.metadata.priority,
                created_str,
                tags
            )
        return table

    def save_to_file(self, file_path: str | Path) -> None:
        """
        Save tasks to a JSON file atomically.
        Updates the file atomically and ensures data is flushed to disk.
        """
        path = Path(file_path)
        # Ensure directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Atomic write: write to temp file then rename
        # Use the same directory to ensure it's on the same filesystem for os.replace
        fd, temp_path = tempfile.mkstemp(dir=path.parent, text=True, prefix=f".{path.name}_tmp_")
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(self.to_json())
                f.flush()
                os.fsync(f.fileno())
            
            # Preserve permissions if original file exists
            if path.exists():
                shutil.copymode(path, temp_path)
                
            os.replace(temp_path, path)
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise e

    @classmethod
    def from_json(cls, json_data: str) -> Self:
        """Create a TaskList from a JSON string."""
        return cls.model_validate_json(json_data)

    def to_json(self) -> str:
        """Convert TaskList to a JSON string."""
        return self.model_dump_json(indent=2)
