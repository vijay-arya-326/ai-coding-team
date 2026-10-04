"""Shell command classification and execution for agent tools.

Safe (read-only) commands run immediately; anything containing an unsafe marker
or an unknown command requires approval. On Windows a few POSIX-style commands
are translated to their cmd.exe equivalents.
"""

import os
import subprocess
import time

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
    ">", "|", ";", "&&", "||", "$(", "&", "^",
)


def normalize_command(command: str) -> str:
    """Trim whitespace and lower-case a command for classification."""
    return " ".join(command.split()).lower()


def classify_command(command: str) -> bool:
    """Return True when the command may run without approval.

    The safe whitelist (built-in + the active workspace's extra safe commands)
    still defers to any unsafe marker present. Granted exemptions (permanent or
    one-time) bypass everything; a one-time exemption is consumed after use.
    """
    from .approvals import current_policy

    policy = current_policy()
    cmd = normalize_command(command)
    if not cmd:
        return False
    for prefix in policy.safe:
        if cmd == prefix or cmd.startswith(prefix + " "):
            if not any(marker in cmd for marker in policy.unsafe):
                return True
            break
    if cmd in policy.permanent:
        return True
    if cmd in policy.one_time:
        policy.one_time.discard(cmd)
        return True
    for marker in policy.unsafe:
        if marker in cmd:
            return False
    return False


def split_compound(command: str) -> list[str]:
    """Split a command on top-level `&&`, `||`, `;` and newlines.

    Quote-aware, so separators inside quotes stay part of the segment. Pipes
    (`|`) are never split — a pipe must stay one shell pipeline.
    """
    parts: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    i = 0
    n = len(command)
    while i < n:
        ch = command[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            buf.append(ch)
            buf.append(command[i + 1])
            i += 2
            continue
        if ch in (";", "\n"):
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        if ch in ("&", "|") and i + 1 < n and command[i + 1] == ch:
            parts.append("".join(buf))
            buf = []
            i += 2
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def _exec_segment(command: str, cwd: str, timeout: float) -> tuple[int, str]:
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


def run_shell(command: str, cwd: str, timeout: int = 90) -> tuple[int, str]:
    segments = split_compound(command) or [command.strip()]
    if len(segments) == 1:
        return _exec_segment(segments[0], cwd, timeout)
    deadline = time.monotonic() + timeout
    blocks: list[str] = []
    first_error = 0
    for seg in segments:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            blocks.append(f"$ {seg}\nERROR: skipped (overall timeout exceeded)")
            first_error = first_error or 124
            continue
        try:
            code, out = _exec_segment(seg, cwd, remaining)
        except subprocess.TimeoutExpired:
            blocks.append(f"$ {seg}\nERROR: timed out")
            first_error = first_error or 124
            continue
        blocks.append(f"$ {seg}\n{out}" if out else f"$ {seg}")
        if code and not first_error:
            first_error = code
    return first_error, "\n\n".join(blocks)