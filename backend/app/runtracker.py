"""Per-thread stop signals and per-chat run capture for the SSE stream."""

import asyncio
import json
from typing import Any

from .config import PREVIEW_LIMIT, TOOL_TRUNCATION
from .persistence import _now


class RunRegistry:
    """Tracks active chat responses per thread so a caller can stop them."""

    def __init__(self) -> None:
        self._active: dict[str, asyncio.Event] = {}

    def stop_event(self, thread_id: str) -> asyncio.Event:
        return self._active.setdefault(thread_id, asyncio.Event())

    def is_active(self, thread_id: str) -> bool:
        return thread_id in self._active

    def request_stop(self, thread_id: str) -> bool:
        event = self._active.get(thread_id)
        if event is None:
            return False
        event.set()
        return True

    def clear(self, thread_id: str) -> None:
        self._active.pop(thread_id, None)


class RunTracker:
    """Accumulates one chat call's model rounds (tokens + tool communication).

    Tracks the same data langgraph events describe: a run begins on
    on_chat_model_start, collects streamed text and usage, and ends on
    on_chat_model_end. Tool calls attach to the current (or previous) run.
    """

    def __init__(self, first_input: str) -> None:
        self.preview_limit = PREVIEW_LIMIT
        self.truncation = TOOL_TRUNCATION
        self.runs: list[dict[str, Any]] = []
        self._current: dict[str, Any] | None = None
        self._first_input = first_input

    @property
    def current(self) -> dict[str, Any] | None:
        return self._current

    def _tool_holder(self) -> dict[str, Any] | None:
        return self._current if self._current is not None else (self.runs[-1] if self.runs else None)

    def _round_input_preview(self) -> str:
        if not self.runs:
            return self._first_input[: self.preview_limit]
        parts = []
        for t in self.runs[-1].get("tools", []):
            parts.append(f"{t['name']}: in={t['input']} out={t['output']}")
        return ("[tool results] " + " | ".join(parts))[: self.preview_limit]

    def start_run(self) -> None:
        if self._current is not None:
            self._current["ended_at"] = _now()
            self.runs.append(self._current)
        self._current = {
            "started_at": _now(),
            "ended_at": None,
            "input_preview": self._round_input_preview(),
            "output_preview": "",
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "tools": [],
        }

    def token(self, text: str) -> None:
        if self._current is not None:
            self._current["output_preview"] += text

    def finish_run(self, usage: dict[str, Any]) -> None:
        if self._current is None:
            return
        self._current["input_tokens"] = usage.get("input_tokens") or usage.get("prompt_tokens")
        self._current["output_tokens"] = usage.get("output_tokens") or usage.get("completion_tokens")
        if self._current["input_tokens"] is not None and self._current["output_tokens"] is not None:
            self._current["total_tokens"] = usage.get("total_tokens") or (
                self._current["input_tokens"] + self._current["output_tokens"]
            )
        else:
            self._current["total_tokens"] = usage.get("total_tokens")
        self._current["ended_at"] = _now()
        self.runs.append(self._current)
        self._current = None

    def attach_tool_start(self, name: str | None, args: Any) -> None:
        target = self._tool_holder()
        if target is None:
            return
        tools = target.setdefault("tools", [])
        if tools and tools[-1].get("output") is None:
            return
        tools.append({
            "name": name,
            "input": json.dumps(args, default=str)[: self.truncation] if args is not None else None,
            "output": None,
        })

    def attach_tool_end(self, output: Any) -> None:
        scope = self._tool_holder()
        if scope is None:
            return
        for t in reversed(scope.get("tools", [])):
            if t.get("output") is None:
                t["output"] = str(output)[: self.truncation]
                return

    def close(self) -> None:
        if self._current is not None:
            self._current["ended_at"] = _now()
            self.runs.append(self._current)
            self._current = None