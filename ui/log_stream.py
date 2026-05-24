from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any

from wq_workflow.paths import (
    ITERATION_LOG_FILE,
    MIGRATION_LOG_DIR,
    REWARD_SHADOW_LOG_DIR,
    STATE_LOG_FILE,
    WORKFLOW_LOG_FILE,
)

from .models import LogLine


DEFAULT_LOG_PATHS = [
    WORKFLOW_LOG_FILE,
    STATE_LOG_FILE,
    REWARD_SHADOW_LOG_DIR / "reward_shadow.jsonl",
    MIGRATION_LOG_DIR / "migration_events.jsonl",
    ITERATION_LOG_FILE,
]


class LogStreamer:
    def __init__(self, paths: list[Path] | None = None, *, max_lines: int = 300) -> None:
        self.paths = paths or list(DEFAULT_LOG_PATHS)
        self.max_lines = max_lines
        self.offsets: dict[str, int] = {}
        self.buffer: list[LogLine] = []

    def poll(self, *, filter_text: str = "") -> list[LogLine]:
        for path in self.paths:
            self._poll_path(path)
        if filter_text:
            needle = filter_text.lower()
            return [line for line in self.buffer if needle in line.message.lower() or needle in line.source.lower()]
        return list(self.buffer)

    def _poll_path(self, path: Path) -> None:
        key = str(path)
        try:
            size = path.stat().st_size
        except OSError:
            self.offsets[key] = 0
            return
        offset = self.offsets.get(key)
        if offset is None:
            offset = max(0, size - 64_000)
        if size < offset:
            offset = 0
        try:
            with path.open("rb") as fh:
                fh.seek(offset)
                data = fh.read()
                self.offsets[key] = fh.tell()
        except OSError:
            return
        text = data.decode("utf-8", errors="ignore")
        for raw_line in text.splitlines():
            line = self._parse_line(path, raw_line)
            if line:
                self.buffer.append(line)
        if len(self.buffer) > self.max_lines:
            self.buffer = self.buffer[-self.max_lines :]

    def _parse_line(self, path: Path, raw_line: str) -> LogLine | None:
        text = raw_line.strip()
        if not text:
            return None
        name = path.name.lower()
        if name.endswith(".jsonl"):
            parsed = _json_line(text)
            if parsed:
                return _log_from_json(path, parsed)
        if name == "iteration_log.csv":
            return _log_from_csv_line(path, text)
        return _log_from_plain(path, text)


def read_recent_logs(paths: list[Path] | None = None, *, max_lines: int = 200, filter_text: str = "") -> list[LogLine]:
    streamer = LogStreamer(paths, max_lines=max_lines)
    for path in streamer.paths:
        streamer.offsets[str(path)] = 0
    return streamer.poll(filter_text=filter_text)[-max_lines:]


def _json_line(text: str) -> dict[str, Any] | None:
    try:
        text = text.lstrip("\ufeff")
        value = json.loads(text)
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _log_from_json(path: Path, payload: dict[str, Any]) -> LogLine:
    timestamp = str(payload.get("time") or payload.get("timestamp") or "")
    level = "INFO"
    source = _source_for_payload(path, payload)
    if payload.get("event") in {"STATE_FATAL", "STATE_TIMEOUT"} or payload.get("action") == "rollback":
        level = "ERROR" if payload.get("event") == "STATE_FATAL" else "WARNING"
    message = json.dumps(payload, ensure_ascii=False, default=str)
    return LogLine(timestamp=timestamp, level=level, source=source, message=message, path=str(path))


def _log_from_csv_line(path: Path, text: str) -> LogLine | None:
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error:
        rows = []
    if not rows or not rows[0]:
        return None
    cells = rows[0]
    if cells and cells[0].lower() == "time":
        return None
    timestamp = cells[0] if cells else ""
    stage = cells[4] if len(cells) > 4 else ""
    alpha = cells[2] if len(cells) > 2 else ""
    level = "WARNING" if "fail" in stage.lower() or "error" in stage.lower() else "INFO"
    source = _source_for_message(stage)
    return LogLine(timestamp=timestamp, level=level, source=source, message=f"{stage} {alpha}".strip(), path=str(path))


def _log_from_plain(path: Path, text: str) -> LogLine:
    match = re.match(r"^(?P<time>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})\s+\[(?P<level>[A-Z]+)\]\s+(?P<msg>.*)$", text)
    if match:
        message = match.group("msg")
        return LogLine(
            timestamp=match.group("time"),
            level=match.group("level"),
            source=_source_for_message(message),
            message=message,
            path=str(path),
        )
    return LogLine(timestamp="", level="INFO", source=_source_for_message(text), message=text, path=str(path))


def _source_for_payload(path: Path, payload: dict[str, Any]) -> str:
    path_text = str(path).lower()
    event = str(payload.get("event") or "").lower()
    if "migration" in path_text or payload.get("action") in {"rollback", "transition", "blend"}:
        return "migration"
    if "reward" in path_text or "legacy_reward" in payload or "v2_reward" in payload:
        return "reward"
    if "browser" in event or str(payload.get("state") or "").upper() == "BROWSER_WATCHDOG":
        return "browser"
    if "workflow_state" in path_text:
        return "simulate"
    return "workflow"


def _source_for_message(message: str) -> str:
    value = message.lower()
    if "migration" in value or "rollback" in value:
        return "migration"
    if "reward" in value or "shadow" in value:
        return "reward"
    if "browser" in value or "chromium" in value or "playwright" in value:
        return "browser"
    if "repair" in value or "deepseek" in value:
        return "repair"
    if "simulate" in value or "backtest" in value or "fsm" in value:
        return "simulate"
    return "workflow"
