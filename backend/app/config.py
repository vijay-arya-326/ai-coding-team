"""Central configuration and constants for the AI agent backend.

Everything here is overridable via environment variables.
"""

import os

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

THREADS_DB_PATH = os.getenv(
    "THREADS_DB_PATH", os.path.join(BASE_DIR, "db", "agent_state.db")
)

ALLOWED_COMMANDS_FILE = os.getenv(
    "ALLOWED_COMMANDS_FILE", os.path.join(BASE_DIR, "allowed_commands.json")
)

SYSTEM_PROMPT = (
    "You are a helpful assistant running on llama3.1:8b. Be concise and accurate. "
    "Use the tools available to you when they help answer the user's question."
)

# Run capture limits.
PREVIEW_LIMIT = int(os.getenv("PREVIEW_LIMIT", "50000"))
TOOL_TRUNCATION = int(os.getenv("TOOL_TRUNCATION", "1000"))

# Shell execution.
SHELL_TIMEOUT = int(os.getenv("SHELL_TIMEOUT", "90"))

# Graph.
RECURSION_LIMIT = int(os.getenv("RECURSION_LIMIT", "25"))

# Seconds of silence (no streamed event) before a chat run aborts.
GENERATION_IDLE_TIMEOUT = int(os.getenv("GENERATION_IDLE_TIMEOUT", "120"))

# App metadata.
APP_VERSION = os.getenv("APP_VERSION", "0.2.0")
APP_TITLE = os.getenv("APP_TITLE", "AI Agent Backend")