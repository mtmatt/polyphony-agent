"""
Todo CLI with Pydantic models and JSON storage.
"""

import sys
import argparse
from pathlib import Path

from typing import List
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from models import Task, TaskList, TaskMetadata

# Initialize rich console
console = Console()

# JSON file path
TASKS_FILE = Path("tasks.json")


def load_tasks() -> TaskList:
    """
    Load tasks from tasks.json using Pydantic's serialization.
    Creates a new TaskList if file doesn't exist or is invalid.
    """
    if not TASKS_FILE.exists():
        task_list = TaskList()
        save_tasks(task_list)
        return task_list

    try:
        return TaskList.from_json(TASKS_FILE.read_text(encoding="utf-8"))
    except (ValueError, Exception) as e:
        backup_path = TASKS_FILE.with_suffix(".json.bak")
        try:
            TASKS_FILE.rename(backup_path)
            console.print(f"[yellow]Warning: Could not load tasks: {e}. Corrupted file moved to {backup_path}. Starting fresh.[/]")
        except Exception as rename_err:
            console.print(f"[red]Error: Could not backup corrupted tasks file: {rename_err}[/]")
        return TaskList()


def save_tasks(task_list: TaskList) -> None:
    """
    Save tasks to tasks.json using TaskList's atomic save method.
    """
    try:
        task_list.save_to_file(TASKS_FILE)
    except Exception as e:
        console.print(f"[red]Error saving tasks: {e}[/]")
        sys.exit(1)


def handle_add(args, task_list: TaskList):
    """Add a new task."""
    try:
        # Strip whitespace from tags and filter empty ones
        tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
        task = task_list.add_task(
            description=args.description, 
            priority=args.priority,
            tags=tags
        )
        save_tasks(task_list)
        console.print(f"[green]Added task {task.id}:[/] {task.description} ({task.metadata.priority})")
    except ValidationError as e:
        console.print(f"[red]Error adding task:[/] {str(e)}")
        sys.exit(1)


def handle_list(args, task_list: TaskList):
    """List all tasks."""
    console.print(task_list.to_rich_table())


def handle_done(args, task_list: TaskList):
    """Mark a task as done."""
    task = task_list.get_task(args.task_id)
    if not task:
        console.print(f"[red]Error: Task {args.task_id} not found.[/]")
        sys.exit(1)
    
    task.mark_completed()
    save_tasks(task_list)
    console.print(f"[green]Task {args.task_id} marked as completed.[/]")


def handle_remove(args, task_list: TaskList):
    """Remove a task."""
    if task_list.remove_task(args.task_id):
        save_tasks(task_list)
        console.print(f"[green]Task {args.task_id} removed.[/]")
    else:
        console.print(f"[red]Error: Task {args.task_id} not found.[/]")
        sys.exit(1)


def handle_edit(args, task_list: TaskList):
    """Edit a task description."""
    task = task_list.get_task(args.task_id)
    if not task:
        console.print(f"[red]Error: Task {args.task_id} not found.[/]")
        sys.exit(1)
    
    old_desc = task.description
    task.description = args.description
    save_tasks(task_list)
    console.print(f"[green]Task {args.task_id} description updated:[/] {old_desc} -> {task.description}")


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(description="Todo CLI - Pydantic 3.14 Edition")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # add command
    add_parser = subparsers.add_parser("add", help="Add a new task")
    add_parser.add_argument("description", type=str, help="Task description")
    add_parser.add_argument("--priority", type=str, choices=["low", "medium", "high"], default="medium", help="Task priority")
    add_parser.add_argument("--tags", type=str, help="Comma-separated tags")

    # list command
    subparsers.add_parser("list", help="List all tasks")

    # done command
    done_parser = subparsers.add_parser("done", help="Mark a task as done")
    done_parser.add_argument("task_id", type=int, help="ID of the task to mark as done")

    # remove command
    remove_parser = subparsers.add_parser("remove", help="Remove a task")
    remove_parser.add_argument("task_id", type=int, help="ID of the task to remove")

    # edit command
    edit_parser = subparsers.add_parser("edit", help="Edit a task description")
    edit_parser.add_argument("task_id", type=int, help="ID of the task to edit")
    edit_parser.add_argument("description", type=str, help="New description")

    args = parser.parse_args()
    
    # Load tasks
    task_list = load_tasks()

    if args.command == "add":
        handle_add(args, task_list)
    elif args.command == "list":
        handle_list(args, task_list)
    elif args.command == "done":
        handle_done(args, task_list)
    elif args.command == "remove":
        handle_remove(args, task_list)
    elif args.command == "edit":
        handle_edit(args, task_list)
    else:
        # If no command provided, show list by default or help
        handle_list(args, task_list)


if __name__ == "__main__":
    main()
