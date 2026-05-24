from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wq_workflow.learning.ml.model_registry import ModelRegistry
from wq_workflow.storage.manager import load_storage_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Show ML model registry.")
    parser.add_argument("--task", default="")
    args = parser.parse_args()
    storage_config = load_storage_config()
    registry = ModelRegistry(db_path=storage_config.db_path)
    rows = registry.list_models(args.task or None)
    print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
