"""A basic LangGraph agent backed by Ollama's phi3 model, with SQLite thread persistence."""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import aiosqlite
import httpx
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, MessagesState, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

logger = logging.getLogger("app.agent")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi3")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THREADS_DB_PATH = os.getenv(
    "THREADS_DB_PATH", os.path.join(BASE_DIR, "db", "agent_state.db")
)

SYSTEM_PROMPT = (
    "You are a helpful assistant running on phi3. Be concise and accurate. "
    "Use the tools available to you when they help answer the user's question."
)


@tool
def calculator(expression: str) -> float:
    """Evaluate a simple arithmetic expression such as '2 + 3 * 4'."""
    allowed = set("0123456789+-*/(). ")
    if any(c not in allowed for c in expression):
        raise ValueError("Expression contains unsupported characters.")
    result = eval(expression, {"__builtins__": {}}, {})  # noqa: S307
    return float(result)


TOOLS = [calculator]


def _create_llm() -> ChatOllama:
    llm = ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0.2,
        num_predict=1024,
        num_ctx=4096,
    )
    if _model_supports_tools():
        llm = llm.bind_tools(TOOLS)
        logger.info("Model %s: tool calling enabled", OLLAMA_MODEL)
    else:
        logger.info("Model %s: tool calling not supported, chat-only", OLLAMA_MODEL)
    return llm


def _model_supports_tools() -> bool:
    """Check Ollama's /api/tags for a 'tools' capability on the configured model."""
    if os.getenv("FORCE_TOOLS") == "1":
        return True
    if os.getenv("DISABLE_TOOLS") == "1":
        return False
    try:
        resp = httpx.get(f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=5)
        resp.raise_for_status()
        for model in resp.json().get("models", []):
            name = model.get("name", "")
            # Match "phi3" or "phi3:latest" when configured as "phi3".
            if name == OLLAMA_MODEL or name.startswith(f"{OLLAMA_MODEL}:"):
                return "tools" in model.get("capabilities", [])
    except Exception:
        pass
    # Assume tool support if Ollama cannot be inspected; degrade gracefully on 400.
    return True


def _agent_node(llm: ChatOllama) -> callable:
    def agent(state: MessagesState) -> dict:
        messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
        return {"messages": [llm.invoke(messages)]}

    return agent


def _build_graph(checkpointer: AsyncSqliteSaver):
    llm = _create_llm()

    graph = StateGraph(MessagesState)
    graph.add_node("agent", _agent_node(llm))
    graph.add_node("tools", ToolNode(TOOLS))

    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    graph.add_edge("agent", END)

    return graph.compile(checkpointer=checkpointer)


async def get_checkpointer() -> AsyncSqliteSaver:
    """Return a long-lived AsyncSqliteSaver backed by a persistent SQLite file."""
    if not hasattr(get_checkpointer, "_saver"):
        os.makedirs(os.path.dirname(THREADS_DB_PATH), exist_ok=True)
        conn = await aiosqlite.connect(THREADS_DB_PATH)
        saver = AsyncSqliteSaver(conn)
        await saver.setup()
        logger.info("SQLite checkpointer initialized at %s", THREADS_DB_PATH)
        get_checkpointer._saver = saver
    return get_checkpointer._saver


async def close_checkpointer() -> None:
    """Close the SQLite connection owned by the checkpointer."""
    if hasattr(get_checkpointer, "_saver"):
        await get_checkpointer._saver.conn.close()
        del get_checkpointer._saver


async def get_graph():
    """Return a cached compiled graph sharing the SQLite checkpointer."""
    if not hasattr(get_graph, "_graph"):
        checkpointer = await get_checkpointer()
        get_graph._graph = _build_graph(checkpointer)
    return get_graph._graph


def _role_of(message: BaseMessage) -> str:
    if isinstance(message, HumanMessage):
        return "user"
    if isinstance(message, AIMessage):
        return "assistant"
    if message.type == "tool":
        return "tool"
    return message.type


def _message_to_dict(message: BaseMessage) -> dict[str, Any]:
    return {"role": _role_of(message), "content": message.content}


def _checkpoint_ts(checkpoint_id: str | None) -> str | None:
    """Decode a langgraph time-ordered checkpoint_id (UUIDv6) to UTC ISO time."""
    if not checkpoint_id:
        return None
    try:
        u = uuid.UUID(checkpoint_id)
        time_high = u.int >> 96
        time_mid = (u.int >> 80) & 0xFFFF
        time_low = (u.int >> 68) & 0x0FFF
        ts100 = (time_high << 28) | (time_mid << 12) | time_low
        unix_s = (ts100 - 122192928000000000) / 1e7
        return datetime.fromtimestamp(unix_s, tz=timezone.utc).isoformat()
    except Exception:
        return None


async def _thread_created_at(saver: AsyncSqliteSaver, thread_id: str) -> str | None:
    """Look up the first (oldest) checkpoint_id for a thread from SQLite."""
    cur = await saver.conn.execute(
        "SELECT MIN(checkpoint_id) FROM checkpoints WHERE thread_id = ?",
        (thread_id,),
    )
    row = await cur.fetchone()
    return _checkpoint_ts(row[0] if row else None)


async def list_threads(limit: int = 100) -> list[dict[str, Any]]:
    """List threads, newest first, with a preview of the last message."""
    saver = await get_checkpointer()
    threads: dict[str, dict[str, Any]] = {}
    async for tup in saver.alist(None, limit=limit):
        thread_id = (tup.config or {}).get("configurable", {}).get("thread_id")
        if not thread_id or thread_id in threads:
            continue
        messages = (tup.checkpoint or {}).get("channel_values", {}).get("messages", [])
        messages = [m for m in messages if isinstance(m, BaseMessage)]
        threads[thread_id] = {
            "thread_id": thread_id,
            "message_count": len(messages),
            "created_at": await _thread_created_at(saver, thread_id),
            "updated_at": _checkpoint_ts(
                (tup.config or {}).get("configurable", {}).get("checkpoint_id")
            ),
            "last_message": _message_to_dict(messages[-1]) if messages else None,
        }
    return list(threads.values())


async def get_thread(thread_id: str) -> dict[str, Any] | None:
    """Return one thread's message history, or None if it does not exist."""
    saver = await get_checkpointer()
    tup = await saver.aget_tuple(
        {"configurable": {"thread_id": thread_id}}
    )
    if tup is None:
        return None
    messages = (tup.checkpoint or {}).get("channel_values", {}).get("messages", [])
    return {
        "thread_id": thread_id,
        "created_at": await _thread_created_at(saver, thread_id),
        "updated_at": _checkpoint_ts(
            (tup.config or {}).get("configurable", {}).get("checkpoint_id")
        ),
        "messages": [_message_to_dict(m) for m in messages if isinstance(m, BaseMessage)],
    }


async def delete_thread(thread_id: str) -> None:
    saver = await get_checkpointer()
    await saver.adelete_thread(thread_id)