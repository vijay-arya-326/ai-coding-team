# AI Agent Backend

A basic agent built with LangGraph, served over FastAPI with token-level
streaming (SSE). The agent runs on Ollama using `phi3` as the base model.
Conversations are persisted per thread in SQLite via LangGraph's checkpointer,
so the server manages thread state across requests.

## Prerequisites

- [Ollama](https://ollama.com) running locally with `phi3` pulled:
  `ollama pull phi3`
- [uv](https://docs.astral.sh/uv/) (the repo venv is uv-managed)

## Setup

```sh
cd backend
uv sync
```

## Run

```sh
uv run uvicorn app.main:app --reload --port 8000
```

Open the interactive docs at http://127.0.0.1:8000/docs.

## API

### `GET /health`

Returns `{"status": "ok"}`.

### `POST /chat` (Server-Sent Events stream)

Server-Sent Events stream. Conversation state is stored in SQLite
(`backend/db/agent_state.db`) under the given `thread_id`, so a follow-up message
on the same thread automatically resumes that conversation.

Request body:

```json
{
  "message": "What is 2 + 3 * 4?",
  "thread_id": "thread-1"
}
```

`thread_id` is optional; when omitted the server assigns one (returned in the
`start` event) so every conversation is persisted.

Response is an SSE stream of events:

| event       | payload                                        |
| ----------- | ---------------------------------------------- |
| `start`     | `{"thread_id": ...}`                           |
| `token`     | `{"delta": "..."}` (one per model output token)|
| `tool_start`| tool name                                      |
| `tool_end`  | `{"name": ..., "output": ...}`                 |
| `end`       | `{"status": "ok"}`                             |
| `error`     | `{"detail": "..."}`                            |

### Thread management

| method   | endpoint               | description                                       |
| -------- | ---------------------- | ------------------------------------------------- |
| `GET`    | `/threads`             | list threads (id, title, archived flag, message count, timestamps, last message) |
| `GET`    | `/threads/{thread_id}` | full message history for a thread (per-message timestamps) |
| `PATCH`  | `/threads/{thread_id}` | rename (`{"title": ...}`) and/or archive (`{"archived": true\|false}`) a thread |
| `POST`   | `/threads/{thread_id}/stop` | cancel an in-flight chat generation for a thread (`{"status": "stopped"}`/`"idle"`) |
| `DELETE` | `/threads/{thread_id}` | delete a thread and all of its checkpoints        |

### Example

```sh
curl -N -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Explain what an API is in one sentence."}'
```

## Configuration

Environment variables (defaults shown):

| variable           | default              |
| ------------------ | -------------------- |
| `OLLAMA_MODEL`     | `phi3`               |
| `OLLAMA_BASE_URL`  | `http://localhost:11434` |
| `THREADS_DB_PATH`  | `backend/db/agent_state.db` |
| `LOGS_DIR`         | `backend/logs`        |
| `LOG_FILE`         | `<LOGS_DIR>/app.log`   |
| `LOG_LEVEL`        | `INFO`                |
| `FORCE_TOOLS`      | unset                |
| `DISABLE_TOOLS`    | unset                |

## Logging

All application, agent, and uvicorn logs go to a single log file
(`backend/logs/app.log`). The file rotates daily at midnight; old files are
kept for 7 days (`app.log.YYYY-MM-DD`), then deleted (TimedRotatingFileHandler
with `when="midnight"`, `backupCount=7`). Logs also mirror to stderr in
development.

## Tools

The agent ships a `calculator` tool. Tool support is auto-detected from
Ollama's `/api/tags` capabilities; `phi3` only supports `completion`, so the
tool-bind is skipped for it and the agent degrades to chat-only. Models with
the `tools` capability (e.g. `llama3.1:8b`, `qwen3:8b`) enable tool calling
automatically:

```sh
OLLAMA_MODEL=llama3.1:8b uv run uvicorn app.main:app --port 8000
```

For 2026 local reasoning, consider `OLLAMA_MODEL=qwen3:8b` too.

## Layout

```
backend/
  app/
    agent.py    # LangGraph graph, tool, Ollama wiring, SQLite checkpointer
    logging.py  # daily-rotating log file setup (7-day retention)
    main.py     # FastAPI app + SSE streaming + thread management endpoints
  pyproject.toml
```