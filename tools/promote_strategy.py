from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wq_workflow.app.bootstrap import build_app_context
from wq_workflow.offline.report import save_model_safety_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote a challenger strategy if eligible.")
    parser.add_argument("--strategy-id", required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--reason", default="")
    args = parser.parse_args()
    ctx = build_app_context()
    policy = ctx.strategy_services.get("promotion_policy")
    registry = ctx.strategy_services.get("registry")
    evaluation = policy.evaluate_promotion(args.strategy_id) if policy else {"promotion_pass": False, "reasons": ["promotion_policy_unavailable"], "strategy_id": args.strategy_id}
    if not evaluation.get("promotion_pass") and not args.force:
        print(json.dumps({"promoted": False, **evaluation}, ensure_ascii=False, indent=2, default=str))
        return 1
    if args.force and registry is not None:
        listing = registry.list_portfolio_strategies() if hasattr(registry, "list_portfolio_strategies") else registry.list_strategies()
        champions = [s for s in listing if s.get("role") == "champion"]
        for champion in champions:
            registry.update_role(str(champion.get("strategy_id")), "previous_champion", f"force_promote:{args.reason or 'manual_force'}")
        registry.update_role(args.strategy_id, "champion", f"force_promote:{args.reason or 'manual_force'}")
        repo = getattr(ctx.repositories, "strategy", None)
        if repo is not None:
            repo.insert_allocation({"strategy_id": args.strategy_id, "role": "champion", "budget": 1.0, "reason": f"force_promote:{args.reason or 'manual_force'}", "raw_payload": {"force": True, "reason": args.reason}})
        save_model_safety_report(ctx.repositories, {"strategy_id": args.strategy_id, "promotion_pass": True, "safety_status": "force_promoted", "reason": args.reason or "manual_force", "raw_payload": {"force": True, "evaluation": evaluation}})
        print(json.dumps({"promoted": True, "forced": True, "evaluation": evaluation}, ensure_ascii=False, indent=2, default=str))
        return 0
    result = policy.promote_if_eligible(args.strategy_id) if policy else {"promoted": False, **evaluation}
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("promoted") else 1


if __name__ == "__main__":
    raise SystemExit(main())
