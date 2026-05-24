from __future__ import annotations

from typing import Any

from .audit import record_data_audit_failure
from .json_utils import safe_float


def _get_attr(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


class IterationUnitOfWork:
    def __init__(self, repositories: Any, logger: Any | None = None, storage: Any | None = None) -> None:
        self.repositories = repositories
        self.logger = logger
        self.storage = storage

    def _repo(self, name: str) -> Any:
        if isinstance(self.repositories, dict):
            return self.repositories.get(name)
        return getattr(self.repositories, name, None)

    def persist_result(self, workflow_context: Any) -> dict[str, Any]:
        wf = workflow_context
        errors: list[dict[str, str]] = []
        written: list[str] = []
        candidate_repo = self._repo("candidate")
        iteration_repo = self._repo("iteration")
        decision_repo = self._repo("decision")
        ml_repo = self._repo("ml")

        candidate = _get_attr(wf, "candidate") or {}
        metrics = _get_attr(wf, "metrics") or {}
        platform_sc = _get_attr(wf, "platform_sc") or {}
        quality = _get_attr(wf, "quality") or {}
        alpha_id = _get_attr(wf, "alpha_id") or candidate.get("alpha_id") or ""
        reward = _get_attr(wf, "reward")

        candidate_record = {
            **candidate,
            "alpha_id": alpha_id or candidate.get("alpha_id", ""),
            "metrics": metrics,
            "platform_sc": platform_sc,
            "quality": quality,
            "reward": reward,
        }
        iteration_record = {
            "iteration_id": _get_attr(wf, "iteration_id", ""),
            "alpha_id": alpha_id,
            "candidate": candidate,
            "metrics": metrics,
            "platform_sc": platform_sc,
            "quality": quality,
            "reward": reward,
            "decisions": _get_attr(wf, "decisions", []),
            "event_type": "iteration_result",
        }

        try:
            if candidate_repo is not None and candidate_record.get("alpha_id"):
                candidate_repo.upsert_candidate(candidate_record)
                written.append("candidate")
        except Exception as exc:
            record_data_audit_failure(self.logger, operation="candidate.upsert", error=exc, storage=self.storage, context={"alpha_id": alpha_id})
            return {"ok": False, "fatal": True, "written": written, "errors": [{"operation": "candidate.upsert", "error": str(exc)}]}

        try:
            if iteration_repo is not None:
                iteration_repo.insert_iteration(iteration_record)
                written.append("iteration")
        except Exception as exc:
            record_data_audit_failure(self.logger, operation="iteration.insert", error=exc, storage=self.storage, context={"alpha_id": alpha_id})
            return {"ok": False, "fatal": True, "written": written, "errors": [{"operation": "iteration.insert", "error": str(exc)}]}

        for decision in _get_attr(wf, "decisions", []) or []:
            if not isinstance(decision, dict):
                continue
            try:
                decision_id = decision.get("decision_id")
                if decision_repo is not None and decision_id:
                    decision_repo.insert_decision_outcome(
                        decision_id=decision_id,
                        decision_type=decision.get("decision_type", ""),
                        alpha_id=decision.get("alpha_id") or alpha_id,
                        reward=reward,
                        reward_delta=decision.get("reward_delta"),
                        success=quality.get("passed") if isinstance(quality, dict) else None,
                        failure_type=quality.get("failure_type") if isinstance(quality, dict) else "",
                        platform_sc_abs_max=safe_float(platform_sc.get("abs_max") if isinstance(platform_sc, dict) else None),
                        metrics=metrics,
                        raw_payload={"decision": decision, "workflow": iteration_record},
                    )
                    written.append("decision_outcome")
            except Exception as exc:
                errors.append({"operation": "decision_outcome", "error": str(exc)})
                record_data_audit_failure(self.logger, operation="decision_outcome", error=exc, storage=self.storage, context={"alpha_id": alpha_id})

        try:
            prediction_audits = _get_attr(wf, "prediction_audits", []) or []
            for audit in prediction_audits:
                if isinstance(audit, dict) and ml_repo is not None:
                    ml_repo.audit_prediction(
                        audit.get("task_name", ""),
                        audit.get("prediction_id", ""),
                        audit.get("alpha_id") or alpha_id,
                        audit.get("model_version", ""),
                        audit.get("features", {}),
                        audit.get("prediction", {}),
                        audit.get("confidence"),
                        audit.get("final_decision", ""),
                        audit.get("final_source", ""),
                        audit.get("raw_payload", audit),
                    )
                    written.append("prediction_audit")
        except Exception as exc:
            errors.append({"operation": "prediction_audit", "error": str(exc)})
            record_data_audit_failure(self.logger, operation="prediction_audit", error=exc, storage=self.storage, context={"alpha_id": alpha_id})

        return {"ok": not errors, "fatal": False, "written": written, "errors": errors}
