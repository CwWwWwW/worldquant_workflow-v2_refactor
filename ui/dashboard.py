from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input

from .state_collector import StateCollector, log_dashboard_error
from .widgets.logs_panel import LogsPanel
from .widgets.migration_panel import MigrationPanel
from .widgets.population_panel import PopulationPanel
from .widgets.status_bar import StatusBar
from .widgets.worker_panel import WorkerPanel


class WorkflowDashboard(App):
    CSS = """
    Screen {
        layout: vertical;
    }

    #status {
        height: 3;
        padding: 1 2;
        background: $surface;
    }

    #main {
        height: 1fr;
    }

    #workers {
        width: 58%;
        height: 100%;
        border: solid $primary;
        padding: 1;
    }

    #side {
        width: 42%;
        height: 100%;
    }

    #population, #migration {
        height: 1fr;
        border: solid $primary;
        padding: 1;
    }

    #filter {
        height: 3;
    }

    #logs {
        height: 16;
        border: solid $primary;
        padding: 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.collector = StateCollector()
        self.filter_text = ""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield StatusBar(id="status")
        with Horizontal(id="main"):
            yield WorkerPanel(id="workers")
            with Vertical(id="side"):
                yield PopulationPanel(id="population")
                yield MigrationPanel(id="migration")
        yield Input(placeholder="Filter logs by text/source...", id="filter")
        yield LogsPanel(id="logs")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(1.0, self.refresh_snapshot)
        self.refresh_snapshot()

    def on_input_changed(self, event: Input.Changed) -> None:
        self.filter_text = event.value.strip()
        self.refresh_snapshot()

    def refresh_snapshot(self) -> None:
        try:
            snapshot = self.collector.collect(log_filter=self.filter_text)
            self.query_one(StatusBar).update_status(snapshot.workflow)
            self.query_one(WorkerPanel).update_workers(snapshot.workers)
            self.query_one(PopulationPanel).update_population(snapshot.population)
            self.query_one(MigrationPanel).update_migration(snapshot.migration)
            self.query_one(LogsPanel).update_logs(
                snapshot.logs,
                filter_text=self.filter_text,
                log_manager=snapshot.log_manager,
            )
        except Exception as exc:
            log_dashboard_error(f"refresh_failed: {exc}")


def main() -> None:
    WorkflowDashboard().run()


if __name__ == "__main__":
    main()
