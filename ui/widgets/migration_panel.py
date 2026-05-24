from __future__ import annotations

from rich.table import Table
from textual.widgets import Static

from ui.models import MigrationMetrics


class MigrationPanel(Static):
    def update_migration(self, metrics: MigrationMetrics) -> None:
        table = Table(title="Migration", expand=True)
        table.add_column("Metric")
        table.add_column("Value", justify="right")
        table.add_row("State", metrics.state, style=_state_style(metrics.state))
        table.add_row("Legacy Weight", f"{metrics.legacy_weight:.2f}")
        table.add_row("V2 Weight", f"{metrics.v2_weight:.2f}")
        table.add_row("Rollback Count", str(metrics.rollback_count), style="red" if metrics.rollback_count else "")
        table.add_row("Reward Variance", f"{metrics.reward_variance:.3f}")
        table.add_row("Diversity Stability", f"{metrics.diversity_stability:.3f}")
        self.update(table)


def _state_style(state: str) -> str:
    lowered = state.lower()
    if "rollback" in lowered:
        return "bold red"
    if "hybrid" in lowered or "full" in lowered:
        return "bold green"
    return "yellow"

