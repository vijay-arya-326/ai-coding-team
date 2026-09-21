"""Pending-approval management for destructive or unsafe agent actions.

Approvals are stored in memory with a time-to-live. Permanent command exemptions
are persisted to a JSON allowlist; one-time exemptions live in memory only.
"""

import json
import logging
import os
import shutil
import subprocess
import time as _time

from .config import ALLOWED_COMMANDS_FILE
from .shell import run_shell

logger = logging.getLogger("app.agent")

# Seconds before an unapproved action expires.
APPROVAL_TTL = int(os.getenv("APPROVAL_TTL", "600"))

PENDING_APPROVALS: dict[str, dict] = {}
_approval_counter = 0


def _cleanup_expired() -> None:
    cutoff = _time.time() - APPROVAL_TTL
    for approval_id, entry in list(PENDING_APPROVALS.items()):
        if entry.get("ts", 0) < cutoff:
            del PENDING_APPROVALS[approval_id]


def _pending_approval(kind: str, params: dict, description: str) -> str:
    global _approval_counter
    _cleanup_expired()
    _approval_counter += 1
    approval_id = f"appr_{_approval_counter}"
    PENDING_APPROVALS[approval_id] = {
        "kind": kind,
        "params": params,
        "description": description,
        "ts": _time.time(),
    }
    return approval_id


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


def grant_exception(command: str, allow: str | None) -> bool:
    """Add a command exemption. 'always' persists it, 'once' allows a single use."""
    if not command or allow not in ("once", "always"):
        return False
    from .shell import normalize_command

    cmd = normalize_command(command)
    if allow == "always":
        PERMANENT_ALLOWED.add(cmd)
        _save_permanent_allowed()
        return True
    ONE_TIME_ALLOWED.add(cmd)
    return True


def _exempt_key(kind: str, path: str) -> str:
    """Canonical key for a destructive filesystem action, e.g. 'delete_file:<abs path>'."""
    return f"{kind}:{os.path.normcase(os.path.abspath(path))}"


def grant_path_exemption(kind: str, path: str, allow: str | None) -> bool:
    """Grant a path-based exemption ('always' persists, 'once' single-use)."""
    if allow not in ("once", "always"):
        return False
    key = _exempt_key(kind, path)
    if allow == "always":
        PERMANENT_ALLOWED.add(key)
        _save_permanent_allowed()
    else:
        ONE_TIME_ALLOWED.add(key)
    return True


def consume_exemption(kind: str, path: str) -> bool:
    """Check for (and consume) a path exemption for a destructive action."""
    key = _exempt_key(kind, path)
    if key in PERMANENT_ALLOWED:
        return True
    if key in ONE_TIME_ALLOWED:
        ONE_TIME_ALLOWED.discard(key)
        return True
    return False


def resolve_approval(approval_id: str, approved: bool, allow: str | None = None) -> dict:
    """Execute or reject a previously requested approval.

    allow may be 'once' or 'always' to grant the same command an exemption from
    future approval prompts (persisted for 'always').
    """
    from .config import PROJECT_ROOT

    _cleanup_expired()
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
            granted = grant_path_exemption(kind, params["path"], allow)
        elif kind == "delete_folder":
            shutil.rmtree(params["path"])
            result["result"] = f"deleted folder {params['path']}"
            granted = grant_path_exemption(kind, params["path"], allow)
        elif kind == "shell":
            code, out = run_shell(params["command"], params.get("cwd") or PROJECT_ROOT)
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