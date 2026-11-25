import os
import sys
import json
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List

from dotenv import load_dotenv
from google import genai
from google.genai import types

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import Client

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nexus-backend")

# ==============================
# PATHS & CONFIGURATION
# ==============================

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
SERVER_SCRIPT = BASE_DIR / "server.py"

# Ensure prototype directory is in sys.path
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from database import (
    init_db,
    db_get_activity_logs,
    db_save_meeting,
    db_get_latest_meeting,
    db_create_approval,
    db_list_approvals,
    db_resolve_approval,
    db_delete_task,
    db_log_activity
)

# Load environment variables (.env in prototype or repo root)
load_dotenv(dotenv_path=BASE_DIR / ".env")
load_dotenv(dotenv_path=REPO_ROOT / ".env")
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Initialize Gemini Client if API key is present
gemini_client: Optional[genai.Client] = None
if GEMINI_API_KEY and GEMINI_API_KEY.strip() and GEMINI_API_KEY != "your_gemini_api_key_here":
    try:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info(f"Initialized Gemini client with model '{GEMINI_MODEL}'.")
    except Exception as e:
        logger.error(f"Failed to initialize Gemini client: {e}")
        gemini_client = None

mcp_client: Optional[Client] = None

# Initialize SQLite database
init_db()

# ==============================
# GEMINI MCP TOOLS SCHEMA
# ==============================

GEMINI_TOOLS = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="create_task",
                description="Create a new task in NEXUS AI workspace and persist it to SQLite database.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "title": types.Schema(type=types.Type.STRING, description="The title or short summary of the task to create"),
                        "description": types.Schema(type=types.Type.STRING, description="Optional additional details, context, or notes for the task")
                    },
                    required=["title"]
                )
            ),
            types.FunctionDeclaration(
                name="list_tasks",
                description="List all existing tasks and their completion status from the database.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={}
                )
            ),
            types.FunctionDeclaration(
                name="complete_task",
                description="Mark an existing task as completed in the database using its unique task ID.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "task_id": types.Schema(type=types.Type.STRING, description="The unique 8-character ID of the task to complete")
                    },
                    required=["task_id"]
                )
            ),
            types.FunctionDeclaration(
                name="get_status",
                description="Get aggregate summary metrics of workspace tasks (total, completed, pending).",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={}
                )
            ),
            types.FunctionDeclaration(
                name="delete_task",
                description="Delete a task from the workspace. SENSITIVE: requires human approval before proceeding.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "task_id": types.Schema(type=types.Type.STRING, description="The unique ID of the task to delete"),
                        "approval_id": types.Schema(type=types.Type.STRING, description="Approved authorization ID if already granted by human")
                    },
                    required=["task_id"]
                )
            )
        ]
    )
]

# ==============================
# MCP RESULT EXTRACTOR
# ==============================

def extract_result(result):
    if result is None:
        return None
    if hasattr(result, "structured_content") and result.structured_content is not None:
        return result.structured_content
    if hasattr(result, "data") and result.data is not None:
        return result.data
    if hasattr(result, "content") and result.content:
        for item in result.content:
            if hasattr(item, "text"):
                try:
                    return json.loads(item.text)
                except (json.JSONDecodeError, TypeError):
                    return item.text
    return result


# ==============================
# LIFECYCLE
# ==============================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global mcp_client
    logger.info(f"Connecting to FastMCP server script at: {SERVER_SCRIPT}")
    async with Client(SERVER_SCRIPT) as client:
        mcp_client = client
        logger.info("NEXUS FastMCP Server Connected successfully via stdio transport!")
        if gemini_client:
            logger.info("NEXUS Gemini AI client connected and configured.")
        else:
            logger.warning("Gemini API key is not configured or placeholder detected.")
        yield
    mcp_client = None
    logger.info("NEXUS FastMCP Server disconnected.")


# ==============================
# FASTAPI APP
# ==============================

