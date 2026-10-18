"""Central configuration and constants for the AI agent backend.

Everything here is overridable via environment variables.
"""

import os

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

# Planner model: classifies intent and produces a structured execution plan.
# Defaults to the dedicated planner (qwen3:4b); override via PLANNER_MODEL.
PLANNER_MODEL = os.getenv("PLANNER_MODEL", "qwen3:4b")

# Seconds before a planner classification call is abandoned and the request
# falls back to the tool-using agent.
PLANNER_TIMEOUT = int(os.getenv("PLANNER_TIMEOUT", "30"))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

THREADS_DB_PATH = os.getenv(
    "THREADS_DB_PATH", os.path.join(BASE_DIR, "db", "agent_state.db")
)

ALLOWED_COMMANDS_FILE = os.getenv(
    "ALLOWED_COMMANDS_FILE", os.path.join(BASE_DIR, "allowed_commands.json")
)

# Workspace configuration: a per-workspace folder holding machine config and
# free-form agent guidelines.
DEFAULT_WORKSPACE_ID = os.getenv("DEFAULT_WORKSPACE_ID", "default")
WORKSPACE_CONFIG_DIR = os.getenv("WORKSPACE_CONFIG_DIR", ".local_agent_workspace")
WORKSPACE_CONFIG_NAME = os.getenv("WORKSPACE_CONFIG_NAME", "config.json")
WORKSPACE_GUIDELINES_NAME = os.getenv("WORKSPACE_GUIDELINES_NAME", "guidelines.md")

SYSTEM_PROMPT = (
    "You are a helpful assistant running on llama3.1:8b. Be concise and accurate. "
    "Use the tools available to you when they help answer the user's question."
)

# Planner instructions: classify the latest request into exactly one intent and
# return a short, validated plan. See app/graph_state.py for the schema.
PLANNER_PROMPT = (
    "You are the planner for a local coding assistant. Read the conversation and "
    "classify the user's latest request into exactly one intent, then return a "
    "short plan (1-5 concrete steps).\n\n"
    "Intents:\n"
    "- QUESTION: a factual or conversational question needing a direct answer.\n"
    "- EXPLAIN: explain existing code, an error, or a concept.\n"
    "- CODE: write new code.\n"
    "- MODIFY: change existing code.\n"
    "- DEBUG: find and fix a bug.\n"
    "- GENERATE_TESTS: write tests.\n"
    "- RUN_TESTS: run existing tests.\n"
    "- REVIEW: review code or a change.\n"
    "- MULTI_STEP: a request that spans several of the above.\n\n"
    "Set needs_clarification only when the request cannot be acted on without "
    "more information, and then ask one focused question."
)

# Run capture limits.
PREVIEW_LIMIT = int(os.getenv("PREVIEW_LIMIT", "50000"))
TOOL_TRUNCATION = int(os.getenv("TOOL_TRUNCATION", "1000"))

# Read/inspect tool limits.
READ_MAX_BYTES = int(os.getenv("READ_MAX_BYTES", "200000"))
READ_MAX_LINES = int(os.getenv("READ_MAX_LINES", "2000"))
LIST_MAX_ENTRIES = int(os.getenv("LIST_MAX_ENTRIES", "500"))
SEARCH_MAX_RESULTS = int(os.getenv("SEARCH_MAX_RESULTS", "200"))
STRUCTURE_MAX_DEPTH = int(os.getenv("STRUCTURE_MAX_DEPTH", "3"))
STRUCTURE_MAX_ENTRIES = int(os.getenv("STRUCTURE_MAX_ENTRIES", "500"))

# Directories skipped by search_code and get_project_structure.
IGNORED_DIRS = {
    d.strip()
    for d in os.getenv(
        "IGNORED_DIRS",
        ".git,node_modules,.venv,venv,__pycache__,dist,build,"
        ".pytest_cache,.mypy_cache,.idea,.next,coverage",
    ).split(",")
    if d.strip()
}

# Shell execution.
SHELL_TIMEOUT = int(os.getenv("SHELL_TIMEOUT", "90"))

# Graph.
RECURSION_LIMIT = int(os.getenv("RECURSION_LIMIT", "25"))

# Seconds of silence (no streamed event) before a chat run aborts.
GENERATION_IDLE_TIMEOUT = int(os.getenv("GENERATION_IDLE_TIMEOUT", "120"))

# App metadata.
APP_VERSION = os.getenv("APP_VERSION", "0.2.0")
APP_TITLE = os.getenv("APP_TITLE", "AI Agent Backend")