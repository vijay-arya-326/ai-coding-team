"""Repository functions for thread metadata, messages, and runs.

Connection lifecycle lives in app/db/connection.py; schema/migrations in
app/db/migrations.py. This module only executes queries against them.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from .config import DEFAULT_WORKSPACE_ID, PREVIEW_LIMIT
from .db import close_checkpointer as _close_db
from .db import meta_conn as _meta_conn
from .db import open_checkpointer as _open_checkpointer

logger = logging.getLogger("app.agent")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def effective_workspace_id(ws_id: str | None) -> str:
    """Untagged/legacy threads belong to the default workspace."""
    return ws_id or DEFAULT_WORKSPACE_ID


# Re-exported for callers that built on the old flat surface.
close_checkpointer = _close_db
meta_conn = _meta_conn
open_checkpointer = _open_checkpointer

__all__ = ["close_checkpointer", "open_checkpointer"]


async def ensure_thread_meta(
    thread_id: str, first_user_text: str | None, workspace_id: str | None = None
) -> None:
    """Create a metadata row when a thread first appears; title defaults to first message."""
    conn = await _meta_conn()
    now = _now()
    title = first_user_text.strip()[:80] if first_user_text and first_user_text.strip() else None
    await conn.execute(
        "INSERT OR IGNORE INTO thread_meta"
        " (thread_id, title, archived, created_at, updated_at, workspace_id)"
        " VALUES (?, ?, 0, ?, ?, ?)",
        (thread_id, title, now, now, workspace_id),
    )
    await conn.commit()


async def thread_workspace_id(thread_id: str) -> str | None:
    """Return the workspace a thread belongs to (None when unknown)."""
    conn = await _meta_conn()
    cur = await conn.execute(
        "SELECT workspace_id FROM thread_meta WHERE thread_id = ?", (thread_id,)
    )
    row = await cur.fetchone()
    return row[0] if row else None


async def thread_exists(thread_id: str) -> bool:
    """True when the thread has any persisted conversation state (checkpoint)."""
    saver = await open_checkpointer()
    cur = await saver.conn.execute(
        "SELECT 1 FROM checkpoints WHERE thread_id = ? LIMIT 1", (thread_id,)
    )
    row = await cur.fetchone()
    return row is not None


async def record_message(
    thread_id: str,
    role: str,
    content: str,
    created_at: str,
    stream_started_at: str | None = None,
    stream_elapsed_ms: int | None = None,
) -> None:
    """Persist one user/assistant message with its timestamp for display.

    Assistant messages also record the stream's start time and duration (ms) so
    the timing survives a page reload.
    """
    if not content:
        return
    conn = await _meta_conn()
    await conn.execute(
        "INSERT INTO thread_messages"
        " (thread_id, role, content, created_at, stream_started_at, stream_elapsed_ms)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (thread_id, role, content, created_at, stream_started_at, stream_elapsed_ms),
    )
    await conn.commit()


def _iso_delta_ms(started_at: str | None, ended_at: str | None) -> float | None:
    if not started_at or not ended_at:
        return None
    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(ended_at)
        return round((end - start).total_seconds() * 1000)
    except (ValueError, TypeError):
        return None


async def record_runs(
    thread_id: str, runs: list[dict[str, Any]], workspace_id: str | None = None
) -> None:
    """Persist one chat call's model rounds with token usage and tool communication."""
    if not runs:
        return
    conn = await _meta_conn()
    cur = await conn.execute(
        "SELECT COALESCE(MAX(run_index), 0) FROM thread_runs WHERE thread_id = ?",
        (thread_id,),
    )
    row = await cur.fetchone()
    start_index = row[0] if row else 0
    for i, run in enumerate(runs, start=1):
        await conn.execute(
            "INSERT INTO thread_runs (thread_id, run_index, started_at, ended_at,"
            " input_tokens, output_tokens, total_tokens, input_preview, output_preview,"
            " tools_json, workspace_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                thread_id,
                start_index + i,
                run.get("started_at"),
                run.get("ended_at"),
                run.get("input_tokens"),
                run.get("output_tokens"),
                run.get("total_tokens"),
                (run.get("input_preview") or "")[:PREVIEW_LIMIT],
                (run.get("output_preview") or "")[:PREVIEW_LIMIT],
                json.dumps(run.get("tools") or [], ensure_ascii=False),
                workspace_id,
            ),
        )
    await conn.commit()


