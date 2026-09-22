"""Workspace model: directories that scope the agent's file access and rules.

Every workspace is a directory on disk. Its root is the boundary for file
operations performed by the agent, and its rules live in a local
``.local_agent_workspace`` folder:

    .local_agent_workspace/
      config.json     machine policy (safe/unsafe/allowed commands, exemptions)
      guidelines.md   free-form instructions injected into the agent prompt

    config.json shape:
    {
      "safe_commands": ["npm test"],
      "unsafe_commands": ["terraform destroy"],
      "allowed_commands": ["npm install lodash"],
      "exemptions": ["delete_file:c:/abs/path/to/file.txt"]
    }

The default workspace is the project root; it keeps reading the legacy
``allowed_commands.json`` for its exemptions unless a ``.local_agent_workspace``
folder appears at the project root. A legacy ``.local_agent_workspace`` JSON
file is migrated into ``.local_agent_workspace/config.json`` automatically. The
active workspace id is persisted in app ``settings`` so it survives restarts,
and it is also kept in memory for synchronous tool calls.
"""

import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .config import (
    ALLOWED_COMMANDS_FILE,
    DEFAULT_WORKSPACE_ID,
    PROJECT_ROOT,
    WORKSPACE_CONFIG_DIR,
    WORKSPACE_CONFIG_NAME,
    WORKSPACE_GUIDELINES_NAME,
)
from .db import meta_conn as _meta_conn

logger = logging.getLogger("app.agent")

_current: "Workspace | None" = None