app = FastAPI(
    title="NEXUS AI Backend",
    description="MCP-Powered Personal Intelligence System with SQLite & Gemini",
    version="3.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)


# ==============================
# CORE & HEALTH ROUTES
# ==============================

@app.get("/")
def home():
    return {
        "message": "NEXUS AI Backend Running",
        "status": "online",
        "gemini": bool(gemini_client),
        "model": GEMINI_MODEL,
        "mcp_connected": bool(mcp_client)
    }


# ==============================
# TASK ROUTES (MCP DELEGATED)
# ==============================

@app.get("/api/tasks")
async def list_tasks():
    if not mcp_client:
        raise HTTPException(status_code=503, detail="MCP server is not connected.")
    result = await mcp_client.call_tool("list_tasks", {})
    return extract_result(result)


@app.post("/api/tasks")
async def create_task(data: dict):
    if not mcp_client:
        raise HTTPException(status_code=503, detail="MCP server is not connected.")
    title = data.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Task title is required.")
    result = await mcp_client.call_tool(
        "create_task",
        {
            "title": title,
            "description": data.get("description", "").strip()
        }
    )
    return extract_result(result)


@app.post("/api/complete/{task_id}")
async def complete_task(task_id: str):
    if not mcp_client:
        raise HTTPException(status_code=503, detail="MCP server is not connected.")
    result = await mcp_client.call_tool("complete_task", {"task_id": task_id})
    return {"result": extract_result(result)}


@app.post("/api/delete/{task_id}")
async def delete_task(task_id: str, data: dict = None):
    if not mcp_client:
        raise HTTPException(status_code=503, detail="MCP server is not connected.")
    approval_id = (data or {}).get("approval_id", "")
    result = await mcp_client.call_tool("delete_task", {"task_id": task_id, "approval_id": approval_id})
    return extract_result(result)


@app.get("/api/status")
async def get_status():
    if not mcp_client:
        raise HTTPException(status_code=503, detail="MCP server is not connected.")
    result = await mcp_client.call_tool("get_status", {})
    return extract_result(result)


# ==============================
# GEMINI NATURAL-LANGUAGE AGENT
# ==============================

@app.post("/api/command")
async def process_command(data: dict):
    command = data.get("command", "").strip()
    if not command:
        return {"message": "Please enter a command."}

    if not mcp_client:
        raise HTTPException(status_code=503, detail="MCP Server is not connected.")

    if not gemini_client:
        raise HTTPException(
            status_code=503,
            detail="Gemini API key is not configured. Please set GEMINI_API_KEY in your .env file."
        )

    try:
        config = types.GenerateContentConfig(
            tools=GEMINI_TOOLS,
            temperature=0.1,
            system_instruction=(
                "You are NEXUS AI, an autonomous intelligence coordinator. "
                "Analyze user requests and select the appropriate MCP tool to execute. "
                "When creating tasks, extract a clear title and description. "
                "When completing or deleting tasks, use the exact task ID if known. "
                "If the user asks general questions or greets you, provide a helpful answer without calling tools."
            )
        )

        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=command,
            config=config
        )

        # Check if Gemini executed native function calling
        if response.function_calls:
            results_list = []
            for call in response.function_calls:
                fn_name = call.name
                fn_args = dict(call.args) if call.args else {}

                logger.info(f"Gemini selected native function call: {fn_name} with args: {fn_args}")

                # Execute through the FastMCP client
                mcp_res = await mcp_client.call_tool(fn_name, fn_args)
                extracted = extract_result(mcp_res)
                results_list.append({
                    "tool": fn_name,
                    "arguments": fn_args,
                    "result": extracted
                })

            primary_res = results_list[0] if len(results_list) == 1 else results_list
            return {
                "action": results_list[0]["tool"],
                "message": f"Gemini autonomously selected and executed '{results_list[0]['tool']}' via MCP.",
                "function_call": results_list[0]["arguments"],
                "result": results_list[0]["result"]
            }

        # Otherwise, Gemini returned a conversational response
        return {
            "action": "chat",
            "message": response.text or "Command received."
        }

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Gemini processing failure: {error}")
        db_log_activity("gemini_command_error", {"command": command}, str(error), "error")
        raise HTTPException(
            status_code=502,
            detail=f"Gemini processing error: {type(error).__name__}. Check API key and quota."
        )


# ==============================
# ACTIVITY LOGS ROUTE
# ==============================

@app.get("/api/activity")
def get_activity(limit: int = 50):
    return db_get_activity_logs(limit=limit)


# ==============================
# MEETING INTELLIGENCE
# ==============================

