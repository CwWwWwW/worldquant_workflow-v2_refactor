from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Static

from wq_workflow.dashboard.cli_formatter import CLIStatusFormatter
from wq_workflow.dashboard.status_aggregator import DashboardStatusAggregator


class WorkflowDashboard(App):
    CSS = """
    Screen {
        layout: vertical;
    }

    #final-status {
        height: 1fr;
        padding: 1 2;
        background: $surface;
        border: solid $primary;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.aggregator = DashboardStatusAggregator()
        self.formatter = CLIStatusFormatter()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Loading readonly dashboard snapshot...", id="final-status")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(10.0, self.refresh_snapshot)
        self.refresh_snapshot()

    def refresh_snapshot(self) -> None:
        try:
            snapshot = self.aggregator.build_snapshot()
            self.query_one("#final-status", Static).update(
                self.formatter.format_snapshot(snapshot, compact=False, limit=12)
            )
        except Exception as exc:
            self.query_one("#final-status", Static).update(
                f"Dashboard refresh failed (readonly): {type(exc).__name__}: {exc}"
            )


def main() -> None:
    WorkflowDashboard().run()


if __name__ == "__main__":
    main()
