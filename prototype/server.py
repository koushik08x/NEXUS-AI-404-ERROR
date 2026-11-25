from fastmcp import FastMCP
from pathlib import Path
import sys

# Ensure prototype directory is on sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from database import (
    init_db,
    db_create_task,
    db_list_tasks,
    db_complete_task,
    db_delete_task,
    db_get_status,
    db_log_activity,
    db_create_approval,
    db_list_approvals
)

# Initialize database tables on server load
init_db()

mcp = FastMCP("NEXUS AI - Task Manager")


@mcp.tool()
def create_task(title: str, description: str = "") -> dict:
    """Create a new task in NEXUS AI and persist it to SQLite database."""
    try:
        task = db_create_task(title=title, description=description)
        db_log_activity("create_task", {"title": title, "description": description}, task, "success")
        return task
    except Exception as e:
        db_log_activity("create_task", {"title": title, "description": description}, str(e), "error")
        raise e


@mcp.tool()
def list_tasks() -> list:
    """List all tasks stored persistently in the NEXUS AI SQLite database."""
    try:
        tasks = db_list_tasks()
        db_log_activity("list_tasks", {}, {"count": len(tasks)}, "success")
        return tasks
    except Exception as e:
        db_log_activity("list_tasks", {}, str(e), "error")
        raise e


@mcp.tool()
def complete_task(task_id: str) -> str:
    """Mark a task as completed in SQLite using its ID."""
    try:
        task = db_complete_task(task_id)
        if task:
            msg = f"Task '{task['title']}' completed successfully."
            db_log_activity("complete_task", {"task_id": task_id}, msg, "success")
            return msg
        else:
            msg = f"Task with ID '{task_id}' not found."
            db_log_activity("complete_task", {"task_id": task_id}, msg, "warning")
            return msg
    except Exception as e:
        db_log_activity("complete_task", {"task_id": task_id}, str(e), "error")
        raise e


@mcp.tool()
def get_status() -> dict:
    """Get NEXUS AI workspace task statistics from SQLite."""
    try:
        status = db_get_status()
        db_log_activity("get_status", {}, status, "success")
        return status
    except Exception as e:
        db_log_activity("get_status", {}, str(e), "error")
        raise e


@mcp.tool()
def delete_task(task_id: str, approval_id: str = "") -> dict:
    """Delete a task from NEXUS AI. SENSITIVE OPERATION: Requires an approved approval_id."""
    if not approval_id:
        appr = db_create_approval("delete_task", {"task_id": task_id})
        res = {
            "status": "approval_required",
            "approval_id": appr["id"],
            "message": f"Sensitive operation: Deleting task {task_id} requires human approval. Approval request {appr['id']} has been submitted."
        }
        db_log_activity("delete_task", {"task_id": task_id}, res, "pending_approval")
        return res

    # Verify approval status
    approvals = db_list_approvals()
    matching = [a for a in approvals if a["id"] == approval_id]
    if not matching or matching[0]["status"] != "approved":
        res = {
            "status": "rejected",
            "message": f"Action blocked: Approval '{approval_id}' is not approved."
        }
        db_log_activity("delete_task", {"task_id": task_id, "approval_id": approval_id}, res, "rejected")
        return res

    deleted = db_delete_task(task_id)
    if deleted:
        res = {"status": "success", "message": f"Task '{task_id}' was successfully deleted following approved authorization."}
    else:
        res = {"status": "error", "message": f"Task '{task_id}' could not be found to delete."}
    db_log_activity("delete_task", {"task_id": task_id, "approval_id": approval_id}, res, "success" if deleted else "error")
    return res


if __name__ == "__main__":
    mcp.run()
