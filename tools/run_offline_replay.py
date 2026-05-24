from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wq_workflow.app.bootstrap import build_app_context
from wq_workflow.offline.report import summarize_replay_report


TASKS = ("parent", "policy", "simulator")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run offline replay evaluation.")
    parser.add_argument("--task", choices=[*TASKS, "all"], default="all")
    parser.add_argument("--model-version", default="")
    args = parser.parse_args()
    ctx = build_app_context()
    evaluator = ctx.offline_services.get("replay_evaluator")
    selected = TASKS if args.task == "all" else (args.task,)
    out = {}
    for task in selected:
        report = evaluator.evaluate_task(task, model_version=args.model_version or None) if evaluator else {"replay_pass": False, "reasons": ["replay_evaluator_unavailable"]}
        out[task] = summarize_replay_report(report)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
