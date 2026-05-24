from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from ui.models import WorkflowStatus


class StatusBar(Static):
    def update_status(self, status: WorkflowStatus) -> None:
        text = Text()
        text.append(f"STATUS: {status.status}", style=_status_style(status.status))
        text.append(f"   Population: {status.population_count}")
        text.append(f"   Queue: {status.queue_size}")
        text.append(f"   Pass Rate: {status.pass_rate * 100:.1f}%")
        text.append(f"   Reward Mode: {status.reward_mode}")
        text.append(f"   Migration: {status.migration_state}")
        text.append(f"   Runtime: {_duration(status.runtime_seconds)}")
        text.append(f"   Last Success: {status.last_success_time or '-'}")
        self.update(text)


def _status_style(status: str) -> str:
    if status in {"ERROR", "STALLED"}:
        return "bold red"
    if status == "RUNNING":
        return "bold green"
    return "bold yellow"


def _duration(seconds: float) -> str:
    seconds = int(seconds or 0)
    hours, rem = divmod(seconds, 3600)
    minutes, sec = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{sec:02d}s"
    return f"{sec}s"

