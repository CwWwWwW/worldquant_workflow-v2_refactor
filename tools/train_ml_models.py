from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wq_workflow.app.bootstrap import build_app_context

TASKS = ("sc", "parent", "policy", "simulator")


def main() -> int:
    parser = argparse.ArgumentParser(description="Train ML models for shadow learning tasks.")
    parser.add_argument("--task", choices=[*TASKS, "all"], default="all")
    args = parser.parse_args()
    ctx = build_app_context()
    selected = TASKS if args.task == "all" else (args.task,)
    results = {}
    key_map = {"sc": "sc_trainer", "parent": "parent_trainer", "policy": "policy_trainer", "simulator": "outcome_trainer"}
    for task in selected:
        trainer = ctx.learning_services.get(key_map[task])
        if trainer is None:
            results[task] = {"trained": False, "status": "missing_trainer", "reason": "missing_trainer"}
            continue
        try:
            results[task] = trainer.train_if_ready() if hasattr(trainer, "train_if_ready") else trainer.train()
        except Exception as exc:
            results[task] = {"trained": False, "status": "training_error", "reason": "training_error", "error": str(exc)}
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
