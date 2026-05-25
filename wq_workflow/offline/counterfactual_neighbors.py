from __future__ import annotations

import hashlib
from typing import Any

from .counterfactual_features import CounterfactualFeatureBuilder
from .schema import CounterfactualEvidence, CounterfactualRequest, DecisionAction, ReplayRecord


class CounterfactualNeighborIndex:
    def __init__(self, *, feature_builder: CounterfactualFeatureBuilder | None = None) -> None:
        self.feature_builder = feature_builder or CounterfactualFeatureBuilder()

    def find_neighbors(self, request: CounterfactualRequest | dict[str, Any], records: list[ReplayRecord] | None, limit: int = 50, threshold: float = 0.55) -> list[CounterfactualEvidence]:
        req = CounterfactualRequest.from_dict(request)
        request_fp = self.feature_builder.combined_fingerprint(req)
        evidence: list[CounterfactualEvidence] = []
        for record in records or []:
            item = ReplayRecord.from_dict(record)
            if not _has_observed_outcome(item):
                continue
            score = self.feature_builder.similarity(request_fp, self.feature_builder.combined_fingerprint(item))
            if score < float(threshold):
                continue
            action = DecisionAction.from_dict(item.chosen_action) if item.chosen_action else DecisionAction()
            evidence.append(
                CounterfactualEvidence(
                    evidence_id=_evidence_id(req.request_id, item.decision_id, score),
                    request_id=req.request_id,
                    source_decision_id=item.decision_id,
                    source_alpha_id=item.alpha_id,
                    action_id=action.action_id or None,
                    action_type=action.action_type or None,
                    similarity_score=score,
                    reward=item.reward,
                    success=item.success,
                    platform_sc_abs_max=item.platform_sc_abs_max,
                    quality_passed=item.quality_passed,
                    reason_codes=["estimated_not_observed", "observed_neighbor_outcome"],
                    raw_payload={"record_id": item.record_id, "decision_type": item.decision_type},
                )
            )
        return self.rank_neighbors(evidence)[: max(1, int(limit))]

    def rank_neighbors(self, evidence: list[CounterfactualEvidence] | None) -> list[CounterfactualEvidence]:
        return sorted([CounterfactualEvidence.from_dict(item) for item in (evidence or [])], key=lambda item: item.similarity_score, reverse=True)

    def filter_neighbors(self, evidence: list[CounterfactualEvidence] | None, threshold: float = 0.55, min_evidence: int = 30) -> list[CounterfactualEvidence]:
        items = [item for item in self.rank_neighbors(evidence) if item.similarity_score >= float(threshold)]
        if len(items) < int(min_evidence):
            return items
        return items


def _has_observed_outcome(record: ReplayRecord) -> bool:
    return record.outcome is not None and any(value is not None for value in (record.reward, record.success, record.platform_sc_abs_max, record.quality_passed))


def _evidence_id(request_id: str, decision_id: str, score: float) -> str:
    seed = f"{request_id}|{decision_id}|{score:.6f}"
    return "counterfactual_evidence:" + hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()[:24]
