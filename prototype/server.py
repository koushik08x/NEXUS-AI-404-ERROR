from fastmcp import FastMCP
from datetime import datetime
import uuid

mcp = FastMCP("NEXUS AI - Task Manager")

tasks = []

@mcp.tool()
def create_task(title: str, description: str = "") -> dict:
    """Create a new task in NEXUS AI."""
    task = {
        "id": str(uuid.uuid4())[:8],
        "title": title,
        "description": description,
        "completed": False,
        "created_at": datetime.now().isoformat()
    }
    tasks.append(task)
    return task


@mcp.tool()
def list_tasks() -> list:
    """List all tasks stored in NEXUS AI."""
    return tasks


@mcp.tool()
def complete_task(task_id: str) -> str:
    """Mark a task as completed using its ID."""
    for task in tasks:
        if task["id"] == task_id:
            task["completed"] = True
            return f"Task '{task['title']}' completed successfully."

    return "Task not found."


@mcp.tool()
def get_status() -> dict:
    """Get NEXUS AI task statistics."""
    return {
        "total_tasks": len(tasks),
        "completed": sum(t["completed"] for t in tasks),
        "pending": sum(not t["completed"] for t in tasks)
    }


if __name__ == "__main__":
    mcp.run()