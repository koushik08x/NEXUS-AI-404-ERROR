import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

DB_PATH = Path(__file__).resolve().parent / "nexus.db"

def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    target_path = db_path or DB_PATH
    conn = sqlite3.connect(target_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: Optional[Path] = None):
    """Initialize database tables with schema migrations."""
    target_path = db_path or DB_PATH
    with get_connection(target_path) as conn:
        cursor = conn.cursor()

        # 1. Tasks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                completed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                completed_at TEXT
            )
        """)

        # 2. Activity logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                arguments TEXT DEFAULT '{}',
                result TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'success'
            )
        """)

        # 3. Meetings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS meetings (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                transcript TEXT NOT NULL,
                summary TEXT NOT NULL,
                decisions TEXT NOT NULL,
                action_items TEXT NOT NULL
            )
        """)

        # 4. Approvals table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS approvals (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                operation TEXT NOT NULL,
                details TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                resolution_time TEXT
            )
        """)
        conn.commit()

# --- Task Operations ---

def db_create_task(title: str, description: str = "", task_id: Optional[str] = None) -> Dict[str, Any]:
    init_db()
    tid = task_id or str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tasks (id, title, description, completed, created_at) VALUES (?, ?, ?, 0, ?)",
            (tid, title, description, now)
        )
        conn.commit()
    return {
        "id": tid,
        "title": title,
        "description": description,
        "completed": False,
        "created_at": now
    }

def db_list_tasks() -> List[Dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, description, completed, created_at, completed_at FROM tasks ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [
            {
                "id": r["id"],
                "title": r["title"],
                "description": r["description"] or "",
                "completed": bool(r["completed"]),
                "created_at": r["created_at"],
                "completed_at": r["completed_at"]
            }
            for r in rows
        ]

def db_complete_task(task_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    now = datetime.now().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        task = cursor.fetchone()
        if not task:
            return None
        cursor.execute("UPDATE tasks SET completed = 1, completed_at = ? WHERE id = ?", (now, task_id))
        conn.commit()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        updated = cursor.fetchone()
        return {
            "id": updated["id"],
            "title": updated["title"],
            "description": updated["description"] or "",
            "completed": True,
            "created_at": updated["created_at"],
            "completed_at": updated["completed_at"]
        }

def db_delete_task(task_id: str) -> bool:
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted

def db_get_status() -> Dict[str, int]:
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tasks")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE completed = 1")
        completed = cursor.fetchone()[0]
        pending = total - completed
        return {
            "total_tasks": total,
            "completed": completed,
            "pending": pending
        }

# --- Activity Logging ---

def db_log_activity(tool_name: str, arguments: Any = None, result: Any = None, status: str = "success"):
    init_db()
    now = datetime.now().isoformat()
    args_str = json.dumps(arguments, ensure_ascii=False) if isinstance(arguments, (dict, list)) else str(arguments or "")
    res_str = json.dumps(result, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result or "")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO activity_logs (timestamp, tool_name, arguments, result, status) VALUES (?, ?, ?, ?, ?)",
            (now, tool_name, args_str, res_str, status)
        )
        conn.commit()

def db_get_activity_logs(limit: int = 50) -> List[Dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, timestamp, tool_name, arguments, result, status FROM activity_logs ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        return [
            {
                "id": r["id"],
                "timestamp": r["timestamp"],
                "tool_name": r["tool_name"],
                "arguments": r["arguments"],
                "result": r["result"],
                "status": r["status"]
            }
            for r in rows
        ]

# --- Meeting Intelligence ---

def db_save_meeting(transcript: str, summary: str, decisions: List[str], action_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    init_db()
    mid = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    dec_json = json.dumps(decisions, ensure_ascii=False)
    act_json = json.dumps(action_items, ensure_ascii=False)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO meetings (id, created_at, transcript, summary, decisions, action_items) VALUES (?, ?, ?, ?, ?, ?)",
            (mid, now, transcript, summary, dec_json, act_json)
        )
        conn.commit()
    return {
        "id": mid,
        "created_at": now,
        "transcript": transcript,
        "summary": summary,
        "decisions": decisions,
        "action_items": action_items
    }

def db_get_latest_meeting() -> Optional[Dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM meetings ORDER BY created_at DESC LIMIT 1")
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "transcript": row["transcript"],
            "summary": row["summary"],
            "decisions": json.loads(row["decisions"]) if row["decisions"] else [],
            "action_items": json.loads(row["action_items"]) if row["action_items"] else []
        }

# --- Human Approvals ---

def db_create_approval(operation: str, details: Dict[str, Any]) -> Dict[str, Any]:
    init_db()
    aid = "appr-" + str(uuid.uuid4())[:6]
    now = datetime.now().isoformat()
    det_json = json.dumps(details, ensure_ascii=False)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO approvals (id, created_at, operation, details, status) VALUES (?, ?, ?, ?, 'pending')",
            (aid, now, operation, det_json)
        )
        conn.commit()
    return {
        "id": aid,
        "created_at": now,
        "operation": operation,
        "details": details,
        "status": "pending"
    }

def db_list_approvals(status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        if status_filter:
            cursor.execute("SELECT * FROM approvals WHERE status = ? ORDER BY created_at DESC", (status_filter,))
        else:
            cursor.execute("SELECT * FROM approvals ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [
            {
                "id": r["id"],
                "created_at": r["created_at"],
                "operation": r["operation"],
                "details": json.loads(r["details"]) if r["details"] else {},
                "status": r["status"],
                "resolution_time": r["resolution_time"]
            }
            for r in rows
        ]

def db_resolve_approval(approval_id: str, decision: str) -> Optional[Dict[str, Any]]:
    """decision: 'approved' or 'rejected'"""
    init_db()
    now = datetime.now().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,))
        appr = cursor.fetchone()
        if not appr:
            return None
        if appr["status"] != "pending":
            return {
                "id": appr["id"],
                "operation": appr["operation"],
                "details": json.loads(appr["details"]) if appr["details"] else {},
                "status": appr["status"],
                "resolution_time": appr["resolution_time"],
                "error": f"Approval already resolved as {appr['status']}"
            }
        cursor.execute(
            "UPDATE approvals SET status = ?, resolution_time = ? WHERE id = ?",
            (decision, now, approval_id)
        )
        conn.commit()
        return {
            "id": appr["id"],
            "operation": appr["operation"],
            "details": json.loads(appr["details"]) if appr["details"] else {},
            "status": decision,
            "resolution_time": now
        }
