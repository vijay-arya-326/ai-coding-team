"""Pending-approval management for destructive or unsafe agent actions.

Approvals are stored in memory with a time-to-live. Permanent exemptions are
persisted per workspace (the default workspace still uses the legacy
``allowed_commands.json``) ; one-time exemptions live in memory only. Policy
(safe/unsafe command sets) is derived per workspace from its
``.local_agent_workspace`` config plus the built-in shell defaults.
"""

import json
import logging
import os
import shutil
import subprocess
import time as _time
from dataclasses import dataclass

from . import workspace as ws_mod
from .config import ALLOWED_COMMANDS_FILE
from .shell import SAFE_COMMANDS, UNSAFE_MARKERS, run_shell

logger = logging.getLogger("app.agent")

# Seconds before an unapproved action expires.
APPROVAL_TTL = int(os.getenv("APPROVAL_TTL", "600"))

PENDING_APPROVALS: dict[str, dict] = {}
_approval_counter = 0

# Per-workspace policy cache; one-time exemptions survive between calls.
POLICIES: dict[str, "Policy"] = {}


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
    ws = ws_mod.get_current()
    PENDING_APPROVALS[approval_id] = {
        "kind": kind,
        "params": params,
        "description": description,
        "ts": _time.time(),
        "workspace_id": ws.id,
        "workspace": {
            "id": ws.id,
            "root_path": ws.root_path,
            "is_default": ws.is_default,
            "config": dict(ws.config or {}),
        },
    }
    return approval_id


@dataclass
class Policy:
    """Per-workspace command policy: exemptions plus safe/unsafe prefixes."""

    ws_key: str
    config_file: str
    mtime: float | None
    permanent: set[str]
    one_time: set[str]
    safe: tuple[str, ...]
    unsafe: tuple[str, ...]

    def save(self) -> None:
        if self.ws_key == ws_mod.default_workspace().id:
            with open(ALLOWED_COMMANDS_FILE, "w", encoding="utf-8") as f:
                json.dump({"allowed": sorted(self.permanent)}, f, indent=2)
            return
        ws = ws_mod.get_current()
        cfg = dict(ws.config or {})
        cfg["allowed_commands"] = [
            s for s in sorted(self.permanent) if not _is_path_exemption(s)
        ]
        cfg["exemptions"] = [
            s for s in sorted(self.permanent) if _is_path_exemption(s)
        ]
        ws_mod.save_workspace_config(ws.root_path, cfg)


def _is_path_exemption(value: str) -> bool:
    kind, sep, _rest = value.partition(":")
    return bool(sep) and kind in ("delete_file", "delete_folder", "shell")


def _file_mtime(path: str) -> float | None:
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _read_file_list(path: str) -> set[str]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(c).strip() for c in data.get("allowed", []) if str(c).strip()}
        return set()
    except (OSError, ValueError):
        return set()


def policy_for(ws: ws_mod.Workspace | None = None) -> Policy:
    ws = ws or ws_mod.get_current()
    config_file = ws.config_file
    mtime = _file_mtime(config_file)
    cached = POLICIES.get(ws.id)
    if cached is not None and cached.config_file == config_file and cached.mtime == mtime:
        return cached

    cfg = ws.config or ws_mod.load_workspace_config(ws.root_path)
    if not cfg:
        cfg = {}
    extra_safe = [str(c).strip() for c in cfg.get("safe_commands", []) if str(c).strip()]
    extra_unsafe = [str(c).strip() for c in cfg.get("unsafe_commands", []) if str(c).strip()]
    safe = tuple(dict.fromkeys((*SAFE_COMMANDS, *extra_safe)))
    unsafe = tuple(dict.fromkeys((*UNSAFE_MARKERS, *extra_unsafe)))

    if ws.is_default:
        permanent = _read_file_list(ALLOWED_COMMANDS_FILE)
        merged = {
            str(c).strip()
            for c in (cfg.get("allowed_commands", []) + cfg.get("exemptions", []))
            if str(c).strip()
        }
        permanent |= merged
    else:
        permanent = {
            str(c).strip()
            for c in (cfg.get("allowed_commands", []) + cfg.get("exemptions", []))
            if str(c).strip()
        }

    policy = Policy(
        ws_key=ws.id,
        config_file=config_file,
        mtime=mtime,
        permanent=permanent,
        one_time=set(),
        safe=safe,
        unsafe=unsafe,
    )
    POLICIES[ws.id] = policy
    return policy


