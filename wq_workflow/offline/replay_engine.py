from __future__ import annotations

import hashlib
import uuid
from typing import Any

from .baseline_comparator import BaselineComparator
from .replay_dataset import ReplayDatasetLoader
from .replay_metrics import ReplayMetricsCalculator
from .replay_policy import ReplayPolicy, actions_match, default_replay_policies
from .replay_reporter import ReplayReporter
from .replay_repository import ReplayRepository
from .schema import ReplayDatasetFilter, ReplayPolicyDecision, ReplayPolicyMetrics, ReplayRecord, ReplayRun, utc_now_iso


class ReplayEngine:
    def __init__(
        self,
        *,
        dataset_loader: ReplayDatasetLoader | None = None,
        repository: ReplayRepository | None = None,
        reporter: ReplayReporter | None = None,
        metrics_calculator: ReplayMetricsCalculator | None = None,
        comparator: BaselineComparator | None = None,
        config: Any | None = None,
        storage: Any | None = None,
        db_path: str | None = None,
        logger: Any | None = None,
    ) -> None:
        self.config = config
        self.logger = logger
        self.repository = repository or ReplayRepository(storage=storage, db_path=db_path or getattr(config, "storage_db_path", None), logger=logger)
        self.dataset_loader = dataset_loader or ReplayDatasetLoader(storage=storage, db_path=db_path or getattr(config, "storage_db_path", None), logger=logger)
        min_samples = int(getattr(config, "offline_replay_min_observable_samples", 30) or 30)
        self.metrics_calculator = metrics_calculator or ReplayMetricsCalculator(min_observable_samples=min_samples)
        baseline = str(getattr(config, "offline_replay_baseline_policy", "legacy") or "legacy")
        self.comparator = comparator or BaselineComparator(calculator=self.metrics_calculator, baseline_policy=baseline)
        status_path = getattr(config, "offline_replay_status_path", "runtime/status/offline_replay_report.json")
        self.reporter = reporter or ReplayReporter(repository=self.repository, status_path=status_path, logger=logger)

    def run_replay(self, dataset_filter: ReplayDatasetFilter | dict[str, Any] | None = None, policies: list[ReplayPolicy | str] | None = None, name: str | None = None) -> ReplayRun:
        filt = ReplayDatasetFilter.from_dict(dataset_filter or {})
        if not (filt.raw_payload or {}).get("limit"):
            filt.raw_payload["limit"] = int(getattr(self.config, "offline_replay_default_limit", 1000) or 1000)
        policy_objects = self._normalize_policies(policies)
        run = ReplayRun(
            replay_run_id="replay_run:" + uuid.uuid4().hex,
            name=name or "offline_replay",
            status="running",
            policies=[policy.name() for policy in policy_objects],
            dataset_filter=filt,
            started_at=utc_now_iso(),
            raw_payload={"counterfactual_available": bool(getattr(self.config, "enable_counterfactual_evaluation", False))},
        )
        try:
            self.repository.initialize()
            self.repository.save_replay_run(run)
            records = self.dataset_loader.load_records(filt)
            if len(records) < int(filt.min_samples or 0):
                run.status = "insufficient_data"
                run.sample_count = len(records)
                run.observable_count = sum(1 for item in records if item.outcome is not None)
                run.completed_at = utc_now_iso()
                self.repository.save_replay_run(run)
                self._update_report(run)
                return run
            decisions: list[ReplayPolicyDecision] = []
            for record in records:
                for policy in policy_objects:
                    decision = self.evaluate_policy_decision(record, policy, run.replay_run_id)
                    self.repository.save_policy_decision(decision)
                    decisions.append(decision)
            metrics = self.compute_metrics(run.replay_run_id, decisions)
            for metric in metrics:
                self.repository.save_policy_metrics(metric)
            comparisons = self.compare_to_baseline(run.replay_run_id, metrics=metrics)
            for comparison in comparisons:
                self.repository.save_comparison(comparison)
            run.sample_count = len(records)
            run.observable_count = sum(1 for item in records if item.outcome is not None)
            run.status = "completed" if records else "insufficient_data"
            run.completed_at = utc_now_iso()
            self.repository.save_replay_run(run)
            self._update_report(run)
            return run
        except Exception as exc:
            self._warn(f"run_replay_failed: {exc}")
            run.status = "failed"
            run.completed_at = utc_now_iso()
            run.raw_payload.setdefault("error", str(exc))
            try:
                self.repository.save_replay_run(run)
                self._update_report(run)
            except Exception:
                pass
            return run

    def evaluate_policy_decision(self, record: ReplayRecord | dict[str, Any], policy: ReplayPolicy, replay_run_id: str) -> ReplayPolicyDecision:
        item = ReplayRecord.from_dict(record)
        reason_codes: list[str] = []
        selected = None
        try:
            selected = policy.choose_action(item)
            reason_codes.extend(getattr(policy, "last_reason_codes", []) or [])
        except Exception as exc:
            reason_codes.append("policy_choose_failed")
            reason_codes.append(str(exc)[:120])
        selected_matches_actual = actions_match(selected, item.chosen_action) if selected is not None and item.chosen_action is not None else None
        selected_matches_legacy = actions_match(selected, item.legacy_choice) if selected is not None and item.legacy_choice is not None else None
        observable = bool(selected is not None and selected_matches_actual and item.outcome is not None)
        if selected is None:
            reason_codes.append("no_policy_action")
        elif not selected_matches_actual:
            reason_codes.append("insufficient_counterfactual_evidence")
        elif item.outcome is None:
            reason_codes.append("no_observed_outcome")
        reason_codes = list(dict.fromkeys(str(code) for code in reason_codes if code))
        return ReplayPolicyDecision(
            policy_decision_id=_policy_decision_id(replay_run_id, item.decision_id, policy.name()),
            replay_run_id=replay_run_id,
            decision_id=item.decision_id,
            policy_name=policy.name(),
            selected_action=selected,
            selected_matches_actual=selected_matches_actual,
            selected_matches_legacy=selected_matches_legacy,
            observable_outcome=observable,
            reward=item.reward if observable else None,
            success=item.success if observable else None,
            platform_sc_abs_max=item.platform_sc_abs_max if observable else None,
            quality_passed=item.quality_passed if observable else None,
            reason_codes=reason_codes,
            raw_payload={"decision_type": item.decision_type, "alpha_id": item.alpha_id, "record_id": item.record_id},
        )

    def compute_metrics(self, replay_run_id: str, policy_decisions: list[ReplayPolicyDecision] | None = None) -> list[ReplayPolicyMetrics]:
        decisions = policy_decisions if policy_decisions is not None else self.repository.list_policy_decisions(replay_run_id)
        by_policy: dict[str, list[ReplayPolicyDecision]] = {}
        for decision in decisions:
            item = ReplayPolicyDecision.from_dict(decision)
            by_policy.setdefault(item.policy_name, []).append(item)
        metrics: list[ReplayPolicyMetrics] = []
        for policy_name, items in by_policy.items():
            metrics.append(self.metrics_calculator.calculate_policy_metrics(replay_run_id, items, decision_type=None))
            types = sorted({str((item.raw_payload or {}).get("decision_type") or "unknown") for item in items})
            for decision_type in types:
                metrics.append(self.metrics_calculator.calculate_policy_metrics(replay_run_id, items, decision_type=decision_type))
        return metrics

    def compare_to_baseline(self, replay_run_id: str, baseline_policy: str | None = None, metrics: list[ReplayPolicyMetrics] | None = None):
        metric_items = metrics if metrics is not None else self.repository.list_policy_metrics(replay_run_id)
        baseline = baseline_policy or str(getattr(self.config, "offline_replay_baseline_policy", "legacy") or "legacy")
        challengers = [item.policy_name for item in metric_items if item.policy_name != baseline]
        return self.comparator.compare(replay_run_id, baseline, challengers, metric_items)

    def collect_counterfactual_requests(self, replay_run_id: str, limit: int = 1000):
        """Return replay decisions eligible for Phase 5C without mutating replay outcomes."""
        try:
            decisions = self.repository.list_policy_decisions(replay_run_id)
            return [
                item
                for item in decisions
                if not item.observable_outcome and "insufficient_counterfactual_evidence" in set(item.reason_codes or [])
            ][: max(1, int(limit))]
        except Exception as exc:
            self._warn(f"collect_counterfactual_requests_failed: {exc}")
            return []

    def _normalize_policies(self, policies: list[ReplayPolicy | str] | None) -> list[ReplayPolicy]:
        if not policies:
            configured = getattr(self.config, "offline_replay_include_policies", None)
            if isinstance(configured, (list, tuple)):
                return default_replay_policies([str(item) for item in configured])
            return default_replay_policies()
        if all(isinstance(item, str) for item in policies):
            return default_replay_policies([str(item) for item in policies])
        return [item for item in policies if isinstance(item, ReplayPolicy)]

    def _update_report(self, run: ReplayRun) -> None:
        try:
            self.reporter.update(
                enabled=bool(getattr(self.config, "enable_offline_replay", False)),
                mode=str(getattr(self.config, "offline_replay_mode", "advisory") or "advisory"),
                latest_replay_run_id=run.replay_run_id,
            )
            run.raw_payload.setdefault("counterfactual_available", bool(getattr(self.config, "enable_counterfactual_evaluation", False)))
        except Exception as exc:
            self._warn(f"update_report_failed: {exc}")

    def _warn(self, message: str) -> None:
        try:
            if self.logger is not None:
                self.logger.warning("offline replay engine: %s", message)
        except Exception:
            pass


def _policy_decision_id(replay_run_id: str, decision_id: str, policy_name: str) -> str:
    seed = f"{replay_run_id}|{decision_id}|{policy_name}"
    return "replay_decision:" + hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()[:24]
