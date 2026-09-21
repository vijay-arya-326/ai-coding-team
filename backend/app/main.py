"""FastAPI app exposing the LangGraph agent with token-level SSE streaming.

Conversation state is persisted per thread in SQLite (see app/agent.py), so a
client only sends a new message plus an optional thread_id to continue a thread.
"""

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]

from app.agent import (
    PENDING_APPROVALS,
    APP_VERSION,
    DEFAULT_WORKSPACE_ID,
    GENERATION_IDLE_TIMEOUT,
    OLLAMA_MODEL,
    activate_workspace,
    close_checkpointer,
    create_workspace,
    delete_thread,
    delete_workspace,
    ensure_thread_meta,
    get_current,
    get_graph,
    get_thread,
    get_workspace,
    init_current,
    list_threads,
    list_workspaces,
    record_message,
    record_runs,
    resolve_approval,
    runs_summary,
    set_current,
    thread_exists,
    thread_runs,
    thread_workspace_id,
    update_thread_meta,
    update_workspace,
    _now,
)
from app.logging import init_logging
from app.runtracker import RunRegistry, RunTracker

logger = init_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up")
    await init_current()
    yield
    logger.info("Shutting down")
    await close_checkpointer()


app = FastAPI(title="AI Agent Backend", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "Authorization"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None


class ThreadUpdateRequest(BaseModel):
    title: str | None = None
    archived: bool | None = None


class ApprovalRequest(BaseModel):
    approved: bool
    allow: str | None = None


class WorkspaceCreateRequest(BaseModel):
    name: str
    root_path: str


class WorkspaceMkdirRequest(BaseModel):
    parent: str
    name: str


class WorkspaceUpdateRequest(BaseModel):
    name: str | None = None
    config: dict | None = None


_WINDOWS_DRIVES = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


_runs = RunRegistry()


async def _require_thread(thread_id: str) -> dict:
    """Return thread metadata scoped to the active workspace or raise a 404.

    Threads are private to their workspace, so a thread of another workspace is
    reported as not found.
    """
    thread = await get_thread(thread_id, workspace_id=get_current().id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


async def _resolve_thread_workspace(thread_id: str) -> str:
    """Activate the workspace a thread belongs to, else keep the current one."""
    ws_id = await thread_workspace_id(thread_id)
    if ws_id:
        ws = await get_workspace(ws_id)
        if ws is not None:
            set_current(ws)
            return ws.id
    return get_current().id


async def _event_generator(req: ChatRequest, config: RunnableConfig, stop_event: asyncio.Event):
    thread_id = config["configurable"]["thread_id"]
    started = time.time()
    tokens = 0
    assistant_parts: list[str] = []
    stopped = False
    logger.info("chat start thread=%s message=%r", thread_id, req.message[:200])
    try:
        ws_id = await _resolve_thread_workspace(thread_id)
        await ensure_thread_meta(thread_id, req.message, ws_id)
        await record_message(thread_id, "user", req.message, _now())
        stream_started_at = _now()
        yield {"event": "start", "data": json.dumps({"thread_id": thread_id})}

        graph = await get_graph()
        tracker = RunTracker(req.message)

        stream = graph.astream_events(
            {"messages": [HumanMessage(content=req.message)]},
            config=config,
            version="v2",
        )
        while True:
                try:
                    event = await asyncio.wait_for(
                        stream.__anext__(), timeout=GENERATION_IDLE_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    await asyncio.wait_for(stream.aclose(), timeout=5)
                    raise TimeoutError(
                        f"model produced no output for {GENERATION_IDLE_TIMEOUT}s; aborting"
                    )
                except StopAsyncIteration:
                    break
                if stop_event.is_set():
                    stopped = True
                    logger.info("chat stop requested thread=%s", thread_id)
                    break
                kind = event["event"]
                data = event.get("data", {}) or {}
                if kind == "on_chat_model_start":
                    tracker.start_run()
                elif kind == "on_chat_model_stream":
                    chunk = data.get("chunk")
                    text = chunk.content if chunk else ""
                    if text:
                        tokens += 1
                        assistant_parts.append(text)
                        tracker.token(text)
                        yield {
                            "event": "token",
                            "data": json.dumps({"delta": text}),
                        }
                elif kind == "on_chat_model_end":
                    usage = None
                    out = data.get("output")
                    if isinstance(out, list):
                        out = out[-1] if out else None
                    if out is not None:
                        usage = getattr(out, "usage_metadata", None)
                        if usage is None:
                            usage = (getattr(out, "response_metadata", None) or {}).get("usage")
                    tracker.finish_run(usage or {})
                elif kind == "on_tool_start":
                    tracker.attach_tool_start(
                        data.get("name") or event.get("name"),
                        data.get("input"),
                    )
                    yield {
                        "event": "tool_start",
                        "data": json.dumps(event["name"]),
                    }
                elif kind == "on_tool_end":
                    output = data.get("output")
                    if hasattr(output, "content"):
                        output = getattr(output, "content")
                    tracker.attach_tool_end(output)
                    yield {
                        "event": "tool_end",
                        "data": json.dumps({
                            "name": event["name"],
                            "output": str(output),
                        }),
                    }
                    out_text = str(output)
                    if out_text.startswith("ACTION_REQUIRES_APPROVAL:"):
                        approval_id = out_text.split(":", 1)[1].strip()
                        entry = PENDING_APPROVALS.get(approval_id)
                        if entry:
                            yield {
                                "event": "approval",
                                "data": json.dumps({
                                    "approval_id": approval_id,
                                    "kind": entry["kind"],
                                    "description": entry["description"],
                                    "command": entry["params"].get("command"),
                                    "path": entry["params"].get("path"),
                                }),
                            }

        tracker.close()

        if assistant_parts:
            await record_message(
                thread_id,
                "assistant",
                "".join(assistant_parts),
                _now(),
                stream_started_at=stream_started_at,
                stream_elapsed_ms=max(0, round((time.time() - started) * 1000)),
            )
        try:
            await record_runs(thread_id, tracker.runs, workspace_id=ws_id)
        except Exception:
            logger.exception("record_runs failed thread=%s runs=%d", thread_id, len(tracker.runs))

        if stopped:
            logger.info(
                "chat stopped thread=%s tokens=%d elapsed=%.2fs",
                thread_id,
                tokens,
                time.time() - started,
            )
        else:
            logger.info(
                "chat end thread=%s tokens=%d elapsed=%.2fs",
                thread_id,
                tokens,
                time.time() - started,
            )
            yield {"event": "end", "data": json.dumps({"status": "ok"})}
    except Exception as exc:
        logger.exception("chat error thread=%s", thread_id)
        yield {"event": "error", "data": json.dumps({"detail": str(exc)})}
    finally:
        _runs.clear(thread_id)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": "AI Agent Backend", "version": APP_VERSION, "model": OLLAMA_MODEL}


@app.post("/chat")
async def chat(req: ChatRequest) -> EventSourceResponse:
    thread_id = req.thread_id or f"thread_{uuid4().hex}"
    if req.thread_id is not None:
        owned = await thread_workspace_id(thread_id)
        if owned is None and await thread_exists(thread_id):
            owned = DEFAULT_WORKSPACE_ID
        if owned is not None and owned != get_current().id:
            raise HTTPException(
                status_code=403, detail="Thread belongs to another workspace"
            )
    config = RunnableConfig(
        recursion_limit=25,
        configurable={"thread_id": thread_id},
    )
    stop_event = _runs.stop_event(thread_id)
    return EventSourceResponse(
        _event_generator(req, config, stop_event),
        headers={"Cache-Control": "no-cache"},
    )


@app.post("/threads/{thread_id}/stop")
async def thread_stop(thread_id: str) -> dict[str, str]:
    if not _runs.is_active(thread_id):
        logger.info("chat stop idle thread=%s", thread_id)
        return {"status": "idle"}
    _runs.request_stop(thread_id)
    logger.info("chat stop requested thread=%s", thread_id)
    return {"status": "stopped"}


@app.post("/approvals/{approval_id}")
async def approval_decision(approval_id: str, req: ApprovalRequest) -> dict:
    result = await asyncio.to_thread(resolve_approval, approval_id, req.approved, req.allow)
    logger.info("approval %s approved=%s -> %s", approval_id, req.approved, result["status"])
    return result


@app.get("/threads")
async def threads() -> list[dict]:
    result = await list_threads(workspace_id=get_current().id)
    logger.info("threads listed count=%d ws=%s", len(result), get_current().id)
    return result


@app.get("/runs")
async def runs_list() -> list[dict]:
    result = await runs_summary(workspace_id=get_current().id)
    logger.info("runs summary count=%d ws=%s", len(result), get_current().id)
    return result


@app.get("/runs/{thread_id}")
async def runs_detail(thread_id: str) -> dict:
    result = await thread_runs(thread_id, workspace_id=get_current().id)
    if result is None:
        logger.info("runs not found id=%s", thread_id)
        raise HTTPException(status_code=404, detail="No runs for thread")
    logger.info("runs fetched id=%s runs=%d", thread_id, result["run_count"])
    return result


@app.get("/threads/{thread_id}")
async def thread_detail(thread_id: str) -> dict:
    thread = await _require_thread(thread_id)
    logger.info("thread fetched id=%s messages=%d", thread_id, len(thread["messages"]))
    return thread


@app.delete("/threads/{thread_id}")
async def thread_delete(thread_id: str) -> dict[str, str]:
    await _require_thread(thread_id)
    await delete_thread(thread_id)
    logger.info("thread deleted id=%s", thread_id)
    return {"status": "deleted"}


@app.patch("/threads/{thread_id}")
async def thread_update(thread_id: str, update: ThreadUpdateRequest) -> dict:
    await _require_thread(thread_id)
    result = await update_thread_meta(
        thread_id,
        title=update.title,
        archived=update.archived,
    )
    logger.info(
        "thread updated id=%s title=%r archived=%s",
        thread_id,
        result.get("title"),
        result.get("archived"),
    )
    return result if result is not None else {"thread_id": thread_id}


@app.get("/workspaces/browse")
async def workspace_browse(path: str | None = None):
    """List subdirectories of `path` for the folder picker.

    An empty/missing path returns the user's home directory as the starting
    point; the sentinel path "<drives>" lists the mounted drives (Windows).
    Only directories are returned; each entry carries its absolute path.
    """
    from pathlib import Path

    raw = (path or "").strip().strip('"')
    if raw == "<drives>":
        drives = [
            {"name": f"{d}:", "path": f"{d}:\\"}
            for d in _WINDOWS_DRIVES
            if os.path.isdir(f"{d}:\\")
        ]
        return {"path": "<drives>", "name": "This PC", "parent": None, "entries": drives}
    if not raw:
        raw = os.path.expanduser("~")
    else:
        raw = os.path.expanduser(raw)
    p = Path(raw)
    if not p.is_dir():
        raise HTTPException(status_code=400, detail="Not a directory")
    try:
        children = sorted(
            p.iterdir(),
            key=lambda c: (not c.is_dir(), str(c).lower()),
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="Access denied")
    entries = [
        {"name": c.name, "path": str(c)}
        for c in children
        if c.is_dir()
    ]
    if p.parent == p:
        entries = [{"name": "This PC", "path": "<drives>"}, *entries]
    parent = str(p.parent) if p.parent != p else None
    return {
        "path": str(p),
        "name": p.name if p.name else str(p),
        "parent": parent,
        "entries": entries,
    }


@app.post("/workspaces/mkdir")
async def workspace_mkdir(req: WorkspaceMkdirRequest) -> dict:
    """Create a subdirectory under `parent` for the folder picker."""
    from pathlib import Path

    parent = Path(req.parent)
    if not parent.is_dir():
        raise HTTPException(status_code=400, detail="Parent is not a directory")
    name = (req.name or "").strip().strip('"')
    if not name or any(ch in name for ch in '<>:"|?*'):
        raise HTTPException(status_code=400, detail="Invalid folder name")
    target = parent / name
    if target.exists():
        raise HTTPException(status_code=409, detail="Folder already exists")
    try:
        target.mkdir()
    except OSError as exc:
        logger.info("mkdir failed parent=%s name=%s: %s", req.parent, req.name, exc)
        raise HTTPException(status_code=403, detail="Could not create folder")
    return {"name": name, "path": str(target)}


@app.get("/workspaces")
async def workspaces_list() -> list[dict]:
    active_id = get_current().id
    result = [
        {
            "id": ws.id,
            "name": ws.name,
            "root_path": ws.root_path,
            "is_default": ws.is_default,
            "config": ws.config,
            "created_at": ws.created_at,
            "updated_at": ws.updated_at,
            "active": ws.id == active_id,
        }
        for ws in await list_workspaces()
    ]
    logger.info("workspaces listed count=%d", len(result))
    return result


@app.post("/workspaces")
async def workspaces_create(req: WorkspaceCreateRequest) -> dict:
    try:
        ws = await create_workspace(req.name, req.root_path)
    except ValueError as exc:
        logger.info("workspace create rejected: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))
    logger.info("workspace created id=%s root=%s", ws.id, ws.root_path)
    return {
        "id": ws.id,
        "name": ws.name,
        "root_path": ws.root_path,
        "is_default": ws.is_default,
    }


@app.get("/workspaces/{ws_id}")
async def workspace_detail(ws_id: str) -> dict:
    ws = await get_workspace(ws_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return {
        "id": ws.id,
        "name": ws.name,
        "root_path": ws.root_path,
        "is_default": ws.is_default,
        "config": ws.config,
        "created_at": ws.created_at,
        "updated_at": ws.updated_at,
    }


@app.patch("/workspaces/{ws_id}")
async def workspace_update(ws_id: str, update: WorkspaceUpdateRequest) -> dict:
    ws = await update_workspace(ws_id, name=update.name, config=update.config)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    logger.info("workspace updated id=%s", ws_id)
    return {
        "id": ws.id,
        "name": ws.name,
        "root_path": ws.root_path,
        "is_default": ws.is_default,
        "config": ws.config,
        "created_at": ws.created_at,
        "updated_at": ws.updated_at,
    }


@app.delete("/workspaces/{ws_id}")
async def workspace_delete(ws_id: str) -> dict[str, str]:
    if not await delete_workspace(ws_id):
        raise HTTPException(status_code=404, detail="Workspace not found or is the default")
    return {"status": "deleted"}


@app.post("/workspaces/{ws_id}/activate")
async def workspace_activate(ws_id: str) -> dict:
    try:
        ws = await activate_workspace(ws_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {
        "id": ws.id,
        "name": ws.name,
        "root_path": ws.root_path,
        "is_default": ws.is_default,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)