from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .schema import utc_now_iso


class ExperimentBudgetScheduler:
    def __init__(self, *, config: Any | None = None) -> None:
        self.config = config
        self.refresh_interval_iterations = max(1, _int(config, "experiment_budget_refresh_interval_iterations", 50))
        self.refresh_interval_hours = max(1, _int(config, "experiment_budget_refresh_interval_hours", 24))

    def should_refresh(self, last_plan: Any | None, iteration: int | None = None, now: datetime | str | None = None) -> bool:
        if last_plan is None:
            return True
        if iteration is not None:
            try:
                last_iteration = int(getattr(last_plan, "raw_payload", {}).get("iteration", 0))
                if int(iteration) - last_iteration >= self.refresh_interval_iterations:
                    return True
            except Exception:
                pass
        current = _coerce_datetime(now) or datetime.now(UTC)
        updated = _coerce_datetime(getattr(last_plan, "updated_at", None) or getattr(last_plan, "created_at", None))
        if updated is None:
            return True
        elapsed_hours = (current - updated).total_seconds() / 3600.0
        return elapsed_hours >= self.refresh_interval_hours


def _coerce_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    try:
        text = str(value)
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _int(config: Any | None, name: str, default: int) -> int:
    try:
        return int(getattr(config, name, default))
    except (TypeError, ValueError):
        return default
