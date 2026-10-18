"""Agent tools: calculator, filesystem operations, and shell execution.

File paths supplied by the model are resolved against the active workspace's
root (POSIX-style root paths count as workspace-root relative) and paths
escaping the workspace root are rejected. Destructive operations are auto-run
when an exemption exists for the pattern's workspace, and otherwise pause the
graph with `interrupt()` until the user approves or rejects the action.
"""

import fnmatch
import os
import shutil

from langchain_core.tools import tool
from langgraph.types import interrupt

from . import workspace as ws_mod
from .approvals import consume_exemption, grant_exception, grant_path_exemption
from .config import (
    IGNORED_DIRS,
    LIST_MAX_ENTRIES,
    READ_MAX_BYTES,
    READ_MAX_LINES,
    SEARCH_MAX_RESULTS,
    SHELL_TIMEOUT,
    STRUCTURE_MAX_DEPTH,
    STRUCTURE_MAX_ENTRIES,
)
from .shell import classify_command, run_shell


def _await_approval(payload: dict) -> dict:
    """Pause the graph until the user decides; returns the resume decision."""
    decision = interrupt(payload)
    if not isinstance(decision, dict):
        return {"approved": False}
    return decision


def resolve_project_path(raw: str) -> str:
    """Resolve a model-supplied path against the active workspace root.

    POSIX-style root paths like '/tools_demo' are treated as workspace-root
    relative (they come from POSIX-trained models), but an absolute path that
    already lies inside the workspace root is used as-is so the root is never
    prefixed twice. Paths escaping the workspace root are rejected.
    """
    root = os.path.abspath(ws_mod.get_current().root_path)
    raw = os.path.expandvars(os.path.expanduser((raw or "").strip().strip('"')))
    if not raw:
        raise ValueError("empty path")
    if raw.startswith("/") and not raw.startswith("//"):
        candidate = os.path.normpath(raw)
        try:
            inside = candidate == root or os.path.commonpath([candidate, root]) == root
        except ValueError:
            inside = False
        if inside:
            resolved = candidate
        else:
            resolved = os.path.normpath(os.path.join(root, raw.lstrip("/")))
    elif os.path.isabs(raw):
        resolved = os.path.normpath(raw)
    else:
        resolved = os.path.normpath(os.path.join(root, raw))
    resolved = os.path.abspath(resolved)
    if resolved != root and os.path.commonpath([resolved, root]) != root:
        raise ValueError(f"path resolves outside the workspace root: {raw}")
    return resolved


@tool
def calculator(expression: str) -> float:
    """Evaluate a simple arithmetic expression such as '2 + 3 * 4'."""
    allowed = set("0123456789+-*/(). ")
    if any(c not in allowed for c in expression):
        raise ValueError("Expression contains unsupported characters.")
    result = eval(expression, {"__builtins__": {}}, {})  # noqa: S307
    return float(result)


@tool
def create_dir(path: str) -> str:
    """Create a directory (and any missing parents) at the given absolute or relative path."""
    try:
        target = resolve_project_path(path)
        os.makedirs(target, exist_ok=True)
        return f"created directory {target}"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: could not create directory {path}: {exc}"


@tool
def create_file(path: str, content: str) -> str:
    """Create or overwrite a text file at the given path with the given content."""
    try:
        target = resolve_project_path(path)
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
        target = resolve_project_path(path)
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
        src = resolve_project_path(path)
        dst = resolve_project_path(new_path)
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {exc}"
    try:
        os.rename(src, dst)
        return f"renamed {src} -> {dst}"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: could not rename {path}: {exc}"


@tool
def delete_file(path: str) -> str:
    """Delete a file. Auto-runs when previously exempted; otherwise requires user confirmation before the file is removed."""
    try:
        target = resolve_project_path(path)
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {exc}"
    if consume_exemption("delete_file", target):
        try:
            os.remove(target)
            return f"deleted file {target}"
        except FileNotFoundError:
            return "ERROR: file not found"
        except Exception as exc:  # noqa: BLE001
            return f"ERROR: could not delete {path}: {exc}"
    decision = _await_approval({
        "kind": "delete_file",
        "description": f"Delete file `{target}`?",
        "path": target,
        "command": None,
    })
    if not decision.get("approved"):
        return "User rejected this action. Do not retry it; inform the user."
    if decision.get("allow") == "always":
        grant_path_exemption("delete_file", target, "always")
    try:
        os.remove(target)
        return f"deleted file {target}"
    except FileNotFoundError:
        return "ERROR: file not found"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: could not delete {path}: {exc}"


@tool
def delete_folder(path: str) -> str:
    """Delete a folder and everything inside it. Auto-runs when previously exempted; otherwise requires user confirmation before deletion."""
    try:
        target = resolve_project_path(path)
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {exc}"
    if consume_exemption("delete_folder", target):
        try:
            shutil.rmtree(target)
            return f"deleted folder {target}"
        except FileNotFoundError:
            return "ERROR: folder not found"
        except Exception as exc:  # noqa: BLE001
            return f"ERROR: could not delete {path}: {exc}"
    decision = _await_approval({
        "kind": "delete_folder",
        "description": f"Delete folder `{target}` recursively?",
        "path": target,
        "command": None,
    })
    if not decision.get("approved"):
        return "User rejected this action. Do not retry it; inform the user."
    if decision.get("allow") == "always":
        grant_path_exemption("delete_folder", target, "always")
    try:
        shutil.rmtree(target)
        return f"deleted folder {target}"
    except FileNotFoundError:
        return "ERROR: folder not found"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: could not delete {path}: {exc}"


