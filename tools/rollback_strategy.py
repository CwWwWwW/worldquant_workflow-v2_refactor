from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wq_workflow.app.bootstrap import build_app_context


def main() -> int:
    parser = argparse.ArgumentParser(description="Rollback active strategy without deleting models.")
    parser.add_argument("--to", choices=["legacy_champion", "previous_champion"], default="legacy_champion")
    parser.add_argument("--reason", default="manual_rollback")
    args = parser.parse_args()
    ctx = build_app_context()
    policy = ctx.strategy_services.get("rollback_policy")
    if policy is None:
        print(json.dumps({"rolled_back": False, "reason": "rollback_policy_unavailable"}, ensure_ascii=False, indent=2))
        return 1
    result = policy.rollback_to_previous_champion(args.reason) if args.to == "previous_champion" else policy.rollback_to_legacy(args.reason)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("rolled_back") else 1


if __name__ == "__main__":
    raise SystemExit(main())
