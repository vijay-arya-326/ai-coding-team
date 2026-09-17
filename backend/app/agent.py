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
    if hasattr(_meta_conn, "_conn"):
        await _meta_conn._conn.close()
        del _meta_conn._conn


async def get_graph():
    """Return a cached compiled graph sharing the SQLite checkpointer."""
    if not hasattr(get_graph, "_graph"):
        checkpointer = await get_checkpointer()
        get_graph._graph = _build_graph(checkpointer)
    return get_graph._graph


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _meta_conn() -> aiosqlite.Connection:
    """Return a long-lived connection to the app's thread metadata tables."""
    if not hasattr(_meta_conn, "_conn"):
        os.makedirs(os.path.dirname(THREADS_DB_PATH), exist_ok=True)
        conn = await aiosqlite.connect(THREADS_DB_PATH)
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS thread_meta ("
            " thread_id TEXT PRIMARY KEY,"
            " title TEXT,"
            " archived INTEGER NOT NULL DEFAULT 0,"
            " created_at TEXT NOT NULL,"
            " updated_at TEXT NOT NULL)"
        )
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS thread_messages ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " thread_id TEXT NOT NULL,"
            " role TEXT NOT NULL,"
            " content TEXT NOT NULL,"
            " created_at TEXT NOT NULL)"
        )
        await conn.commit()
        logger.info("Thread metadata tables ready at %s", THREADS_DB_PATH)
        _meta_conn._conn = conn
    return _meta_conn._conn


async def ensure_thread_meta(thread_id: str, first_user_text: str | None) -> None:
    """Create a metadata row when a thread first appears; title defaults to first message."""
    conn = await _meta_conn()
    now = _now()
    title = first_user_text.strip()[:80] if first_user_text and first_user_text.strip() else None
    await conn.execute(
        "INSERT OR IGNORE INTO thread_meta"
        " (thread_id, title, archived, created_at, updated_at) VALUES (?, ?, 0, ?, ?)",
        (thread_id, title, now, now),
    )
    await conn.commit()


async def record_message(thread_id: str, role: str, content: str, created_at: str) -> None:
    """Persist one user/assistant message with its timestamp for display."""
    if not content:
        return
    conn = await _meta_conn()
    await conn.execute(
        "INSERT INTO thread_messages (thread_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (thread_id, role, content, created_at),
    )
    await conn.commit()


async def _load_thread_meta(thread_id: str) -> tuple[str | None, bool]:
    conn = await _meta_conn()
    cur = await conn.execute(
        "SELECT title, archived FROM thread_meta WHERE thread_id = ?", (thread_id,)
    )
    row = await cur.fetchone()
    if row is None:
        return None, False
    return row[0], bool(row[1])


async def update_thread_meta(
    thread_id: str,
    title: str | None = None,
    archived: bool | None = None,
) -> dict[str, Any] | None:
    """Rename and/or (un)archive a thread; returns the new metadata state."""
    conn = await _meta_conn()
    now = _now()
    await conn.execute(
        "INSERT OR IGNORE INTO thread_meta"
        " (thread_id, title, archived, created_at, updated_at) VALUES (?, NULL, 0, ?, ?)",
        (thread_id, now, now),
    )
    if title is not None:
        title = title.strip() or None
        await conn.execute(
            "UPDATE thread_meta SET title = ?, updated_at = ? WHERE thread_id = ?",
            (title, now, thread_id),
        )
    if archived is not None:
        await conn.execute(
            "UPDATE thread_meta SET archived = ?, updated_at = ? WHERE thread_id = ?",
            (int(archived), now, thread_id),
        )
    await conn.commit()
    title, archived = await _load_thread_meta(thread_id)
    return {"thread_id": thread_id, "title": title, "archived": archived}


async def _stored_messages(thread_id: str) -> list[dict[str, Any]] | None:
    conn = await _meta_conn()
    cur = await conn.execute(
        "SELECT role, content, created_at FROM thread_messages"
        " WHERE thread_id = ? ORDER BY id",
        (thread_id,),
    )
    rows = await cur.fetchall()
    if not rows:
        return None
    return [
        {"role": role, "content": content, "created_at": created_at}
        for role, content, created_at in rows
    ]


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
    """List threads, newest first, with title, archived flag, and last-message preview."""
    saver = await get_checkpointer()
    threads: dict[str, dict[str, Any]] = {}
    async for tup in saver.alist(None, limit=limit):
        thread_id = (tup.config or {}).get("configurable", {}).get("thread_id")
        if not thread_id or thread_id in threads:
            continue
        messages = (tup.checkpoint or {}).get("channel_values", {}).get("messages", [])
        messages = [m for m in messages if isinstance(m, BaseMessage)]
        first_user = next((m for m in messages if isinstance(m, HumanMessage)), None)
        title, archived = await _load_thread_meta(thread_id)
        threads[thread_id] = {
            "thread_id": thread_id,
            "title": title,
            "archived": archived,
            "message_count": len(messages),
            "created_at": await _thread_created_at(saver, thread_id),
            "updated_at": _checkpoint_ts(
                (tup.config or {}).get("configurable", {}).get("checkpoint_id")
            ),
            "last_message": _message_to_dict(messages[-1]) if messages else None,
            "first_user_message": (
                str(first_user.content)[:80] if first_user and first_user.content else None
            ),
        }
    return list(threads.values())


async def get_thread(thread_id: str) -> dict[str, Any] | None:
    """Return one thread's message history (with timestamps), or None if missing."""
    saver = await get_checkpointer()
    tup = await saver.aget_tuple(
        {"configurable": {"thread_id": thread_id}}
    )
    if tup is None:
        return None
    title, archived = await _load_thread_meta(thread_id)
    messages = await _stored_messages(thread_id)
    if messages is None:
        raw = (tup.checkpoint or {}).get("channel_values", {}).get("messages", [])
        messages = [
            {**_message_to_dict(m), "created_at": None}
            for m in raw
            if isinstance(m, BaseMessage)
        ]
    return {
        "thread_id": thread_id,
        "title": title,
        "archived": archived,
        "created_at": await _thread_created_at(saver, thread_id),
        "updated_at": _checkpoint_ts(
            (tup.config or {}).get("configurable", {}).get("checkpoint_id")
        ),
        "messages": messages,
    }


async def delete_thread(thread_id: str) -> None:
    saver = await get_checkpointer()
    await saver.adelete_thread(thread_id)