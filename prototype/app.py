import os
import re
import json

from contextlib import asynccontextmanager
from dotenv import load_dotenv
from google import genai

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import Client


# ==============================
# CONFIGURATION
# ==============================

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

gemini_client = (
    genai.Client(api_key=GEMINI_API_KEY)
    if GEMINI_API_KEY else None
)

mcp_client = None


# ==============================
# MCP RESULT HANDLER
# ==============================

def extract_result(result):

    if result.structured_content is not None:
        return result.structured_content

    if result.data is not None:
        return result.data

    if result.content:
        for item in result.content:

            if hasattr(item, "text"):

                try:
                    return json.loads(item.text)

                except (json.JSONDecodeError, TypeError):
                    return item.text

    return []


# ==============================
# APPLICATION LIFECYCLE
# ==============================

@asynccontextmanager
async def lifespan(app: FastAPI):

    global mcp_client

    async with Client("server.py") as client:

        mcp_client = client

        print("NEXUS MCP Server Connected!")

        if gemini_client:
            print("NEXUS Gemini AI Connected!")
        else:
            print("Gemini API Key Missing!")

        yield

    mcp_client = None


# ==============================
# FASTAPI APPLICATION
# ==============================

app = FastAPI(
    title="NEXUS AI Backend",
    description="MCP Powered Personal Intelligence System",
    version="2.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)


# ==============================
# HOME
# ==============================

@app.get("/")
def home():

    return {
        "message": "NEXUS AI Backend Running",
        "status": "online",
        "gemini": bool(gemini_client)
    }


# ==============================
# LIST TASKS
# ==============================

@app.get("/api/tasks")
async def list_tasks():

    result = await mcp_client.call_tool(
        "list_tasks", {}
    )

    return extract_result(result)


# ==============================
# CREATE TASK
# ==============================

@app.post("/api/tasks")
async def create_task(data: dict):

    result = await mcp_client.call_tool(
        "create_task",
        {
            "title": data.get("title", "New Task"),
            "description": data.get("description", "")
        }
    )

    return extract_result(result)


# ==============================
# COMPLETE TASK
# ==============================

@app.post("/api/complete/{task_id}")
async def complete_task(task_id: str):

    result = await mcp_client.call_tool(
        "complete_task",
        {"task_id": task_id}
    )

    return extract_result(result)


# ==============================
# WORKSPACE STATUS
# ==============================

@app.get("/api/status")
async def get_status():

    result = await mcp_client.call_tool(
        "get_status", {}
    )

    return extract_result(result)


# ==============================
# GEMINI AI COMMAND UNDERSTANDING
# ==============================

async def understand_command(command):

    if not gemini_client:
        raise HTTPException(
            status_code=503,
            detail="Gemini API key is not configured."
        )

    prompt = f"""
You are NEXUS AI, an intelligent productivity assistant.

Understand the user's command and classify it.

Available actions:

1. create_task
2. list_tasks
3. get_status
4. complete_task
5. chat

Return ONLY valid JSON in this format:

{{
    "action": "create_task",
    "title": "task title",
    "description": "task description",
    "reply": "short friendly response"
}}

Rules:

- For task creation, extract the title and description.
- For listing tasks, use list_tasks.
- For progress questions, use get_status.
- For completing tasks, extract the task title.
- For general questions, use chat.
- Never invent task IDs.
- Never return markdown.
- Do not execute tools yourself.

User command: {command}
"""

    try:

        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )

        raw = response.text.strip()

        raw = re.sub(
            r"^```(?:json)?\s*|\s*```$",
            "",
            raw
        )

        return json.loads(raw)

    except Exception as error:

        print("Gemini Error:", error)

        raise HTTPException(
            status_code=502,
            detail="Gemini could not process the command. Please try again."
        )


# ==============================
# NEXUS AI COMMAND ENGINE
# ==============================

@app.post("/api/command")
async def process_command(data: dict):

    command = data.get("command", "").strip()

    if not command:
        return {
            "message": "Please enter a command."
        }

    # Ask Gemini to understand the command

    intent = await understand_command(command)

    action = intent.get("action")

    # ==========================
    # CREATE TASK
    # ==========================

    if action == "create_task":

        title = intent.get("title", "").strip()

        if not title:
            return {
                "message": "Please specify a task title."
            }

        result = await mcp_client.call_tool(
            "create_task",
            {
                "title": title,
                "description": intent.get("description", "")
            }
        )

        return {
            "action": "create_task",
            "message": intent.get(
                "reply",
                "Task created successfully!"
            ),
            "result": extract_result(result)
        }

    # ==========================
    # LIST TASKS
    # ==========================

    elif action == "list_tasks":

        result = await mcp_client.call_tool(
            "list_tasks", {}
        )

        return {
            "action": "list_tasks",
            "message": intent.get(
                "reply",
                "Here are your tasks."
            ),
            "result": extract_result(result)
        }

    # ==========================
    # CHECK STATUS
    # ==========================

    elif action == "get_status":

        result = await mcp_client.call_tool(
            "get_status", {}
        )

        return {
            "action": "get_status",
            "message": intent.get(
                "reply",
                "Here is your workspace status."
            ),
            "result": extract_result(result)
        }

    # ==========================
    # COMPLETE TASK
    # ==========================

    elif action == "complete_task":

        tasks_result = await mcp_client.call_tool(
            "list_tasks", {}
        )

        tasks = extract_result(tasks_result)

        title = intent.get("title", "").strip().lower()

        if not title or not isinstance(tasks, list):
            return {
                "message": "Please specify the full task title."
            }

        matches = [
            task for task in tasks
            if task.get("title", "").lower() == title
        ]

        if len(matches) != 1:

            return {
                "message": "I couldn't identify exactly one task. Please provide its exact title."
            }

        result = await mcp_client.call_tool(
            "complete_task",
            {
                "task_id": matches[0]["id"]
            }
        )

        return {
            "action": "complete_task",
            "message": "Task completed successfully!",
            "result": extract_result(result)
        }

    # ==========================
    # GENERAL AI CHAT
    # ==========================

    elif action == "chat":

        return {
            "action": "chat",
            "message": intent.get(
                "reply",
                "I'm NEXUS AI. How can I help?"
            )
        }

    # ==========================
    # UNKNOWN COMMAND
    # ==========================

    return {
        "message": "I couldn't understand that command. Please try again."
    }