def _run_to_dict(row: tuple) -> dict[str, Any]:
    (
        _id,
        _thread_id,
        run_index,
        started_at,
        ended_at,
        input_tokens,
        output_tokens,
        total_tokens,
        input_preview,
        output_preview,
        tools_json,
        workspace_id,
    ) = row
    tools = json.loads(tools_json) if tools_json else []
    return {
        "run_index": run_index,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_ms": _iso_delta_ms(started_at, ended_at),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "input_preview": input_preview,
        "output_preview": output_preview,
        "tools": tools,
        "workspace_id": workspace_id,
    }


async def thread_runs(thread_id: str, workspace_id: str | None = None) -> dict[str, Any] | None:
    """Return one thread's model-round runs (token usage + tool communication).

    When workspace_id is given, threads belonging to another workspace are hidden.
    """
    conn = await _meta_conn()
    if workspace_id is not None:
        _m_title, _m_archived, meta_ws = await _load_thread_meta(thread_id)
        if effective_workspace_id(workspace_id) != effective_workspace_id(meta_ws):
            return None
    cur = await conn.execute(
        "SELECT * FROM thread_runs WHERE thread_id = ? ORDER BY run_index", (thread_id,)
    )
    rows = await cur.fetchall()
    if not rows:
        return None
    title, archived, workspace_id = await _load_thread_meta(thread_id)
    runs = [_run_to_dict(r) for r in rows]
    totals = {
        "input_tokens": sum(r["input_tokens"] or 0 for r in runs),
        "output_tokens": sum(r["output_tokens"] or 0 for r in runs),
        "total_tokens": sum(r["total_tokens"] or 0 for r in runs),
        "tool_count": sum(len(r["tools"]) for r in runs),
    }
    non_null = [r["duration_ms"] for r in runs if r["duration_ms"] is not None]
    totals["avg_duration_ms"] = (
        round(sum(non_null) / len(non_null)) if non_null else None
    )
    return {
        "thread_id": thread_id,
        "title": title,
        "archived": archived,
        "workspace_id": workspace_id,
        "run_count": len(runs),
        "totals": totals,
        "runs": runs,
    }


async def runs_summary(workspace_id: str | None = None) -> list[dict[str, Any]]:
    """Summarise run usage per thread (scoped to a workspace), newest first."""
    conn = await _meta_conn()
    eff = effective_workspace_id(workspace_id)
    cur = await conn.execute(
        "SELECT * FROM thread_runs WHERE COALESCE(workspace_id, ?) = ? ORDER BY id",
        (DEFAULT_WORKSPACE_ID, eff),
    )
    rows = await cur.fetchall()
    by_thread: dict[str, dict[str, Any]] = {}
    for row in rows:
        run = _run_to_dict(row)
        thread_id = row[1]
        agg = by_thread.setdefault(
            thread_id,
            {
                "thread_id": thread_id,
                "run_count": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_tokens": 0,
                "tool_count": 0,
                "last_run_at": None,
                "workspace_id": run["workspace_id"],
            },
        )
        agg["run_count"] += 1
        agg["total_input_tokens"] += run["input_tokens"] or 0
        agg["total_output_tokens"] += run["output_tokens"] or 0
        agg["total_tokens"] += run["total_tokens"] or 0
        agg["tool_count"] += len(run["tools"])
        if run["ended_at"] and (
            agg["last_run_at"] is None or run["ended_at"] > agg["last_run_at"]
        ):
            agg["last_run_at"] = run["ended_at"]
    result = list(by_thread.values())
    for thread_id, agg in by_thread.items():
        title, _archived, ws_id = await _load_thread_meta(thread_id)
        agg["title"] = title
        agg["workspace_id"] = ws_id or agg["workspace_id"]
    result.sort(key=lambda a: a["last_run_at"] or "", reverse=True)
    return result


async def _load_thread_meta(thread_id: str) -> tuple[str | None, bool, str | None]:
    conn = await _meta_conn()
    cur = await conn.execute(
        "SELECT title, archived, workspace_id FROM thread_meta WHERE thread_id = ?",
        (thread_id,),
    )
    row = await cur.fetchone()
    if row is None:
        return None, False, None
    return row[0], bool(row[1]), row[2]


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
    title, archived, workspace_id = await _load_thread_meta(thread_id)
    return {
        "thread_id": thread_id,
        "title": title,
        "archived": archived,
        "workspace_id": workspace_id,
    }


