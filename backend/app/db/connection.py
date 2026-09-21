"""Long-lived SQLite connections: the langgraph checkpointer and app metadata.

Both share the same SQLite file. The checkpointer owns conversation state; the
metadata connection owns the app tables (see db/migrations.py).
"""

import logging
import os

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from ..config import THREADS_DB_PATH
from .migrations import apply_schema

logger = logging.getLogger("app.agent")

_saver: AsyncSqliteSaver | None = None
_meta_conn_ref: aiosqlite.Connection | None = None


def _ensure_dir() -> None:
    os.makedirs(os.path.dirname(THREADS_DB_PATH), exist_ok=True)


async def open_checkpointer() -> AsyncSqliteSaver:
    """Return a long-lived AsyncSqliteSaver backed by a persistent SQLite file."""
    global _saver
    if _saver is None:
        _ensure_dir()
        conn = await aiosqlite.connect(THREADS_DB_PATH)
        saver = AsyncSqliteSaver(conn)
        await saver.setup()
        logger.info("SQLite checkpointer initialized at %s", THREADS_DB_PATH)
        _saver = saver
    return _saver


async def meta_conn() -> aiosqlite.Connection:
    """Return a long-lived connection to the app's thread metadata tables."""
    global _meta_conn_ref
    if _meta_conn_ref is None:
        _ensure_dir()
        conn = await aiosqlite.connect(THREADS_DB_PATH)
        await apply_schema(conn)
        logger.info("Thread metadata tables ready at %s", THREADS_DB_PATH)
        _meta_conn_ref = conn
    return _meta_conn_ref


async def close_checkpointer() -> None:
    global _saver, _meta_conn_ref
    if _saver is not None:
        await _saver.conn.close()
        _saver = None
    if _meta_conn_ref is not None:
        await _meta_conn_ref.close()
        _meta_conn_ref = None