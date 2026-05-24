from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wq_workflow.learning.ml.model_registry import ModelRegistry
from wq_workflow.storage.manager import load_storage_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check ML model registry consistency without platform/browser access.")
    parser.add_argument("--task", default="", help="Optional task name, e.g. sc, parent, policy, simulator.")
    parser.add_argument("--repair", action="store_true", help="Safely disable broken active pointers and extra active DB rows.")
    args = parser.parse_args(argv)

    storage_config = load_storage_config()
    registry = ModelRegistry(db_path=storage_config.db_path)
    if args.repair:
        result = registry.repair_registry(args.task or None)
    else:
        result = registry.check_registry_consistency(args.task or None)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
