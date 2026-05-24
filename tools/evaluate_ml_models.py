from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wq_workflow.app.bootstrap import build_app_context

TASKS = ("sc", "parent", "policy", "simulator")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate active ML model registry state.")
    parser.add_argument("--task", choices=[*TASKS, "all"], default="all")
    args = parser.parse_args()
    ctx = build_app_context()
    registry = ctx.learning_services.get("model_registry")
    selected = TASKS if args.task == "all" else (args.task,)
    out = {}
    for task in selected:
        active = registry.load_active_model(task) if registry else None
        meta = (active or {}).get("payload", {}) if active else {}
        out[task] = {"active_model": bool(active), "model_version": meta.get("model_version", ""), "metrics": meta.get("validation_metric_json", {}), "sample_count": meta.get("train_sample_count", 0), "model_path": meta.get("model_path", ""), "validation_status": meta.get("validation_passed", False)}
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