@app.post("/api/meetings/summarize")
def summarize_meeting(data: dict):
    transcript = data.get("transcript", "").strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="Transcript text is required.")

    summary = ""
    decisions: List[str] = []
    action_items: List[Dict[str, Any]] = []

    if gemini_client:
        try:
            prompt = f"""
Analyze the following meeting transcript.
Provide a concise summary, key decisions made, and concrete actionable tasks.

Respond ONLY with valid JSON matching this schema:
{{
    "summary": "High-level summary of the meeting",
    "decisions": ["Decision 1", "Decision 2"],
    "action_items": [
        {{"title": "Action item title", "description": "Specific action details", "assignee": "Name or unassigned"}}
    ]
}}

Meeting Transcript:
{transcript}
"""
            response = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2
                )
            )
            parsed = json.loads(response.text)
            summary = parsed.get("summary", "")
            decisions = parsed.get("decisions", [])
            action_items = parsed.get("action_items", [])
        except Exception as e:
            logger.warning(f"Gemini transcript parsing failed ({e}); falling back to heuristic extraction.")

    # Fallback heuristic parser if Gemini is unavailable or failed
    if not summary:
        sentences = [s.strip() for s in transcript.replace("\n", ". ").split(".") if len(s.strip()) > 3]
        decisions = [s for s in sentences if any(w in s.lower() for w in ["decid", "agree", "approved", "will use", "adopted", "settled"])]
        action_candidates = [s for s in sentences if any(w in s.lower() for w in ["todo", "will", "send", "prepare", "follow up", "create", "implement", "deploy"])]

        summary = f"Meeting discussion covering {len(sentences)} key points. Extracted {len(decisions)} decisions and {len(action_candidates)} action items."
        action_items = [
            {"title": act, "description": f"Extracted from transcript: {act}", "assignee": "Team"}
            for act in action_candidates
        ]

    # Save to SQLite
    meeting = db_save_meeting(transcript, summary, decisions, action_items)
    db_log_activity("meeting_summarize", {"transcript_length": len(transcript)}, {"meeting_id": meeting["id"], "action_items_count": len(action_items)}, "success")
    return meeting


@app.get("/api/meetings/latest")
def get_latest_meeting():
    meeting = db_get_latest_meeting()
    if not meeting:
        return {"message": "No meeting transcripts recorded yet."}
    return meeting


@app.post("/api/meetings/action-to-task")
async def convert_action_to_task(data: dict):
    if not mcp_client:
        raise HTTPException(status_code=503, detail="MCP server is not connected.")
    title = data.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Action item title is required.")
    description = data.get("description", "Converted from meeting action item.").strip()

    result = await mcp_client.call_tool("create_task", {"title": title, "description": description})
    task = extract_result(result)
    db_log_activity("convert_action_to_task", {"title": title}, task, "success")
    return {
        "status": "success",
        "message": f"Action item '{title}' converted into MCP task.",
        "task": task
    }


# ==============================
# HUMAN APPROVAL WORKFLOW
# ==============================

@app.get("/api/approvals")
def list_approvals(status: Optional[str] = None):
    return db_list_approvals(status_filter=status)


@app.post("/api/approvals")
def create_approval(data: dict):
    operation = data.get("operation", "sensitive_operation").strip()
    details = data.get("details", {})
    appr = db_create_approval(operation, details)
    db_log_activity("create_approval", {"operation": operation, "details": details}, appr, "pending")
    return appr


@app.post("/api/approvals/{approval_id}/approve")
async def approve_operation(approval_id: str):
    res = db_resolve_approval(approval_id, "approved")
    if not res:
        raise HTTPException(status_code=404, detail="Approval request not found.")
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])

    # If this was a deferred sensitive operation, execute it now!
    op = res["operation"]
    details = res["details"]
    execution_result = None

    if op == "delete_task" and mcp_client:
        tid = details.get("task_id")
        if tid:
            mcp_res = await mcp_client.call_tool("delete_task", {"task_id": tid, "approval_id": approval_id})
            execution_result = extract_result(mcp_res)

    db_log_activity("approve_operation", {"approval_id": approval_id, "operation": op}, execution_result or res, "approved")
    return {
        "status": "approved",
        "approval": res,
        "execution_result": execution_result
    }


@app.post("/api/approvals/{approval_id}/reject")
def reject_operation(approval_id: str):
    res = db_resolve_approval(approval_id, "rejected")
    if not res:
        raise HTTPException(status_code=404, detail="Approval request not found.")
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])

    db_log_activity("reject_operation", {"approval_id": approval_id}, res, "rejected")
    return {
        "status": "rejected",
        "approval": res
    }
