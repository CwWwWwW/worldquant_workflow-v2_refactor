from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from wq_workflow.experiment.scheduler import ExperimentBudgetScheduler


def test_budget_scheduler_iteration_and_hours():
    scheduler = ExperimentBudgetScheduler()
    now = datetime(2026, 1, 2, tzinfo=UTC)
    last = SimpleNamespace(created_at=(now - timedelta(hours=1)).isoformat(), updated_at=(now - timedelta(hours=1)).isoformat(), raw_payload={"iteration": 10})
    assert scheduler.should_refresh(None, now=now)
    assert not scheduler.should_refresh(last, iteration=20, now=now)
    assert scheduler.should_refresh(last, iteration=60, now=now)
    old = SimpleNamespace(created_at=(now - timedelta(hours=25)).isoformat(), updated_at=(now - timedelta(hours=25)).isoformat(), raw_payload={"iteration": 10})
    assert scheduler.should_refresh(old, iteration=20, now=now)
