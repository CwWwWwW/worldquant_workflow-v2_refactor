from __future__ import annotations

from rich.table import Table
from textual.widgets import Static

from ui.models import PopulationMetrics


class PopulationPanel(Static):
    def update_population(self, metrics: PopulationMetrics) -> None:
        table = Table(title="Population Health", expand=True)
        table.add_column("Metric")
        table.add_column("Value", justify="right")
        table.add_row("Diversity", f"{metrics.diversity:.3f}", style=_metric_style(metrics.diversity, low_bad=True))
        table.add_row("Correlation", f"{metrics.correlation:.3f}", style=_metric_style(metrics.correlation, low_bad=False))
        table.add_row("Mutation Success", f"{metrics.mutation_success_rate * 100:.1f}%")
        table.add_row("Reward Variance", f"{metrics.reward_stability:.3f}")
        table.add_row("Survival Rate", f"{metrics.survival_rate * 100:.1f}%")
        self.update(table)


def _metric_style(value: float, *, low_bad: bool) -> str:
    if low_bad and value < 0.3:
        return "red"
    if not low_bad and value > 0.82:
        return "red"
    return "green"

