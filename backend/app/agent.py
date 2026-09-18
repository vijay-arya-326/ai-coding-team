"""A basic LangGraph agent backed by Ollama's phi3 model, with SQLite thread persistence."""

import json
import logging
import os
import shutil
import subprocess
import time as _time
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
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THREADS_DB_PATH = os.getenv(
    "THREADS_DB_PATH", os.path.join(BASE_DIR, "db", "agent_state.db")
)

SYSTEM_PROMPT = (
    "You are a helpful assistant running on llama3.1:8b. Be concise and accurate. "
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


PROJECT_ROOT = os.path.dirname(BASE_DIR)

SAFE_COMMANDS = (
    "ls", "dir", "pwd", "cat", "type", "head", "tail", "echo",
    "where", "which", "find", "git status", "git log", "git diff",
    "git branch", "git ls-files", "git blame",
)

UNSAFE_MARKERS = (
    "rm ", "rm -", "rmdir", "remove-item", "del ", "erase ",
    "format ", "shutdown", "restart", "sudo", "su ",
    "curl ", "wget ", "iwr ", "invoke-webrequest", "invoke-restmethod",
    "pip install", "pip uninstall", "npm install", "npm uninstall",
    "git push", "git pull", "git reset", "git clean", "git revert",
    "git checkout .", "chmod", "chown", "chkdsk",
    "taskkill", "kill ", "stop-process", "stop-service",
    ">", "|", ";", "&&", "||", "$(",
)

# Pending approvals for destructive or unsafe actions, keyed by approval id.
PENDING_APPROVALS: dict[str, dict] = {}
_approval_counter = 0

# Command exemptions. ONE_TIME_ALLOWED lives in memory only; PERMANENT_ALLOWED
# persists to a JSON file and is loaded at startup.
ALLOWED_COMMANDS_FILE = os.getenv(
    "ALLOWED_COMMANDS_FILE", os.path.join(BASE_DIR, "allowed_commands.json")
)


def _load_permanent_allowed() -> set[str]:
    try:
        with open(ALLOWED_COMMANDS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return {str(c).strip() for c in data.get("allowed", []) if str(c).strip()}
    except (OSError, ValueError):
        return set()


PERMANENT_ALLOWED: set[str] = _load_permanent_allowed()
ONE_TIME_ALLOWED: set[str] = set()


def _save_permanent_allowed() -> None:
    with open(ALLOWED_COMMANDS_FILE, "w", encoding="utf-8") as f:
        json.dump({"allowed": sorted(PERMANENT_ALLOWED)}, f, indent=2)


def _normalize_command(command: str) -> str:
    return " ".join(command.split()).lower()


def grant_exception(command: str, allow: str | None) -> bool:
    """Add a command exemption. 'always' persists it, 'once' allows a single use."""
    if not command or allow not in ("once", "always"):
        return False
    cmd = _normalize_command(command)
    if allow == "always":
        PERMANENT_ALLOWED.add(cmd)
        _save_permanent_allowed()
        return True
    ONE_TIME_ALLOWED.add(cmd)
    return True


def classify_command(command: str) -> bool:
    """Return True when the command may run without approval.

    Safe whitelist and granted exemptions (permanent or one-time) bypass approval;
    the one-time exemption is consumed after a single use.
    """
    cmd = _normalize_command(command)
    if not cmd:
        return False
    for prefix in SAFE_COMMANDS:
        if cmd == prefix or cmd.startswith(prefix + " "):
            return True
    if cmd in PERMANENT_ALLOWED:
        return True
    if cmd in ONE_TIME_ALLOWED:
        ONE_TIME_ALLOWED.discard(cmd)
        return True
    for marker in UNSAFE_MARKERS:
        if marker in cmd:
            return False
    return False


def _resolve_project_path(raw: str) -> str:
    """Resolve a model-supplied path to an absolute path inside PROJECT_ROOT.

    POSIX-style root paths like '/tools_demo' are treated as project-root relative
    (they come from POSIX-trained models). Paths escaping PROJECT_ROOT are rejected.
    """
    raw = os.path.expandvars(os.path.expanduser((raw or "").strip().strip('"')))
    if not raw:
        raise ValueError("empty path")
    if raw.startswith("/") and not raw.startswith("//"):
        resolved = os.path.normpath(os.path.join(PROJECT_ROOT, raw.lstrip("/")))
    elif os.path.isabs(raw):
        resolved = os.path.normpath(raw)
    else:
        resolved = os.path.normpath(os.path.join(PROJECT_ROOT, raw))
    resolved = os.path.abspath(resolved)
    root = os.path.abspath(PROJECT_ROOT)
    if resolved != root and os.path.commonpath([resolved, root]) != root:
        raise ValueError(f"path resolves outside the project root: {raw}")
    return resolved


def _pending_approval(kind: str, params: dict, description: str) -> str:
    global _approval_counter
    _approval_counter += 1
    approval_id = f"appr_{_approval_counter}"
    PENDING_APPROVALS[approval_id] = {
        "kind": kind,
        "params": params,
        "description": description,
        "ts": _time.time(),
    }
    return approval_id


def _run_shell(command: str, cwd: str, timeout: int = 90) -> tuple[int, str]:
    if os.name == "nt":
        c = command.strip()
        if c == "ls":
            command = "dir"
        elif c.startswith("ls "):
            command = "dir " + c[3:]
        elif c == "pwd":
            command = "cd"
        elif c == "cat" or c.startswith("cat "):
            command = "type " + c[3:] if c != "cat" else "type"
    proc = subprocess.run(
        command,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    return proc.returncode, (out + ("\n" + err if err else "")).strip()


def resolve_approval(approval_id: str, approved: bool, allow: str | None = None) -> dict:
    """Execute or reject a previously requested approval.

    allow may be 'once' or 'always' to grant the same command an exemption from
    future approval prompts (persisted for 'always').
    """
    entry = PENDING_APPROVALS.pop(approval_id, None)
    if entry is None:
        return {"status": "not_found", "approval_id": approval_id}
    if not approved:
        return {"status": "rejected", "approval_id": approval_id, "kind": entry["kind"]}
    kind, params = entry["kind"], entry["params"]
    result: dict = {"status": "approved", "kind": kind, "approval_id": approval_id}
    granted = False
    try:
        if kind == "delete_file":
            os.remove(params["path"])
            result["result"] = f"deleted file {params['path']}"
        elif kind == "delete_folder":
            shutil.rmtree(params["path"])
            result["result"] = f"deleted folder {params['path']}"
        elif kind == "shell":
            code, out = _run_shell(params["command"], params.get("cwd") or PROJECT_ROOT)
            result["exit_code"] = code
            result["output"] = out
            if allow in ("once", "always"):
                granted = grant_exception(params["command"], allow)
        else:
            result["status"] = "unknown_kind"
    except FileNotFoundError:
        result["error"] = "path not found"
    except PermissionError as exc:
        result["error"] = f"permission denied: {exc}"
    except subprocess.TimeoutExpired:
        result["error"] = "command timed out"
    if granted:
        result["allow_granted"] = allow
    return result


@tool
def create_dir(path: str) -> str:
    """Create a directory (and any missing parents) at the given absolute or relative path."""
    try:
        target = _resolve_project_path(path)
        os.makedirs(target, exist_ok=True)
        return f"created directory {target}"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: could not create directory {path}: {exc}"


@tool
def create_file(path: str, content: str) -> str:
    """Create or overwrite a text file at the given path with the given content."""
    try:
        target = _resolve_project_path(path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        return f"created file {target} ({len(content)} chars)"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: could not create file {path}: {exc}"


@tool
def edit_file(path: str, old_string: str, new_string: str) -> str:
    """Replace old_string with new_string in a text file. old_string must be an exact, unique match."""
    try:
        target = _resolve_project_path(path)
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {exc}"
    try:
        with open(target, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return f"ERROR: file not found: {target}"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: could not read {target}: {exc}"
    if old_string not in content:
        return f"ERROR: old_string not found in {target}"
    if content.count(old_string) > 1:
        return f"ERROR: old_string appears {content.count(old_string)} times; include more context"
    with open(target, "w", encoding="utf-8") as f:
        f.write(content.replace(old_string, new_string, 1))
    return f"edited {target}"


@tool
def rename_file(path: str, new_path: str) -> str:
    """Rename or move path to new_path."""
    try:
        src = _resolve_project_path(path)
        dst = _resolve_project_path(new_path)
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {exc}"
    try:
        os.rename(src, dst)
        return f"renamed {src} -> {dst}"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: could not rename {path}: {exc}"


@tool
def delete_file(path: str) -> str:
    """Delete a file. Requires user confirmation before the file is removed."""
    try:
        target = _resolve_project_path(path)
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {exc}"
    approval_id = _pending_approval(
        "delete_file", {"path": target}, f"Delete file `{target}`?"
    )
    return f"ACTION_REQUIRES_APPROVAL:{approval_id}"


@tool
def delete_folder(path: str) -> str:
    """Delete a folder and everything inside it. Requires user confirmation before deletion."""
    try:
        target = _resolve_project_path(path)
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {exc}"
    approval_id = _pending_approval(
        "delete_folder", {"path": target}, f"Delete folder `{target}` recursively?"
    )
    return f"ACTION_REQUIRES_APPROVAL:{approval_id}"


@tool
def run_shell_command(command: str) -> str:
    """Run a shell command in the project root. Read-only commands run immediately; anything else requires explicit user approval."""
    if not classify_command(command):
        approval_id = _pending_approval(
            "shell",
            {"command": command, "cwd": PROJECT_ROOT},
            f"Run shell command `{command}`?",
        )
        return f"ACTION_REQUIRES_APPROVAL:{approval_id}"
    try:
        code, out = _run_shell(command, PROJECT_ROOT)
        return f"exit {code}\n{out}"
    except subprocess.TimeoutExpired:
        return "ERROR: command timed out"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {exc}"


TOOLS = [
    calculator,
    create_dir,
    create_file,
    edit_file,
    rename_file,
    delete_file,
    delete_folder,
    run_shell_command,
]


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
            " created_at TEXT NOT NULL,"
            " stream_started_at TEXT,"
            " stream_elapsed_ms INTEGER)"
        )
        cur = await conn.execute("PRAGMA table_info(thread_messages)")
        existing = {row[1] for row in await cur.fetchall()}
        if "stream_started_at" not in existing:
            await conn.execute(
                "ALTER TABLE thread_messages ADD COLUMN stream_started_at TEXT"
            )
        if "stream_elapsed_ms" not in existing:
            await conn.execute(
                "ALTER TABLE thread_messages ADD COLUMN stream_elapsed_ms INTEGER"
            )
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS thread_runs ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " thread_id TEXT NOT NULL,"
            " run_index INTEGER NOT NULL,"
            " started_at TEXT,"
            " ended_at TEXT,"
            " input_tokens INTEGER,"
            " output_tokens INTEGER,"
            " total_tokens INTEGER,"
            " input_preview TEXT,"
            " output_preview TEXT,"
            " tools_json TEXT)"
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


async def record_runs(thread_id: str, runs: list[dict[str, Any]]) -> None:
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
            " tools_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                thread_id,
                start_index + i,
                run.get("started_at"),
                run.get("ended_at"),
                run.get("input_tokens"),
                run.get("output_tokens"),
                run.get("total_tokens"),
                (run.get("input_preview") or "")[:50000],
                (run.get("output_preview") or "")[:50000],
                json.dumps(run.get("tools") or [], ensure_ascii=False),
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
    }


async def thread_runs(thread_id: str) -> dict[str, Any] | None:
    """Return one thread's model-round runs (token usage + tool communication)."""
    conn = await _meta_conn()
    cur = await conn.execute(
        "SELECT * FROM thread_runs WHERE thread_id = ? ORDER BY run_index", (thread_id,)
    )
    rows = await cur.fetchall()
    if not rows:
        return None
    title, archived = await _load_thread_meta(thread_id)
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
        "run_count": len(runs),
        "totals": totals,
        "runs": runs,
    }


async def runs_summary() -> list[dict[str, Any]]:
    """Summarise run usage per thread, newest first."""
    conn = await _meta_conn()
    cur = await conn.execute("SELECT * FROM thread_runs ORDER BY id")
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
        title, _archived = await _load_thread_meta(thread_id)
        agg["title"] = title
    result.sort(key=lambda a: a["last_run_at"] or "", reverse=True)
    return result


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
    conn = await _meta_conn()
    for table in ("thread_messages", "thread_meta", "thread_runs"):
        await conn.execute(
            f"DELETE FROM {table} WHERE thread_id = ?", (thread_id,)
        )
    await conn.commit()