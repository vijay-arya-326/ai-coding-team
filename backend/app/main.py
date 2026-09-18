"""FastAPI app exposing the LangGraph agent with token-level SSE streaming.

Conversation state is persisted per thread in SQLite (see app/agent.py), so a
client only sends a new message plus an optional thread_id to continue a thread.
"""

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from typing import Any
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
    close_checkpointer,
    delete_thread,
    ensure_thread_meta,
    get_graph,
    get_thread,
    list_threads,
    record_message,
    record_runs,
    resolve_approval,
    runs_summary,
    thread_runs,
    update_thread_meta,
    _now,
)
from app.logging import init_logging

logger = init_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up")
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


_active_runs: dict[str, asyncio.Event] = {}


def _stop_event(thread_id: str) -> asyncio.Event:
    return _active_runs.setdefault(thread_id, asyncio.Event())


async def _event_generator(req: ChatRequest, config: RunnableConfig, stop_event: asyncio.Event):
    thread_id = config["configurable"]["thread_id"]
    started = time.time()
    tokens = 0
    assistant_parts: list[str] = []
    stopped = False
    logger.info("chat start thread=%s message=%r", thread_id, req.message[:200])
    try:
        await ensure_thread_meta(thread_id, req.message)
        await record_message(thread_id, "user", req.message, _now())
        stream_started_at = _now()
        yield {"event": "start", "data": json.dumps({"thread_id": thread_id})}

        graph = await get_graph()
        runs: list[dict] = []
        current_run: dict | None = None

        def attach_tool_start(name: str | None, args: Any) -> None:
            target = current_run if current_run is not None else (runs[-1] if runs else None)
            if target is None:
                return
            tools = target.setdefault("tools", [])
            if tools and tools[-1].get("output") is None:
                return
            tools.append({
                "name": name,
                "input": json.dumps(args, default=str)[:1000] if args is not None else None,
                "output": None,
            })

        def attach_tool_end(output: Any) -> None:
            scope = current_run if current_run is not None else (runs[-1] if runs else None)
            if scope is None:
                return
            for t in reversed(scope.get("tools", [])):
                if t.get("output") is None:
                    t["output"] = str(output)[:1000]
                    return

        def round_input_preview() -> str:
            if not runs:
                return req.message[:50000]
            parts = []
            for t in runs[-1].get("tools", []):
                parts.append(f"{t['name']}: in={t['input']} out={t['output']}")
            return ("[tool results] " + " | ".join(parts))[:50000]

        async for event in graph.astream_events(
            {"messages": [HumanMessage(content=req.message)]},
            config=config,
            version="v2",
        ):
            if stop_event.is_set():
                stopped = True
                logger.info("chat stop requested thread=%s", thread_id)
                break
            kind = event["event"]
            data = event.get("data", {}) or {}
            if kind == "on_chat_model_start":
                if current_run is not None:
                    current_run["ended_at"] = _now()
                    runs.append(current_run)
                current_run = {
                    "started_at": _now(),
                    "ended_at": None,
                    "input_preview": round_input_preview(),
                    "output_preview": "",
                    "input_tokens": None,
                    "output_tokens": None,
                    "total_tokens": None,
                    "tools": [],
                }
            elif kind == "on_chat_model_stream":
                chunk = data.get("chunk")
                text = chunk.content if chunk else ""
                if text:
                    tokens += 1
                    assistant_parts.append(text)
                    if current_run is not None:
                        current_run["output_preview"] += text
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
                usage = usage or {}
                if current_run is not None:
                    current_run["input_tokens"] = (
                        usage.get("input_tokens") or usage.get("prompt_tokens")
                    )
                    current_run["output_tokens"] = (
                        usage.get("output_tokens") or usage.get("completion_tokens")
                    )
                    if current_run["input_tokens"] is not None and current_run["output_tokens"] is not None:
                        current_run["total_tokens"] = (
                            usage.get("total_tokens")
                            or current_run["input_tokens"] + current_run["output_tokens"]
                        )
                    else:
                        current_run["total_tokens"] = usage.get("total_tokens")
                    current_run["ended_at"] = _now()
                    runs.append(current_run)
                    current_run = None
            elif kind == "on_tool_start":
                attach_tool_start(
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
                attach_tool_end(output)
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

        if current_run is not None:
            current_run["ended_at"] = _now()
            runs.append(current_run)

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
            await record_runs(thread_id, runs)
        except Exception:
            logger.exception("record_runs failed thread=%s runs=%d", thread_id, len(runs))

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
        _active_runs.pop(thread_id, None)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
async def chat(req: ChatRequest) -> EventSourceResponse:
    thread_id = req.thread_id or f"thread_{uuid4().hex}"
    config = RunnableConfig(
        recursion_limit=25,
        configurable={"thread_id": thread_id},
    )
    stop_event = _stop_event(thread_id)
    return EventSourceResponse(
        _event_generator(req, config, stop_event),
        headers={"Cache-Control": "no-cache"},
    )


@app.post("/threads/{thread_id}/stop")
async def thread_stop(thread_id: str) -> dict[str, str]:
    if thread_id not in _active_runs:
        logger.info("chat stop idle thread=%s", thread_id)
        return {"status": "idle"}
    _active_runs[thread_id].set()
    logger.info("chat stop requested thread=%s", thread_id)
    return {"status": "stopped"}


@app.post("/approvals/{approval_id}")
async def approval_decision(approval_id: str, req: ApprovalRequest) -> dict:
    result = await asyncio.to_thread(resolve_approval, approval_id, req.approved, req.allow)
    logger.info("approval %s approved=%s -> %s", approval_id, req.approved, result["status"])
    return result


@app.get("/threads")
async def threads() -> list[dict]:
    result = await list_threads()
    logger.info("threads listed count=%d", len(result))
    return result


@app.get("/runs")
async def runs_list() -> list[dict]:
    result = await runs_summary()
    logger.info("runs summary count=%d", len(result))
    return result


@app.get("/runs/{thread_id}")
async def runs_detail(thread_id: str) -> dict:
    result = await thread_runs(thread_id)
    if result is None:
        logger.info("runs not found id=%s", thread_id)
        raise HTTPException(status_code=404, detail="No runs for thread")
    logger.info("runs fetched id=%s runs=%d", thread_id, result["run_count"])
    return result


@app.get("/threads/{thread_id}")
async def thread_detail(thread_id: str) -> dict:
    thread = await get_thread(thread_id)
    if thread is None:
        logger.info("thread not found id=%s", thread_id)
        raise HTTPException(status_code=404, detail="Thread not found")
    logger.info("thread fetched id=%s messages=%d", thread_id, len(thread["messages"]))
    return thread


@app.delete("/threads/{thread_id}")
async def thread_delete(thread_id: str) -> dict[str, str]:
    before = await get_thread(thread_id)
    if before is None:
        logger.info("thread delete miss id=%s", thread_id)
        raise HTTPException(status_code=404, detail="Thread not found")
    await delete_thread(thread_id)
    logger.info("thread deleted id=%s", thread_id)
    return {"status": "deleted"}


@app.patch("/threads/{thread_id}")
async def thread_update(thread_id: str, update: ThreadUpdateRequest) -> dict:
    before = await get_thread(thread_id)
    if before is None:
        logger.info("thread update miss id=%s", thread_id)
        raise HTTPException(status_code=404, detail="Thread not found")
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)