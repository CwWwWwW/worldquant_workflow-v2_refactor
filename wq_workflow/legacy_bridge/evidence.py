from __future__ import annotations

from pathlib import Path
from typing import Any

from wq_workflow import paths

from .schema import LegacyLearningEvidence
from .utils import append_jsonl_direct, read_jsonl_tail_direct, resolve_path, rotate_if_large_direct, summarize_payload, truncate_text

DEFAULT_LEGACY_EVIDENCE_PATH = "runtime/status/legacy_learning_evidence.jsonl"


def _metrics(payload: dict[str, Any] | None) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {}


class LegacyLearningEvidenceBuilder:
    def build_generic(self, evidence_type: str = "unknown", **kwargs: Any) -> LegacyLearningEvidence:
        payload = _metrics(kwargs.pop("raw_payload", {}))
        metrics = _metrics(kwargs.pop("metrics", {}))
        platform_sc = _metrics(kwargs.pop("platform_sc", {}))
        summary = kwargs.pop("summary", evidence_type)
        return LegacyLearningEvidence(
            evidence_type=evidence_type,
            reward=kwargs.pop("reward", None),
            sc_value=kwargs.pop("sc_value", platform_sc.get("abs_max") or platform_sc.get("max") or metrics.get("self_corr")),
            sharpe=kwargs.pop("sharpe", metrics.get("sharpe")),
            fitness=kwargs.pop("fitness", metrics.get("fitness")),
            turnover=kwargs.pop("turnover", metrics.get("turnover")),
            summary=truncate_text(summary, 300),
            raw_payload=summarize_payload({**payload, "metrics": metrics, "platform_sc": platform_sc}, max_payload_chars=1000),
            **kwargs,
        )

    def from_template_selected(self, **kwargs: Any) -> LegacyLearningEvidence:
        return self.build_generic("template_selected", summary="legacy template selected", **kwargs)

    def from_alpha_generated(self, **kwargs: Any) -> LegacyLearningEvidence:
        return self.build_generic("alpha_generated", summary="legacy alpha generated", **kwargs)

    def from_backtest_submitted(self, **kwargs: Any) -> LegacyLearningEvidence:
        return self.build_generic("backtest_submitted", summary="legacy backtest submitted", **kwargs)

    def from_backtest_result(self, **kwargs: Any) -> LegacyLearningEvidence:
        return self.build_generic("backtest_result", summary="legacy backtest result", observed=True, estimated=False, advisory=False, **kwargs)

    def from_parse_result(self, **kwargs: Any) -> LegacyLearningEvidence:
        return self.build_generic("parse_result", summary="legacy parse result", **kwargs)

    def from_sc_check(self, **kwargs: Any) -> LegacyLearningEvidence:
        return self.build_generic("sc_check", summary="legacy platform sc check", **kwargs)

    def from_reward_update(self, **kwargs: Any) -> LegacyLearningEvidence:
        return self.build_generic("reward_update", summary="legacy reward update", **kwargs)

    def from_candidate_pool_update(self, **kwargs: Any) -> LegacyLearningEvidence:
        return self.build_generic("candidate_pool_update", summary="legacy candidate pool update", **kwargs)

    def from_failure(self, **kwargs: Any) -> LegacyLearningEvidence:
        return self.build_generic("failure", summary="legacy failure", **kwargs)

    def from_governance_result(self, **kwargs: Any) -> LegacyLearningEvidence:
        return self.build_generic("governance_result", summary="legacy governance result", **kwargs)

    def from_ml_prediction(self, **kwargs: Any) -> LegacyLearningEvidence:
        return self.build_generic("ml_prediction", summary="legacy ml prediction", advisory=True, **kwargs)


class LegacyLearningEvidenceWriter:
    def __init__(self, path: str | Path = DEFAULT_LEGACY_EVIDENCE_PATH, *, root: str | Path | None = None, enabled: bool = True, max_bytes: int = 10_485_760) -> None:
        self.root = Path(root or paths.ROOT)
        self.path = resolve_path(self.root, path)
        self.enabled = bool(enabled)
        self.max_bytes = int(max_bytes or 0)

    def append_evidence(self, evidence: LegacyLearningEvidence) -> bool:
        if not self.enabled:
            return False
        try:
            return append_jsonl_direct(self.path, evidence.to_dict(), max_bytes=self.max_bytes)
        except Exception:
            return False

    def append_many(self, evidence: list[LegacyLearningEvidence]) -> int:
        count = 0
        for item in list(evidence or []):
            if self.append_evidence(item):
                count += 1
        return count

    def rotate_if_needed(self, max_bytes: int | None = None) -> None:
        rotate_if_large_direct(self.path, int(max_bytes or self.max_bytes or 0))


class LegacyLearningEvidenceReader:
    def __init__(self, path: str | Path = DEFAULT_LEGACY_EVIDENCE_PATH, *, root: str | Path | None = None) -> None:
        self.root = Path(root or paths.ROOT)
        self.path = resolve_path(self.root, path)

    def read_tail(self, limit: int = 200) -> list[LegacyLearningEvidence]:
        return [LegacyLearningEvidence.from_dict(row) for row in read_jsonl_tail_direct(self.path, limit=limit)]

    def summarize_by_type(self, limit: int = 200) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        for item in self.read_tail(limit=limit):
            bucket = summary.setdefault(item.evidence_type, {"count": 0, "observed": 0, "estimated": 0, "advisory": 0})
            bucket["count"] += 1
            bucket["observed"] += 1 if item.observed else 0
            bucket["estimated"] += 1 if item.estimated else 0
            bucket["advisory"] += 1 if item.advisory else 0
        return summary

    def summarize_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = []
        for item in self.read_tail(limit=limit):
            rows.append({
                "timestamp": item.timestamp,
                "evidence_type": item.evidence_type,
                "alpha_id": item.alpha_id,
                "iteration": item.iteration,
                "observed": item.observed,
                "estimated": item.estimated,
                "advisory": item.advisory,
                "result_status": item.result_status,
                "reward": item.reward,
                "sc_value": item.sc_value,
                "summary": truncate_text(item.summary, 160),
            })
        return rows
