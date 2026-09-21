"""Agent tools: calculator, filesystem operations, and shell execution.

File paths supplied by the model are resolved against PROJECT_ROOT (POSIX-style
root paths count as project-root relative) and paths escaping the root are
rejected. Destructive operations are auto-run when an exemption exists, and
otherwise register a pending approval instead of running.
"""

import os
import shutil

from langchain_core.tools import tool

from .approvals import _pending_approval, consume_exemption
from .config import PROJECT_ROOT, SHELL_TIMEOUT
from .shell import classify_command, run_shell


def resolve_project_path(raw: str) -> str:
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
    approval_id = _pending_approval(
        "delete_file", {"path": target}, f"Delete file `{target}`?"
    )
    return f"ACTION_REQUIRES_APPROVAL:{approval_id}"


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
        code, out = run_shell(command, PROJECT_ROOT, timeout=SHELL_TIMEOUT)
        return f"exit {code}\n{out}"
    except TimeoutError:
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