from __future__ import annotations

from rich.table import Table
from textual.widgets import Static

from ui.models import WorkerState


class WorkerPanel(Static):
    def update_workers(self, workers: list[WorkerState]) -> None:
        table = Table(title="Browser Workers", expand=True)
        table.add_column("ID", no_wrap=True)
        table.add_column("Health", no_wrap=True)
        table.add_column("Task", no_wrap=True)
        table.add_column("Runtime", no_wrap=True)
        table.add_column("Restarts", justify="right", no_wrap=True)
        table.add_column("Current Alpha")
        if not workers:
            table.add_row("-", "IDLE", "-", "-", "0", "-", style="dim")
        for worker in workers:
            style = _health_style(worker.health)
            table.add_row(
                worker.worker_id,
                worker.health,
                worker.current_task,
                _duration(worker.runtime_seconds),
                str(worker.restart_count),
                worker.current_alpha or worker.alpha_id,
                style=style,
            )
        self.update(table)


def _health_style(health: str) -> str:
    if health in {"FATAL", "STALLED"}:
        return "bold red"
    if health == "RESTARTING":
        return "yellow"
    if health == "RUNNING":
        return "green"
    return "dim"


def _duration(seconds: float) -> str:
    seconds = int(seconds or 0)
    minutes, sec = divmod(seconds, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{sec:02d}s"
    return f"{sec}s"