async def _stored_messages(thread_id: str) -> list[dict[str, Any]] | None:
    conn = await _meta_conn()
    cur = await conn.execute(
        "SELECT role, content, created_at, stream_started_at, stream_elapsed_ms"
        " FROM thread_messages WHERE thread_id = ? ORDER BY id",
        (thread_id,),
    )
    rows = await cur.fetchall()
    if not rows:
        return None
    return [
        {
            "role": role,
            "content": content,
            "created_at": created_at,
            "stream_started_at": stream_started_at,
            "stream_elapsed_ms": stream_elapsed_ms,
        }
        for role, content, created_at, stream_started_at, stream_elapsed_ms in rows
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


async def _thread_created_at(saver, thread_id: str) -> str | None:
    """Look up the first (oldest) checkpoint_id for a thread from SQLite."""
    cur = await saver.conn.execute(
        "SELECT MIN(checkpoint_id) FROM checkpoints WHERE thread_id = ?",
        (thread_id,),
    )
    row = await cur.fetchone()
    return _checkpoint_ts(row[0] if row else None)


async def list_threads(limit: int = 100, workspace_id: str | None = None) -> list[dict[str, Any]]:
    """List threads of one workspace (default when omitted), newest first.

    Threads are enumerated as distinct rows (one per thread_id) so that thread
    count, not checkpoint-row count, is what the limit bounds. Untagged/legacy
    threads belong to the default workspace.
    """
    saver = await open_checkpointer()
    eff = effective_workspace_id(workspace_id)
    if eff == DEFAULT_WORKSPACE_ID:
        where = "WHERE tm.thread_id IS NULL OR COALESCE(tm.workspace_id, ?) = ?"
        params: tuple = (DEFAULT_WORKSPACE_ID, eff, limit)
    else:
        where = "WHERE tm.thread_id IS NOT NULL AND tm.workspace_id = ?"
        params = (eff, limit)
    cur = await saver.conn.execute(
        "SELECT c.thread_id, MAX(c.checkpoint_id) AS cid"
        " FROM checkpoints c LEFT JOIN thread_meta tm ON tm.thread_id = c.thread_id"
        f" {where} GROUP BY c.thread_id ORDER BY cid DESC LIMIT ?",
        params,
    )
    rows = await cur.fetchall()
    threads: list[dict[str, Any]] = []
    for (thread_id, _cid) in rows:
        tup = await saver.aget_tuple(
            {"configurable": {"thread_id": thread_id}}
        )
        if tup is None:
            continue
        messages = (tup.checkpoint or {}).get("channel_values", {}).get("messages", [])
        messages = [m for m in messages if isinstance(m, BaseMessage)]
        first_user = next((m for m in messages if isinstance(m, HumanMessage)), None)
        title, archived, workspace_id = await _load_thread_meta(thread_id)
        threads.append({
            "thread_id": thread_id,
            "title": title,
            "archived": archived,
            "workspace_id": workspace_id,
            "message_count": len(messages),
            "created_at": await _thread_created_at(saver, thread_id),
            "updated_at": _checkpoint_ts(
                (tup.config or {}).get("configurable", {}).get("checkpoint_id")
            ),
            "last_message": _message_to_dict(messages[-1]) if messages else None,
            "first_user_message": (
                str(first_user.content)[:80] if first_user and first_user.content else None
            ),
        })
    return threads


async def get_thread(thread_id: str, workspace_id: str | None = None) -> dict[str, Any] | None:
    """Return one thread's message history (with timestamps), or None.

    When workspace_id is given, threads belonging to another workspace are hidden.
    """
    saver = await open_checkpointer()
    tup = await saver.aget_tuple(
        {"configurable": {"thread_id": thread_id}}
    )
    if tup is None:
        return None
    title, archived, workspace_id_from_meta = await _load_thread_meta(thread_id)
    if workspace_id is not None and effective_workspace_id(workspace_id) != effective_workspace_id(
        workspace_id_from_meta
    ):
        return None
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
        "workspace_id": workspace_id,
        "created_at": await _thread_created_at(saver, thread_id),
        "updated_at": _checkpoint_ts(
            (tup.config or {}).get("configurable", {}).get("checkpoint_id")
        ),
        "messages": messages,
    }


async def delete_thread(thread_id: str) -> None:
    saver = await open_checkpointer()
    await saver.adelete_thread(thread_id)
    conn = await _meta_conn()
    for table in ("thread_messages", "thread_meta", "thread_runs"):
        await conn.execute(
            f"DELETE FROM {table} WHERE thread_id = ?", (thread_id,)
        )
    await conn.commit()