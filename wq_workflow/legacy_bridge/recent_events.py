from __future__ import annotations

from pathlib import Path
from typing import Any

from wq_workflow import paths

from .schema import RuntimeEvent
from .utils import append_jsonl_direct, read_jsonl_tail_direct, resolve_path, rotate_if_large_direct, summarize_exception, summarize_payload, truncate_text

DEFAULT_RECENT_EVENTS_PATH = "runtime/status/recent_events.jsonl"


class RecentEventWriter:
    def __init__(self, path: str | Path = DEFAULT_RECENT_EVENTS_PATH, *, root: str | Path | None = None, enabled: bool = True, max_bytes: int = 5_242_880) -> None:
        self.root = Path(root or paths.ROOT)
        self.path = resolve_path(self.root, path)
        self.enabled = bool(enabled)
        self.max_bytes = int(max_bytes or 0)

    def append_event(self, event: RuntimeEvent) -> bool:
        if not self.enabled:
            return False
        try:
            return append_jsonl_direct(self.path, event.to_dict(), max_bytes=self.max_bytes)
        except Exception:
            return False

    def append_event_type(self, event_type: str, **kwargs: Any) -> bool:
        event = RuntimeEvent(event_type=event_type, **kwargs)
        return self.append_event(event)

    def append_error(self, error: Exception, state: str | None = None, **kwargs: Any) -> bool:
        include_traceback = bool(kwargs.pop("include_traceback", False))
        return self.append_event_type(
            "RECOVERABLE_ERROR",
            state=state,
            severity="error",
            message=summarize_exception(error, include_traceback=include_traceback),
            raw_payload={"error": summarize_exception(error)},
            **kwargs,
        )

    def rotate_if_needed(self, max_bytes: int | None = None) -> None:
        rotate_if_large_direct(self.path, int(max_bytes or self.max_bytes or 0))


class RecentEventReader:
    def __init__(self, path: str | Path = DEFAULT_RECENT_EVENTS_PATH, *, root: str | Path | None = None) -> None:
        self.root = Path(root or paths.ROOT)
        self.path = resolve_path(self.root, path)
        self.warnings: list[str] = []

    def read_raw_tail(self, limit: int = 50) -> list[dict[str, Any]]:
        self.warnings = []
        return read_jsonl_tail_direct(self.path, limit=limit, warnings=self.warnings)

    def read_tail(self, limit: int = 50) -> list[RuntimeEvent]:
        return [RuntimeEvent.from_dict(row) for row in self.read_raw_tail(limit=limit)]

    def summarize_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        rows = []
        for event in self.read_tail(limit=limit):
            rows.append({
                "time": event.timestamp,
                "timestamp": event.timestamp,
                "level": event.severity,
                "severity": event.severity,
                "event": event.event_type,
                "event_type": event.event_type,
                "state": event.state,
                "alpha_id": event.alpha_id,
                "iteration": event.iteration,
                "template": event.template_name,
                "message": truncate_text(event.message, 160),
            })
        return rows
