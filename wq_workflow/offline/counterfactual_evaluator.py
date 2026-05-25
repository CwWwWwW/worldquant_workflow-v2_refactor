from __future__ import annotations

from typing import Any

from .counterfactual_dataset import CounterfactualDatasetLoader
from .counterfactual_metrics import CounterfactualMetricsCalculator
from .counterfactual_neighbors import CounterfactualNeighborIndex
from .counterfactual_reporter import CounterfactualReporter
from .counterfactual_repository import CounterfactualRepository
from .schema import CounterfactualEstimate, CounterfactualRequest, ReplayPolicyDecision, ReplayRecord, utc_now_iso


class CounterfactualEvaluator:
    def __init__(
        self,
        *,
        dataset_loader: CounterfactualDatasetLoader | None = None,
        repository: CounterfactualRepository | None = None,
        reporter: CounterfactualReporter | None = None,
        neighbor_index: CounterfactualNeighborIndex | None = None,
        metrics_calculator: CounterfactualMetricsCalculator | None = None,
        config: Any | None = None,
        storage: Any | None = None,
        db_path: str | None = None,
        logger: Any | None = None,
    ) -> None:
        self.config = config
        self.logger = logger
        self.repository = repository or CounterfactualRepository(storage=storage, db_path=db_path or getattr(config, "storage_db_path", None), logger=logger)
        self.dataset_loader = dataset_loader or CounterfactualDatasetLoader(storage=storage, db_path=db_path or getattr(config, "storage_db_path", None), config=config, logger=logger)
        self.neighbor_index = neighbor_index or CounterfactualNeighborIndex()
        self.metrics_calculator = metrics_calculator or CounterfactualMetricsCalculator.from_config(config)
        status_path = getattr(config, "counterfactual_status_path", "runtime/status/counterfactual_report.json")
        self.reporter = reporter or CounterfactualReporter(repository=self.repository, status_path=status_path, logger=logger)

    def evaluate_request(self, request: CounterfactualRequest | dict[str, Any]) -> CounterfactualEstimate:
        req = CounterfactualRequest.from_dict(request)
        try:
            self.repository.initialize()
            if not req.request_id:
                req.request_id = f"counterfactual_request:{req.decision_id}:{utc_now_iso()}"
            if not req.min_evidence:
                req.min_evidence = int(getattr(self.config, "counterfactual_min_evidence", 30) or 30)
            self.repository.save_request(req)
            limit = int(getattr(self.config, "counterfactual_default_limit", 1000) or 1000)
            candidate_limit = max(limit, int(req.min_evidence or 30))
            records = self.dataset_loader.load_candidate_evidence(req, limit=candidate_limit)
            threshold = float(getattr(self.config, "counterfactual_similarity_threshold", 0.55) or 0.55)
            neighbors = self.neighbor_index.find_neighbors(req, records, limit=limit, threshold=threshold)
            estimate = self.metrics_calculator.estimate_from_evidence(req, neighbors)
            for item in neighbors:
                self.repository.save_evidence(item)
            self.repository.save_estimate(estimate)
            self.repository.update_summary(req.decision_type)
            self.repository.update_summary(None)
            self._update_report(req.replay_run_id)
            return estimate
        except Exception as exc:
            self._warn(f"evaluate_request_failed: {exc}")
            return CounterfactualEstimate(
                estimate_id=f"counterfactual_estimate:failed:{req.decision_id}",
                request_id=req.request_id,
                decision_id=req.decision_id,
                target_action_json=req.target_action.to_dict() if req.target_action is not None else None,
                confidence="insufficient",
                verdict="insufficient_evidence",
                reason_codes=["counterfactual_evaluation_failed", "insufficient_evidence"],
                estimated_not_observed=True,
                raw_payload={"error": str(exc)},
            )

    def evaluate_policy_decision(self, policy_decision: ReplayPolicyDecision | dict[str, Any], replay_record: ReplayRecord | dict[str, Any] | None = None) -> CounterfactualEstimate | None:
        decision = ReplayPolicyDecision.from_dict(policy_decision)
        if decision.observable_outcome:
            return None
        if decision.selected_action is None:
            return None
        record = ReplayRecord.from_dict(replay_record or {}) if replay_record is not None else self.dataset_loader.load_record_for_decision(decision.decision_id)
        if record is None:
            return None
        request = self.dataset_loader.build_request_from_policy_decision(decision, record)
        if request is None:
            return None
        return self.evaluate_request(request)

    def evaluate_replay_run(self, replay_run_id: str | None = None, limit: int = 1000) -> list[CounterfactualEstimate]:
        estimates: list[CounterfactualEstimate] = []
        try:
            decisions = self.dataset_loader.load_replay_policy_decisions(replay_run_id=replay_run_id, only_insufficient=True, limit=max(1, int(limit)))
            for decision in decisions:
                record = self.dataset_loader.load_record_for_decision(decision.decision_id)
                estimate = self.evaluate_policy_decision(decision, record)
                if estimate is not None:
                    estimates.append(estimate)
            self._update_report(replay_run_id)
        except Exception as exc:
            self._warn(f"evaluate_replay_run_failed: {exc}")
        return estimates

    def _update_report(self, latest_replay_run_id: str | None = None) -> None:
        try:
            self.reporter.update(
                enabled=bool(getattr(self.config, "enable_counterfactual_evaluation", False)),
                mode=str(getattr(self.config, "counterfactual_mode", "advisory") or "advisory"),
                latest_replay_run_id=latest_replay_run_id,
            )
        except Exception as exc:
            self._warn(f"update_report_failed: {exc}")

    def _warn(self, message: str) -> None:
        try:
            if self.logger is not None:
                self.logger.warning("counterfactual evaluator: %s", message)
        except Exception:
            pass
