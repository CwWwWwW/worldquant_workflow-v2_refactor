from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator


LOG_RE = re.compile(
    r"^(?P<time>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})\s+"
    r"\[(?P<level>[A-Z]+)\]\s+(?P<message>.*)$"
)


def parse_log_line(text: str) -> dict[str, str]:
    match = LOG_RE.match(text.strip())
    if not match:
        return {
            "timestamp": "",
            "level": "INFO",
            "message": text.strip(),
            "source": source_for_message(text),
        }
    message = match.group("message")
    return {
        "timestamp": match.group("time"),
        "level": match.group("level"),
        "message": message,
        "source": source_for_message(message),
    }


def iter_log_lines(path: Path) -> Iterator[tuple[int, str, dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", errors="replace") as fh:
        for line_no, raw_line in enumerate(fh, start=1):
            yield line_no, raw_line, parse_log_line(raw_line)


def source_for_message(message: str) -> str:
    value = (message or "").lower()
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