# Backward-compatible aliases used by the facade and older callers; they mirror
# the *current* workspace's policy.
PERMANENT_ALLOWED: set[str] = set()
ONE_TIME_ALLOWED: set[str] = set()


def _sync_legacy_aliases(policy: Policy) -> None:
    PERMANENT_ALLOWED.clear()
    PERMANENT_ALLOWED.update(policy.permanent)
    ONE_TIME_ALLOWED.clear()
    ONE_TIME_ALLOWED.update(policy.one_time)


def current_policy() -> Policy:
    policy = policy_for()
    _sync_legacy_aliases(policy)
    return policy


def grant_exception(command: str, allow: str | None, ws: ws_mod.Workspace | None = None) -> bool:
    """Add a command exemption for the (given/current) workspace. 'always' persists it."""
    if not command or allow not in ("once", "always"):
        return False
    from .shell import normalize_command

    policy = policy_for(ws)
    cmd = normalize_command(command)
    if allow == "always":
        policy.permanent.add(cmd)
        policy.save()
        ONE_TIME_ALLOWED.discard(cmd)
        return True
    policy.one_time.add(cmd)
    PERMANENT_ALLOWED.discard(cmd)
    return True


def _exempt_key(kind: str, path: str) -> str:
    """Canonical key for a destructive filesystem action, e.g. 'delete_file:<abs path>'."""
    return f"{kind}:{os.path.normcase(os.path.abspath(path))}"


def grant_path_exemption(
    kind: str, path: str, allow: str | None, ws: ws_mod.Workspace | None = None
) -> bool:
    """Grant a path-based exemption for the (given/current) workspace."""
    if allow not in ("once", "always"):
        return False
    policy = policy_for(ws)
    key = _exempt_key(kind, path)
    if allow == "always":
        policy.permanent.add(key)
        policy.save()
    else:
        policy.one_time.add(key)
    return True


def consume_exemption(kind: str, path: str, ws: ws_mod.Workspace | None = None) -> bool:
    """Check for (and consume) a path exemption for a destructive action."""
    policy = policy_for(ws)
    key = _exempt_key(kind, path)
    if key in policy.permanent:
        return True
    if key in policy.one_time:
        policy.one_time.discard(key)
        return True
    return False


def resolve_approval(approval_id: str, approved: bool, allow: str | None = None) -> dict:
    """Execute or reject a previously requested approval.

    allow may be 'once' or 'always' to grant the same command an exemption from
    future approval prompts (persisted for 'always'). Exemptions are scoped to
    the workspace that issued the approval.
    """
    _cleanup_expired()
    entry = PENDING_APPROVALS.pop(approval_id, None)
    if entry is None:
        return {"status": "not_found", "approval_id": approval_id}
    if not approved:
        return {"status": "rejected", "approval_id": approval_id, "kind": entry["kind"]}

    stored = entry.get("workspace")
    if stored:
        ws = ws_mod.Workspace(
            id=stored.get("id") or ws_mod.DEFAULT_WORKSPACE_ID,
            name="",
            root_path=stored.get("root_path") or ws_mod.PROJECT_ROOT,
            config=dict(stored.get("config") or {}),
            is_default=bool(stored.get("is_default")),
        )
    else:
        ws = ws_mod.get_current()

    kind, params = entry["kind"], entry["params"]
    result: dict = {"status": "approved", "kind": kind, "approval_id": approval_id}
    granted = False
    try:
        if kind == "delete_file":
            os.remove(params["path"])
            result["result"] = f"deleted file {params['path']}"
            granted = grant_path_exemption(kind, params["path"], allow, ws)
        elif kind == "delete_folder":
            shutil.rmtree(params["path"])
            result["result"] = f"deleted folder {params['path']}"
            granted = grant_path_exemption(kind, params["path"], allow, ws)
        elif kind == "shell":
            cwd = params.get("cwd") or ws.root_path
            code, out = run_shell(params["command"], cwd)
            result["exit_code"] = code
            result["output"] = out
            if allow in ("once", "always"):
                granted = grant_exception(params["command"], allow, ws)
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