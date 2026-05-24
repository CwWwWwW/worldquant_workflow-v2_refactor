from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wq_workflow.app.bootstrap import build_app_context


def main() -> int:
    ctx = build_app_context()
    registry = ctx.strategy_services.get("registry")
    allocator = ctx.strategy_services.get("budget_allocator")
    tracker = ctx.strategy_services.get("performance_tracker")
    strategies = registry.list_strategies() if registry else []
    safety_repo = getattr(ctx.repositories, "replay", None)
    allocations = allocator.allocate(strategies) if allocator else {}
    rows = []
    for strategy in strategies:
        sid = str(strategy.get("strategy_id") or "")
        safety = safety_repo.latest_model_safety_report(strategy_id=sid) if safety_repo is not None else {}
        rows.append({
            "strategy_id": sid,
            "role": strategy.get("role", ""),
            "status": strategy.get("status", ""),
            "task_name": strategy.get("task_name", ""),
            "model_version": strategy.get("model_version", ""),
            "current_budget": allocations.get(sid, 0.0),
            "recent_performance": tracker.load_strategy_metrics(sid) if tracker else {},
            "safety_status": (safety or {}).get("safety_status", "unknown"),
        })
    print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
