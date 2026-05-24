from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from ui.models import LogLine, LogManagerStatus


class LogsPanel(Static):
    def update_logs(
        self,
        logs: list[LogLine],
        *,
        filter_text: str = "",
        log_manager: LogManagerStatus | None = None,
    ) -> None:
        text = Text()
        title = "Realtime Logs"
        if filter_text:
            title += f" filter={filter_text}"
        text.append(title + "\n", style="bold")
        if log_manager is not None:
            text.append(
                (
                    f"Log I/E: {log_manager.progress or 'idle'}"
                    f"  archive={_size(log_manager.archive_size)}"
                    f"  integrity={log_manager.integrity_status or 'unknown'}"
                    f"  last={log_manager.last_backup_time or '-'}"
                )
                + "\n",
                style=_integrity_style(log_manager.integrity_status),
            )
        for line in logs[-80:]:
            prefix = " ".join(part for part in [line.timestamp, line.level, line.source] if part)
            text.append(prefix[:80].ljust(80), style=_level_style(line.level))
            text.append(" ")
            text.append(line.message[:220].replace("\n", " "))
            text.append("\n")
        self.update(text)


def _level_style(level: str) -> str:
    if level == "ERROR":
        return "bold red"
    if level == "WARNING":
        return "yellow"
    return "dim"


def _integrity_style(status: str) -> str:
    if status == "failed":
        return "bold red"
    if status == "ok":
        return "green"
    return "dim"


def _size(value: int) -> str:
    size = float(value or 0)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024 or unit == "GB":
            return f"{size:.1f}{unit}" if unit != "B" else f"{int(size)}B"
        size /= 1024
    return f"{size:.1f}GB"
