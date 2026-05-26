from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wq_workflow.dashboard.cli_formatter import CLIStatusFormatter, snapshot_to_json
from wq_workflow.dashboard.status_aggregator import DashboardStatusAggregator


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show final readonly workflow/dashboard status.")
    parser.add_argument("--compact", action="store_true", help="Show compact summary (default).")
    parser.add_argument("--verbose", action="store_true", help="Show more recent events, still bounded by --limit.")
    parser.add_argument("--limit", type=int, default=8, help="Maximum event/detail rows to print.")
    parser.add_argument("--json", action="store_true", help="Print JSON snapshot.")
    parser.add_argument("--no-db", action="store_true", help="Do not read workflow.db.")
    parser.add_argument("--no-logs", action="store_true", help="Do not read logs.")
    args = parser.parse_args(argv)

    snapshot = DashboardStatusAggregator(include_db=not args.no_db, include_logs=not args.no_logs).build_snapshot()
    if args.json:
        print(snapshot_to_json(snapshot))
    else:
        formatter = CLIStatusFormatter()
        print(formatter.format_snapshot(snapshot, compact=not args.verbose, limit=max(1, int(args.limit))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
