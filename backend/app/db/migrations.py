"""SQLite schema definition and migrations for the agent backend.

Tables are created idempotently; historically added columns are applied as
ALTER TABLE migrations when the table already exists.
"""


SCHEMA: dict[str, list[str]] = {
    "thread_meta": [
        "thread_id TEXT PRIMARY KEY",
        "title TEXT",
        "archived INTEGER NOT NULL DEFAULT 0",
        "created_at TEXT NOT NULL",
        "updated_at TEXT NOT NULL",
    ],
    "thread_messages": [
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "thread_id TEXT NOT NULL",
        "role TEXT NOT NULL",
        "content TEXT NOT NULL",
        "created_at TEXT NOT NULL",
        "stream_started_at TEXT",
        "stream_elapsed_ms INTEGER",
    ],
    "thread_runs": [
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "thread_id TEXT NOT NULL",
        "run_index INTEGER NOT NULL",
        "started_at TEXT",
        "ended_at TEXT",
        "input_tokens INTEGER",
        "output_tokens INTEGER",
        "total_tokens INTEGER",
        "input_preview TEXT",
        "output_preview TEXT",
        "tools_json TEXT",
    ],
}

# Columns appended to existing tables when the app is upgraded.
MIGRATIONS: dict[str, list[tuple[str, str]]] = {
    "thread_messages": [
        ("stream_started_at", "TEXT"),
        ("stream_elapsed_ms", "INTEGER"),
    ],
}


async def apply_schema(conn) -> None:
    """Create missing tables/columns on the given aiosqlite connection."""
    for table, columns in SCHEMA.items():
        await conn.execute(
            f"CREATE TABLE IF NOT EXISTS {table} (" + ", ".join(columns) + ")"
        )
    for table, migrations in MIGRATIONS.items():
        cur = await conn.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in await cur.fetchall()}
        for column, ctype in migrations:
            if column not in existing:
                await conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {ctype}"
                )
    await conn.commit()