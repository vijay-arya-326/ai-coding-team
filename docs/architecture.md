# Architecture & Phase Reference

Living reference for the local multimodal AI coding agent. Update this file at
every phase boundary. Source roadmap: `docs/plan.md`. Task checklist:
`docs/todo_list.md`.

## Repository layout

- `backend/app/` — FastAPI + LangGraph backend (authoritative implementation)
  - `main.py` — FastAPI app, routes, SSE streaming loop (`/chat`, `/threads/...`)
  - `model.py` — LLM factory + agent graph assembly
  - `graph_state.py` — typed `AgentState`, `ExecutionPlan`, intents, routing
  - `config.py` — all env-overridable constants
  - `tools.py` — agent tools (filesystem, shell, calculator) + approvals
  - `persistence.py`, `db/` — SQLite threads/runs + LangGraph checkpointer
  - `workspace.py` — workspaces, active workspace, guidelines
  - `runtracker.py` — per-thread stop signals + run capture
  - `agent.py` — public facade re-exporting the above
- `backend/tests/` — pytest suite (`uv run pytest`)
- `frontend/src/` — React 19 + Vite + Tailwind chat UI
- `docs/` — `plan.md` (roadmap), `todo_list.md` (checklist), this file

## Runtime stack

- Python >= 3.12, managed with `uv` (`backend/pyproject.toml`, `uv.lock`)
- FastAPI + `sse-starlette` for streaming; LangGraph 1.x; `langchain-ollama`
- SQLite for threads/runs and LangGraph checkpoints (`backend/db/agent_state.db`)
- Dev deps: `pytest`, `pytest-asyncio` (group `dev`)

## Models on the target machine

Verified via `GET http://localhost:11434/api/tags`:

| Model | Capabilities |
|-------|--------------|
| `llama3.1:8b` | completion, tools |
| `llama3.2:latest` | completion, tools |
| `mistral:latest` | completion, tools |
| `qwen3:4b` | completion, tools, thinking |
| `qwen2.5-coder:3b` | completion, tools, insert |
| `gemma4:e2b` | completion, vision, audio, tools, thinking |
| `qwen2.5vl:3b` / `qwen2.5vl:7b` | completion, vision |
| `phi3:latest` | completion |

Plan-role mapping: planner = `qwen3:4b`; coder/tester = `qwen2.5-coder:3b`;
vision = `qwen2.5vl:3b`; audio = a separate Whisper runtime (see Phase 6 note —
Ollama has no Whisper model). `PLANNER_MODEL` defaults to `qwen3:4b`.

## Configuration (`backend/app/config.py`)

| Env var | Default | Purpose |
|---------|---------|---------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | `llama3.1:8b` | main chat/agent model |
| `PLANNER_MODEL` | `qwen3:4b` | planner classification model |
| `PLANNER_TIMEOUT` | `30` | seconds before planner fallback |
| `RECURSION_LIMIT` | `25` | graph recursion cap |
| `GENERATION_IDLE_TIMEOUT` | `120` | idle seconds before a run aborts |
| `SHELL_TIMEOUT` | `90` | shell command timeout |

## Streaming event contract (SSE)

`POST /chat` and `POST /threads/{id}/resume` return `text/event-stream`.
Each event has a `data` payload (JSON unless noted):

| event | payload |
|-------|---------|
| `start` | `{"thread_id": ...}` |
| `token` | `{"delta": "..."}` |
| `plan` | `{"intent": "...", "plan": {...}}` (Phase 1) |
| `tool_start` | `"<tool name>"` (bare JSON string) |
| `tool_end` | `{"name": ..., "output": "..."}` |
| `approval` | `{"approval_id", "kind", "description", "command", "path"}` |
| `end` | `{"status": "ok" \| "awaiting_approval"}` |
| `error` | `{"detail": "..."}` |

Frontend (`frontend/src/api.ts`) hand-parses the body into a typed
`StreamEvent` union; unknown events are ignored, so new events are additive.

---

## Phase 1 — LangGraph Integration (implemented)

### What changed

- **`graph_state.py` (new).** Typed `AgentState` (extends `MessagesState`),
  `ExecutionPlan`/`PlanStep` Pydantic schemas, the 9 intents, `route_intent`,
  and `fallback_plan`.
- **`model.py`.** Graph is now `planner → (route_intent) → responder | agent`.
  Added async `_planner_node` (structured output + timeout + fallback),
  `_responder_node` (tool-free direct answer), and `create_llm(model, bind_tools)`.
- **`main.py`.** Emits a `plan` SSE event on planner completion.
- **`config.py`.** Added `PLANNER_MODEL`, `PLANNER_TIMEOUT`, `PLANNER_PROMPT`.
- **`agent.py`.** Re-exports the new symbols.
- **`pyproject.toml`.** Added `pytest` + `pytest-asyncio`, `[tool.pytest.ini_options]`.

### Graph flow

```
START → planner ──(route_intent)──┬─ QUESTION/EXPLAIN → responder → END
                                   └─ everything else   → agent → (tools_condition)
                                                              ↑          │
                                                              └─ tools ←─┘
```

### State schema (`AgentState`)

`messages` (from `MessagesState`) plus: `detected_intent`, `execution_plan`,
`current_agent`, `agent_status`, `clarification_needed`,
`errors` (`operator.add` reducer), `final_response`.

### Intents

`QUESTION`, `EXPLAIN`, `CODE`, `MODIFY`, `DEBUG`, `GENERATE_TESTS`,
`RUN_TESTS`, `REVIEW`, `MULTI_STEP`. Conversational (`QUESTION`, `EXPLAIN`) go
to the responder; the rest go to the tool-using agent. Later phases replace the
single `agent` node with per-intent coder/tester/reviewer agents.

### Failure handling

The planner call is wrapped in `asyncio.wait_for(..., PLANNER_TIMEOUT)` and a
broad try/except. On timeout, model error, or schema-validation failure it
returns `fallback_plan(reason)` → `MULTI_STEP` → the tool-using agent, and
records the reason in `errors`. The planner never blocks a user reply.

### Tests

`backend/tests/test_graph_state.py` — 29 tests covering state fields, routing
for every intent, plan validation (bad intent, blank step, step cap),
fallback, planner success/error/timeout, and graph compilation.

Run: `cd backend && uv run pytest`

### Verified

- `29 passed`
- Live smoke (real Ollama): "Explain a list comprehension" → `EXPLAIN` →
  responder; "Write a Python function that reverses a string" → `CODE` → agent.
- `plan` event emitted with the detected intent.

### Known limitations / follow-ups

- `plan` event reaches the client but the UI does not render it yet (Phase 7).
- Planner is non-streaming (structured output) — expected; tokens are not
  leaked to the chat because only non-empty `chunk.content` is emitted.
- `clarification_needed` is recorded in state but no clarification round-trip
  is implemented yet.
- Per-intent coder/tester/reviewer agents are Phase 2–4; Phase 1 routes all
  actionable intents to the single existing agent.

### Files touched

`backend/app/graph_state.py` (new), `backend/app/model.py`,
`backend/app/main.py`, `backend/app/config.py`, `backend/app/agent.py`,
`backend/pyproject.toml`, `backend/uv.lock`, `backend/tests/test_graph_state.py` (new).
