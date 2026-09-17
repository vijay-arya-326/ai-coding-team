"""FastAPI app exposing the LangGraph agent with token-level SSE streaming.

Conversation state is persisted per thread in SQLite (see app/agent.py), so a
client only sends a new message plus an optional thread_id to continue a thread.
"""

import json
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.agent import (
    close_checkpointer,
    delete_thread,
    get_graph,
    get_thread,
    list_threads,
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
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None


async def _event_generator(req: ChatRequest, config: RunnableConfig):
    thread_id = config["configurable"]["thread_id"]
    started = time.time()
    tokens = 0
    logger.info("chat start thread=%s message=%r", thread_id, req.message[:200])
    try:
        yield {"event": "start", "data": json.dumps({"thread_id": thread_id})}

        graph = await get_graph()
        async for event in graph.astream_events(
            {"messages": [HumanMessage(content=req.message)]},
            config=config,
            version="v2",
        ):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                text = chunk.content if chunk else ""
                if text:
                    tokens += 1
                    yield {
                        "event": "token",
                        "data": json.dumps({"delta": text}),
                    }
            elif kind == "on_tool_start":
                yield {
                    "event": "tool_start",
                    "data": json.dumps(event["name"]),
                }
            elif kind == "on_tool_end":
                output = event["data"]["output"]
                if hasattr(output, "content"):
                    output = getattr(output, "content")
                yield {
                    "event": "tool_end",
                    "data": json.dumps({
                        "name": event["name"],
                        "output": str(output),
                    }),
                }

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
    return EventSourceResponse(
        _event_generator(req, config),
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/threads")
async def threads() -> list[dict]:
    result = await list_threads()
    logger.info("threads listed count=%d", len(result))
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)