@tool
def read_file(path: str, start_line: int = 1, max_lines: int = 0) -> str:
    """Read a text file inside the workspace, optionally from `start_line` for `max_lines` lines (0 = up to the configured limit). Output is capped by byte and line limits."""
    try:
        target = resolve_project_path(path)
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {exc}"
    if not os.path.isfile(target):
        return f"ERROR: not a file: {target}"
    limit_lines = max_lines if max_lines > 0 else READ_MAX_LINES
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            data = f.read(READ_MAX_BYTES + 1)
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: could not read {path}: {exc}"
    truncated = False
    if len(data) > READ_MAX_BYTES:
        data = data[:READ_MAX_BYTES]
        truncated = True
    all_lines = data.splitlines()
    total = len(all_lines)
    start = max(1, start_line) - 1
    window = all_lines[start : start + limit_lines]
    if start + limit_lines < total:
        truncated = True
    header = f"{target} ({total} lines shown from {start + 1})"
    body = "\n".join(window)
    if truncated:
        body += "\n... [truncated]"
    return f"{header}\n{body}"


@tool
def list_files(path: str = ".", pattern: str = "") -> str:
    """List files and directories at `path` inside the workspace. Optional `pattern` filters names by glob (e.g. '*.py'). Directories are shown with a trailing '/'."""
    try:
        target = resolve_project_path(path)
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {exc}"
    if os.path.isfile(target):
        return f"{os.path.relpath(target, ws_mod.get_current().root_path)}"
    if not os.path.isdir(target):
        return f"ERROR: not a directory: {target}"
    try:
        names = sorted(os.listdir(target))
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: could not list {path}: {exc}"
    if pattern:
        names = [n for n in names if fnmatch.fnmatch(n, pattern)]
    entries = []
    for name in names[:LIST_MAX_ENTRIES]:
        full = os.path.join(target, name)
        entries.append(f"{name}/" if os.path.isdir(full) else name)
    if len(names) > LIST_MAX_ENTRIES:
        entries.append(f"... [{len(names) - LIST_MAX_ENTRIES} more]")
    return "\n".join(entries) if entries else "(empty)"


@tool
def search_code(query: str, path: str = ".", pattern: str = "") -> str:
    """Search file contents under `path` for `query` (case-insensitive substring). Optional `pattern` restricts files by glob (e.g. '*.py'). Returns 'file:line: text' matches, capped by the configured limit."""
    if not query:
        return "ERROR: empty query"
    try:
        base = resolve_project_path(path)
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {exc}"
    root = ws_mod.get_current().root_path
    results: list[str] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
        for name in filenames:
            if pattern and not fnmatch.fnmatch(name, pattern):
                continue
            full = os.path.join(dirpath, name)
            try:
                if os.path.getsize(full) > READ_MAX_BYTES:
                    continue
                with open(full, "r", encoding="utf-8") as f:
                    for lineno, line in enumerate(f, 1):
                        if query.lower() in line.lower():
                            rel = os.path.relpath(full, root)
                            results.append(f"{rel}:{lineno}: {line.rstrip()}")
                            if len(results) >= SEARCH_MAX_RESULTS:
                                results.append(f"... [capped at {SEARCH_MAX_RESULTS}]")
                                return "\n".join(results)
            except (UnicodeDecodeError, OSError):
                continue
    return "\n".join(results) if results else "(no matches)"


@tool
def get_project_structure(path: str = ".", max_depth: int = 0) -> str:
    """Return an indented tree of the workspace (or `path` within it), skipping ignored directories. Depth defaults to the configured limit."""
    try:
        base = resolve_project_path(path)
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {exc}"
    root = ws_mod.get_current().root_path
    depth_limit = max_depth if max_depth > 0 else STRUCTURE_MAX_DEPTH
    base_depth = len(os.path.relpath(base, root).split(os.sep)) if base != root else 0
    lines: list[str] = [os.path.relpath(base, root) or "."]
    count = 0
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS)
        depth = len(os.path.relpath(dirpath, base).split(os.sep)) if dirpath != base else 0
        if depth >= depth_limit:
            dirnames[:] = []
        indent = "  " * depth
        for name in dirnames:
            lines.append(f"{indent}{name}/")
            count += 1
        for name in sorted(filenames):
            lines.append(f"{indent}{name}")
            count += 1
        if count >= STRUCTURE_MAX_ENTRIES:
            lines.append(f"... [capped at {STRUCTURE_MAX_ENTRIES} entries]")
            break
    return "\n".join(lines)


@tool
def run_shell_command(command: str) -> str:
    """Run a shell command in the active workspace root. Read-only commands run immediately; anything else requires explicit user approval."""
    cwd = ws_mod.get_current().root_path
    if not classify_command(command):
        decision = _await_approval({
            "kind": "shell",
            "description": f"Run shell command `{command}`?",
            "command": command,
            "path": None,
        })
        if not decision.get("approved"):
            return "User rejected this command. Do not retry it; inform the user."
        if decision.get("allow") == "always":
            grant_exception(command, "always")
    try:
        code, out = run_shell(command, cwd, timeout=SHELL_TIMEOUT)
        return f"exit {code}\n{out}"
    except TimeoutError:
        return "ERROR: command timed out"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {exc}"


TOOLS = [
    calculator,
    list_files,
    read_file,
    search_code,
    get_project_structure,
    create_dir,
    create_file,
    edit_file,
    rename_file,
    delete_file,
    delete_folder,
    run_shell_command,
]