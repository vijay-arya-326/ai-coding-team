"""Shell command classification and execution for agent tools.

Safe (read-only) commands run immediately; anything containing an unsafe marker
or an unknown command requires approval. On Windows a few POSIX-style commands
are translated to their cmd.exe equivalents.
"""

import os
import subprocess

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

    A safe whitelist match is not enough: a command that also contains an unsafe
    marker falls through to the exemption check, then to the marker check and is
    rejected unless explicitly granted. Granted exemptions (permanent or one-time)
    bypass everything; the one-time exemption is consumed after a single use.
    """
    from .approvals import ONE_TIME_ALLOWED, PERMANENT_ALLOWED

    cmd = normalize_command(command)
    if not cmd:
        return False
    for prefix in SAFE_COMMANDS:
        if cmd == prefix or cmd.startswith(prefix + " "):
            if not any(marker in cmd for marker in UNSAFE_MARKERS):
                return True
            break
    if cmd in PERMANENT_ALLOWED:
        return True
    if cmd in ONE_TIME_ALLOWED:
        ONE_TIME_ALLOWED.discard(cmd)
        return True
    for marker in UNSAFE_MARKERS:
        if marker in cmd:
            return False
    return False


def run_shell(command: str, cwd: str, timeout: int = 90) -> tuple[int, str]:
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