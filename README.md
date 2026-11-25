# NEXUS AI — Team 404 ERROR
### MCP-Powered Personal Intelligence & Autonomous Productivity System

An autonomous personal intelligence command center built for **Track 1: Make MCP Matter**. NEXUS AI bridges natural language commands, native Google Gemini function calling, Model Context Protocol (MCP) tool execution, and persistent SQLite storage.

---

## 🌟 Key Architecture & Implemented Features

1. **Native Gemini Function Calling (`google-genai` SDK)**:
   - Exposes registered FastMCP tools directly as Gemini function declarations (`create_task`, `list_tasks`, `complete_task`, `get_status`, `delete_task`).
   - Gemini autonomously selects tools based on user intent and passes verified parameters.
2. **FastMCP Server & Client Architecture**:
   - `prototype/server.py`: FastMCP stdio server exposing task and workspace tools.
   - `prototype/app.py`: FastAPI bridge utilizing FastMCP async stdio client.
3. **SQLite Persistence (`nexus.db`)**:
   - Automatic database provisioning with tables for `tasks`, `activity_logs`, `meetings`, and `approvals`.
   - Records survive server reboots and process termination.
4. **Persistent Activity Logging**:
   - Every MCP tool call, argument set, timestamp, and outcome is logged in SQLite and viewable via `/api/activity`.
5. **Meeting Intelligence & Action Item Conversion**:
   - `/api/meetings/summarize`: Analyzes raw transcripts to extract concise summaries, decisions, and action items.
   - `/api/meetings/action-to-task`: 1-click conversion promoting extracted meeting items into persistent MCP tasks.
6. **Human-in-the-Loop Backend Approval**:
   - Sensitive actions (such as task deletion) generate a cryptographically tagged `pending` approval request.
   - Actions remain blocked until explicitly approved via backend authorization endpoints (`/api/approvals/{id}/approve`).
7. **Clean Web Command Center**:
   - Clean, modern single-page dashboard connected directly to FastAPI and FastMCP endpoints.

---

## 🚀 Running on Windows

### 1. Prerequisites
- Python 3.10+
- Modern Web Browser (Chrome / Edge / Firefox)

### 2. Installation
```powershell
# Navigate into the project directory
cd NEXUS-AI-404-ERROR\prototype

# Create and activate virtual environment (optional but recommended)
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install required dependencies
pip install fastapi uvicorn fastmcp google-genai python-dotenv
```

### 3. Configure Gemini API Key
Create a `.env` file in `prototype\` (or use the provided `.env.example` template):
```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

### 4. Start the Backend Server
You can launch the server from the repository root **or** from the `prototype/` directory:

**From repository root:**
```powershell
python -m uvicorn prototype.app:app --host 127.0.0.1 --port 8000 --reload
```

**From `prototype/` directory:**
```powershell
cd prototype
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

### 5. Launch the Command Center UI
Open `prototype/index.html` in your browser:
```powershell
Start-Process "prototype/index.html"
```
