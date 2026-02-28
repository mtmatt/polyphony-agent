# Todo App Spec
Implement a simple Todo management CLI tool called `todo_cli.py`.

Requirements:
- Store tasks in a local `tasks.json` file.
- Commands:
    - `add`: Add a new task (e.g., `todo_cli add "Buy milk"`).
    - `list`: Show all tasks with their IDs and completion status.
    - `done`: Mark a task as complete by its ID (e.g., `todo_cli done 1`).
    - `remove`: Delete a task by its ID.
- Use `rich` to display the tasks in a nice table.
- Ensure the JSON file is created if it doesn't exist.