GUIDELINES_TEMPLATE = (
    "# Workspace guidelines\n\n"
    "Instructions in this file are added to the agent's system prompt whenever it\n"
    "works in this workspace. Use it for conventions, constraints, and context.\n"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def workspace_dir(root: str) -> str:
    """Path of the .local_agent_workspace folder for a workspace root."""
    return os.path.join(root, WORKSPACE_CONFIG_DIR)


def config_path(root: str) -> str:
    return os.path.join(workspace_dir(root), WORKSPACE_CONFIG_NAME)


def guidelines_path(root: str) -> str:
    return os.path.join(workspace_dir(root), WORKSPACE_GUIDELINES_NAME)


def migrate_workspace_config(root: str) -> None:
    """Convert a legacy .local_agent_workspace JSON file into the folder layout."""
    legacy = workspace_dir(root)
    if not os.path.isfile(legacy):
        return
    try:
        with open(legacy, encoding="utf-8") as f:
            data = json.load(f)
        cfg = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        cfg = {}
    try:
        os.remove(legacy)
        os.makedirs(legacy, exist_ok=True)
        with open(config_path(root), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        logger.info("migrated legacy workspace config root=%s", root)
    except OSError:
        logger.exception("workspace config migration failed root=%s", root)


@dataclass
class Workspace:
    id: str
    name: str
    root_path: str
    config: dict[str, Any]
    is_default: bool = False
    created_at: str = ""
    updated_at: str = ""

    @property
    def config_file(self) -> str:
        """Where persistent exemptions/rules are written for this workspace."""
        if self.is_default:
            # Backward compatible: default workspace still uses the legacy file
            # unless a .local_agent_workspace folder exists at the project root.
            if os.path.isdir(workspace_dir(PROJECT_ROOT)):
                return config_path(PROJECT_ROOT)
            return ALLOWED_COMMANDS_FILE
        return config_path(self.root_path)

    @property
    def guidelines_file(self) -> str:
        return guidelines_path(self.root_path)


def make_workspace(
    ws_id: str = "",
    name: str = "workspace",
    root_path: str = PROJECT_ROOT,
    config: dict[str, Any] | None = None,
    is_default: bool = False,
) -> Workspace:
    return Workspace(
        id=ws_id or (DEFAULT_WORKSPACE_ID if is_default else f"ws_{uuid.uuid4().hex}"),
        name=name,
        root_path=os.path.abspath(root_path),
        config=config or {},
        is_default=is_default,
    )


def default_workspace() -> Workspace:
    cfg = load_workspace_config(PROJECT_ROOT)
    return Workspace(
        id=DEFAULT_WORKSPACE_ID,
        name="Default",
        root_path=PROJECT_ROOT,
        config=cfg,
        is_default=True,
        created_at="",
        updated_at="",
    )


def load_workspace_config(root: str) -> dict[str, Any]:
    """Read .local_agent_workspace/config.json at root; {} when missing/invalid."""
    migrate_workspace_config(root)
    path = config_path(root)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_workspace_config(root: str, config: dict[str, Any]) -> None:
    """Write .local_agent_workspace/config.json at root (creating the folder)."""
    migrate_workspace_config(root)
    os.makedirs(workspace_dir(root), exist_ok=True)
    with open(config_path(root), "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def load_workspace_guidelines(root: str) -> str:
    """Read .local_agent_workspace/guidelines.md at root; '' when missing."""
    try:
        with open(guidelines_path(root), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def save_workspace_guidelines(root: str, text: str) -> None:
    """Write .local_agent_workspace/guidelines.md at root (creating the folder)."""
    os.makedirs(workspace_dir(root), exist_ok=True)
    with open(guidelines_path(root), "w", encoding="utf-8") as f:
        f.write(text)


def get_current() -> Workspace:
    """Synchronous accessor used by tools; falls back to the default workspace."""
    return _current if _current is not None else default_workspace()


def set_current(ws: Workspace | None) -> None:
    global _current
    _current = ws


async def init_current() -> None:
    """Load the persisted active workspace into memory on startup."""
    ws = await get_workspace(await _get_setting("active_workspace_id"))
    set_current(ws or default_workspace())
    if _current is not None:
        logger.info("active workspace id=%s root=%s", _current.id, _current.root_path)


async def _get_setting(key: str) -> str | None:
    conn = await _meta_conn()
    cur = await conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = await cur.fetchone()
    return row[0] if row else None


async def _set_setting(key: str, value: str) -> None:
    conn = await _meta_conn()
    await conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    await conn.commit()


def _row_to_workspace(row: tuple) -> Workspace:
    ws_id, name, root, is_default, config_json, created_at, updated_at = row
    try:
        config = json.loads(config_json) if config_json else {}
        config = config if isinstance(config, dict) else {}
    except (ValueError, TypeError):
        config = {}
    return Workspace(
        id=ws_id,
        name=name,
        root_path=root,
        config=config,
        is_default=bool(is_default),
        created_at=created_at,
        updated_at=updated_at,
    )


async def list_workspaces() -> list[Workspace]:
    conn = await _meta_conn()
    cur = await conn.execute("SELECT * FROM workspaces ORDER BY is_default DESC, created_at")
    rows = await cur.fetchall()
    workspaces = [_row_to_workspace(r) for r in rows]
    for ws in workspaces:
        ws.config = load_workspace_config(ws.root_path) or ws.config
    if not workspaces or not any(w.is_default for w in workspaces):
        cfg = load_workspace_config(PROJECT_ROOT)
        workspaces.insert(
            0,
            Workspace(
                id=DEFAULT_WORKSPACE_ID,
                name="Default",
                root_path=PROJECT_ROOT,
                config=cfg,
                is_default=True,
                created_at=_now(),
                updated_at=_now(),
            ),
        )
    return workspaces


async def get_workspace(ws_id: str | None) -> Workspace | None:
    if not ws_id:
        return default_workspace()
    if ws_id == DEFAULT_WORKSPACE_ID:
        return default_workspace()
    conn = await _meta_conn()
    cur = await conn.execute("SELECT * FROM workspaces WHERE id = ?", (ws_id,))
    row = await cur.fetchone()
    if row is None:
        return None
    ws = _row_to_workspace(row)
    ws.config = load_workspace_config(ws.root_path) or ws.config
    return ws


async def workspace_by_root(root: str) -> Workspace | None:
    conn = await _meta_conn()
    cur = await conn.execute(
        "SELECT * FROM workspaces WHERE lower(root_path) = lower(?)", (os.path.abspath(root),)
    )
    row = await cur.fetchone()
    return _row_to_workspace(row) if row else None


async def create_workspace(name: str, root_path: str) -> Workspace:
    root = os.path.abspath(root_path)
    if not os.path.isdir(root):
        raise ValueError(f"workspace root does not exist: {root}")
    existing = await workspace_by_root(root)
    if existing is not None:
        raise ValueError(f"a workspace already exists for {root}")
    ws = make_workspace(name=name, root_path=root)
    now = _now()
    conn = await _meta_conn()
    await conn.execute(
        "INSERT INTO workspaces (id, name, root_path, is_default, config_json, created_at, updated_at)"
        " VALUES (?, ?, ?, 0, ?, ?, ?)",
        (ws.id, ws.name, ws.root_path, json.dumps(ws.config), now, now),
    )
    await conn.commit()
    # Preserve any migrated legacy config instead of clobbering it with {}.
    save_workspace_config(ws.root_path, load_workspace_config(ws.root_path) or {})
    if not os.path.exists(guidelines_path(ws.root_path)):
        save_workspace_guidelines(ws.root_path, GUIDELINES_TEMPLATE)
    logger.info("workspace created id=%s root=%s", ws.id, ws.root_path)
    return ws


async def update_workspace(
    ws_id: str,
    name: str | None = None,
    config: dict[str, Any] | None = None,
    guidelines: str | None = None,
) -> Workspace | None:
    ws = await get_workspace(ws_id)
    if ws is None:
        return None
    now = _now()
    cfg = ws.config if config is None else config
    conn = await _meta_conn()
    if name is not None:
        await conn.execute(
            "UPDATE workspaces SET name = ?, updated_at = ? WHERE id = ?",
            (name.strip() or ws.name, now, ws_id),
        )
    await conn.execute(
        "UPDATE workspaces SET config_json = ?, updated_at = ? WHERE id = ?",
        (json.dumps(cfg), now, ws_id),
    )
    await conn.commit()
    save_workspace_config(ws.root_path, cfg)
    if guidelines is not None:
        save_workspace_guidelines(ws.root_path, guidelines)
    if _current is not None and _current.id == ws_id:
        set_current(
            Workspace(
                id=ws_id,
                name=(name or ws.name).strip(),
                root_path=ws.root_path,
                config=cfg,
                is_default=ws.is_default,
                created_at=ws.created_at,
                updated_at=now,
            )
        )
    logger.info("workspace updated id=%s", ws_id)
    return await get_workspace(ws_id)


async def delete_workspace(ws_id: str) -> bool:
    ws = await get_workspace(ws_id)
    if ws is None or ws.is_default:
        return False
    conn = await _meta_conn()
    await conn.execute("DELETE FROM workspaces WHERE id = ?", (ws_id,))
    await conn.commit()
    if (await _get_setting("active_workspace_id")) == ws_id:
        await activate_workspace(DEFAULT_WORKSPACE_ID)
    logger.info("workspace deleted id=%s", ws_id)
    return True


async def activate_workspace(ws_id: str) -> Workspace:
    ws = await get_workspace(ws_id)
    if ws is None:
        raise ValueError(f"workspace not found: {ws_id}")
    await _set_setting("active_workspace_id", ws.id)
    set_current(ws)
    logger.info("workspace activated id=%s root=%s", ws.id, ws.root_path)
    return ws