from __future__ import annotations

from typing import Any

from wq_workflow.data.json_utils import json_loads_safe, safe_float
from .counterfactual import CounterfactualEstimator, _action_key
from .metrics import estimated_reward_delta, estimated_risk_delta, failure_delta, model_match_rate, replay_pass_gate, support_coverage
from .report import build_replay_report, save_replay_report
from .support_checker import SupportChecker


def _decision_type_for_task(task_name: str) -> str:
    task = str(task_name or "").lower()
    if task == "parent":
        return "parent_selection"
    if task == "policy":
        return "policy_action"
    if task in {"simulator", "outcome"}:
        return "simulator_decision"
    if task == "sc":
        return "sc_decision"
    return task


class OfflineReplayEvaluator:
    def __init__(self, repositories: Any, model_registry: Any, config: Any, logger: Any | None = None) -> None:
        self.repositories = repositories
        self.model_registry = model_registry
        self.config = config
        self.logger = logger
        self.counterfactual = CounterfactualEstimator(repositories, config, logger)
        self.support_checker = SupportChecker(repositories, config, logger)

    def evaluate_task(self, task_name: str, model_version: str | None = None, decision_type: str | None = None) -> dict:
        task = str(task_name or "")
        dtype = decision_type or _decision_type_for_task(task)
        decision_repo = getattr(self.repositories, "decision", None)
        if decision_repo is None:
            report = build_replay_report(task_name=task, model_version=model_version or "", decision_type=dtype, sample_count=0, support_coverage=0.0, model_match_rate=0.0, estimated_reward_delta=0.0, estimated_sc_risk_delta=0.0, estimated_failure_delta=0.0, replay_pass=False, reasons=["decision_repository_unavailable"])
            return report
        limit = int(getattr(self.config, "offline_replay_max_decisions", 5000) or 5000)
        decisions = decision_repo.list_recent_decisions(decision_type=dtype, limit=limit)
        matches: list[bool] = []
        supported: list[bool] = []
        reward_deltas: list[float] = []
        risk_deltas: list[float] = []
        failure_deltas: list[float] = []
        reasons: list[str] = []
        details: list[dict[str, Any]] = []
        used_model_version = model_version or ""

        for row in decisions:
            context = json_loads_safe(row.get("context_json"), {})
            available = json_loads_safe(row.get("available_actions_json"), [])
            chosen = json_loads_safe(row.get("chosen_action_json"), {})
            scores = json_loads_safe(row.get("action_scores_json"), {})
            if not isinstance(available, list):
                available = [available]
            if not isinstance(context, dict):
                context = {}
            if not isinstance(chosen, dict):
                chosen = {}
            recommendation = self._recommend(task, dtype, context, available, scores, model_version)
            if recommendation.get("model_version") and not used_model_version:
                used_model_version = str(recommendation.get("model_version") or "")
            recommended_action = recommendation.get("action") if isinstance(recommendation.get("action"), dict) else {}
            is_match = self._actions_match(chosen, recommended_action)
            matches.append(is_match)
            support = self.support_checker.check_action_support(dtype, _action_key(recommended_action), context)
            supported.append(bool(support.get("support_pass")))

            outcome = decision_repo.get_outcome_for_decision(str(row.get("decision_id") or ""))
            if is_match and outcome:
                reward_deltas.append(safe_float(outcome.get("reward_delta", outcome.get("reward")), 0.0))
                risk_deltas.append(0.0)
                failure_deltas.append(0.0 if outcome.get("success") in {1, True} else 1.0)
                source = "real_outcome_for_matching_legacy_action"
            else:
                estimate = self.counterfactual.estimate_action_outcome(context, recommended_action, dtype)
                reward_deltas.append(safe_float(estimate.get("estimated_reward_delta"), 0.0))
                risk_deltas.append(safe_float(estimate.get("estimated_sc_risk"), 0.0))
                failure_deltas.append(safe_float(estimate.get("estimated_failure_rate"), 0.0))
                source = "counterfactual_conservative_estimate"
                if estimate.get("support_status") != "sufficient":
                    reasons.append("support_insufficient")
            details.append({
                "decision_id": row.get("decision_id", ""),
                "legacy_action": chosen,
                "recommended_action": recommended_action,
                "match": is_match,
                "support": support,
                "outcome_source": source,
            })

        sample_count = len(decisions)
        metrics = {
            "sample_count": sample_count,
            "support_coverage": support_coverage(supported) if supported else 0.0,
            "model_match_rate": model_match_rate(matches) if matches else 0.0,
            "estimated_reward_delta": estimated_reward_delta(reward_deltas) if reward_deltas else 0.0,
            "estimated_sc_risk_delta": estimated_risk_delta(risk_deltas) if risk_deltas else 0.0,
            "estimated_failure_delta": failure_delta(failure_deltas) if failure_deltas else 0.0,
        }
        gate = replay_pass_gate(metrics, self.config)
        all_reasons = list(dict.fromkeys(reasons + list(gate.get("reasons") or [])))
        report = build_replay_report(
            task_name=task,
            strategy_id=self._strategy_id_for_task(task),
            model_version=used_model_version,
            decision_type=dtype,
            replay_pass=bool(gate.get("replay_pass")) and "support_insufficient" not in all_reasons,
            reasons=all_reasons,
            details=details,
            **metrics,
        )
        report["report_id"] = save_replay_report(self.repositories, report) or report["report_id"]
        return report

    def evaluate_parent_model(self, model_version: str | None = None) -> dict:
        return self.evaluate_task("parent", model_version=model_version, decision_type="parent_selection")

    def evaluate_policy_model(self, model_version: str | None = None) -> dict:
        return self.evaluate_task("policy", model_version=model_version, decision_type="policy_action")

    def evaluate_simulator_model(self, model_version: str | None = None) -> dict:
        return self.evaluate_task("simulator", model_version=model_version, decision_type="simulator_decision")

    def _recommend(self, task: str, decision_type: str, context: dict[str, Any], available: list[Any], scores: Any, model_version: str | None) -> dict[str, Any]:
        actions = [a for a in available if isinstance(a, dict)]
        if not actions:
            return {"action": {}, "model_version": model_version or "", "source": "no_available_actions"}
        if hasattr(self.model_registry, "recommend"):
            try:
                rec = self.model_registry.recommend(decision_type=decision_type, context=context, actions=actions, model_version=model_version)
                if isinstance(rec, dict):
                    return {"action": rec.get("action", rec), "model_version": rec.get("model_version", model_version or ""), "source": rec.get("source", "model_registry_recommend")}
            except Exception:
                pass
        if isinstance(scores, dict) and scores:
            def score(action: dict[str, Any], idx: int) -> float:
                keys = [_action_key(action), str(action.get("alpha_id") or ""), str(idx)]
                for key in keys:
                    if key in scores:
                        return safe_float(scores.get(key), 0.0)
                return safe_float(action.get("model_score", action.get("action_score", action.get("legacy_score"))), 0.0)

            best_idx, best = max(enumerate(actions), key=lambda item: score(item[1], item[0]))
            return {"action": best, "model_version": model_version or "", "source": "snapshot_action_scores", "score": score(best, best_idx)}
        return {"action": actions[0], "model_version": model_version or "", "source": "legacy_fallback_no_model_score"}

    def _actions_match(self, legacy: dict[str, Any], recommended: dict[str, Any]) -> bool:
        legacy_key = _action_key(legacy)
        rec_key = _action_key(recommended)
        if legacy_key or rec_key:
            return legacy_key == rec_key
        return legacy == recommended

    def _strategy_id_for_task(self, task: str) -> str:
        task = str(task or "").lower()
        if task in {"parent", "policy", "simulator", "sc"}:
            return f"{task}_learning_challenger"
        return ""
