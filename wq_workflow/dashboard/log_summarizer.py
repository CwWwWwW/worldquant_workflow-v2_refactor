from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


STATE_NAMES = {
    "IDLE",
    "STARTING",
    "GENERATING_TEMPLATE",
    "SUBMITTING_BACKTEST",
    "WAIT_RESULT",
    "PARSE_RESULT",
    "PLATFORM_SC_CHECK",
    "GOVERNANCE_CHECK",
    "STRATEGY_UPDATE",
    "OBSERVABILITY_READY",
    "ERROR_RECOVERABLE",
    "ERROR_FATAL",
    "UNKNOWN",
}


class LogSummarizer:
    def read_tail(self, path: str | Path, max_bytes: int = 200_000) -> str:
        p = Path(path)
        try:
            with p.open("rb") as fh:
                fh.seek(0, os.SEEK_END)
                size = fh.tell()
                fh.seek(max(0, size - max(1, int(max_bytes))))
                return fh.read().decode("utf-8", errors="replace")
        except (FileNotFoundError, OSError, UnicodeError):
            return ""

    def extract_recent_events(self, text: str, limit: int = 20) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for line in (text or "").splitlines():
            event = self.classify_event(line)
            if event:
                events.append(event)
        return events[-max(1, int(limit)) :]

    def extract_error_summaries(self, text: str, limit: int = 5) -> list[dict[str, Any]]:
        errors: list[dict[str, Any]] = []
        for line in (text or "").splitlines():
            lowered = line.lower()
            if "traceback" in lowered or "exception" in lowered or "error" in lowered or "failed" in lowered:
                event = self.classify_event(line) or {"level": "ERROR", "message": self.strip_long_payload(line)}
                event["level"] = event.get("level") or "ERROR"
                errors.append(event)
        return errors[-max(1, int(limit)) :]

    def classify_event(self, line: str) -> dict[str, Any] | None:
        raw = (line or "").strip()
        if not raw:
            return None
        payload = _json_line(raw)
        if payload is not None:
            state = _normalize_state(str(payload.get("state") or payload.get("current_state") or payload.get("event") or ""))
            return {
                "time": str(payload.get("time") or payload.get("timestamp") or payload.get("created_at") or ""),
                "level": _level_from_payload(payload),
                "state": state,
                "alpha_id": _first_text(payload, "alpha_id", "alpha", "current_alpha"),
                "template": _first_text(payload, "template_file", "template", "current_template"),
                "iteration": payload.get("iteration"),
                "source": _first_text(payload, "source", "event") or "log",
                "message": self.strip_long_payload(json.dumps(payload, ensure_ascii=False, default=str)),
            }
        state = _normalize_state(raw)
        alpha = _match_first(raw, r"alpha[_-]?id[=: ]+([A-Za-z0-9_.:-]+)", r"alpha[=: ]+([A-Za-z0-9_.:-]+)")
        template = _match_first(raw, r"template(?:_file)?[=: ]+([^, ]+)")
        timestamp = _match_first(raw, r"^(\d{4}-\d{2}-\d{2}[T ][^ ]+)")
        if state == "UNKNOWN" and not alpha and "error" not in raw.lower() and "failed" not in raw.lower():
            return None
        level = "ERROR" if re.search(r"error|fatal|traceback|exception", raw, re.I) else ("WARNING" if re.search(r"warn|timeout|stale", raw, re.I) else "INFO")
        return {
            "time": timestamp or "",
            "level": level,
            "state": state,
            "alpha_id": alpha,
            "template": template,
            "iteration": _safe_int(_match_first(raw, r"iteration[=: ]+(\d+)")),
            "source": "log",
            "message": self.strip_long_payload(raw),
        }

    def strip_long_payload(self, line: str, max_chars: int = 300) -> str:
        text = re.sub(r"<[^>]{80,}>", "<html omitted>", str(line or ""))
        text = re.sub(r"\{.{300,}\}", "{json omitted}", text)
        text = re.sub(r"Traceback \(most recent call last\):.*", "Traceback omitted", text)
        text = " ".join(text.replace("\r", " ").replace("\n", " ").split())
        if len(text) > max_chars:
            return text[: max(0, max_chars - 3)] + "..."
        return text


def _json_line(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text.lstrip("\ufeff"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _normalize_state(value: str) -> str:
    upper = (value or "").upper()
    for state in STATE_NAMES:
        if state != "UNKNOWN" and state in upper:
            return state
    if "SC" in upper and "CHECK" in upper:
        return "PLATFORM_SC_CHECK"
    if "GENERAT" in upper and "TEMPLATE" in upper:
        return "GENERATING_TEMPLATE"
    if "BACKTEST" in upper or "SIMULATE" in upper:
        return "SUBMITTING_BACKTEST"
    if "FATAL" in upper:
        return "ERROR_FATAL"
    if "ERROR" in upper or "FAIL" in upper:
        return "ERROR_RECOVERABLE"
    return "UNKNOWN"


def _level_from_payload(payload: dict[str, Any]) -> str:
    level = str(payload.get("level") or "").upper()
    if level:
        return level
    event = str(payload.get("event") or payload.get("state") or "").upper()
    if "FATAL" in event or "ERROR" in event:
        return "ERROR"
    if "WARN" in event or "TIMEOUT" in event:
        return "WARNING"
    return "INFO"


def _first_text(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _match_first(text: str, *patterns: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1)
    return None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None
