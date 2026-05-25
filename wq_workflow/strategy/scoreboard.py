from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from .evidence_loader import StrategyEvidenceLoader
from .registry import StrategyRegistry
from .schema import StrategyEvidence, StrategyScore, StrategyScoreboard, utc_now_iso
from .scorer import StrategyScorer


class StrategyScoreboardBuilder:
    def __init__(self, registry: StrategyRegistry, evidence_loader: StrategyEvidenceLoader, scorer: StrategyScorer, config: Any | None = None, logger: Any | None = None) -> None:
        self.registry = registry
        self.evidence_loader = evidence_loader
        self.scorer = scorer
        self.config = config
        self.logger = logger

    def build_scoreboard(self) -> StrategyScoreboard:
        self.registry.ensure_default_strategies()
        profiles = self.registry.list_profiles()
        evidence = self.evidence_loader.load_all_evidence()
        scores = self.rank_scores([self.scorer.score_strategy(profile, evidence) for profile in profiles])
        signals = []
        for profile in profiles:
            signals.extend(self.scorer.build_signals(profile, evidence))
        warnings = self.generate_warnings(scores, evidence)
        warnings.extend(getattr(self.evidence_loader, "warnings", []))
        return StrategyScoreboard(
            scoreboard_id=f"strategy_scoreboard:{uuid.uuid4().hex}",
            generated_at=utc_now_iso(),
            profiles=profiles,
            scores=scores,
            signals=signals,
            evidence_summary=self.summarize_evidence(evidence),
            warnings=list(dict.fromkeys(warnings))[-100:],
            raw_payload={"mode": getattr(self.config, "strategy_registry_mode", "advisory"), "advisory_only": True},
        )

    def rank_scores(self, scores: list[StrategyScore]) -> list[StrategyScore]:
        priority = {"keep_baseline": 0, "candidate_for_challenger": 1, "observe_more": 2, "keep_shadow": 3, "risk_limited": 4, "insufficient_evidence": 5, "blocked_by_governance": 6}
        return sorted([StrategyScore.from_dict(item) for item in scores], key=lambda s: (priority.get(s.recommendation, 9), -float(s.total_score), s.strategy_id))

    def summarize_evidence(self, evidence: list[StrategyEvidence]) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "experiment": {"count": 0, "sample_count": 0},
            "replay": {"count": 0, "sample_count": 0},
            "counterfactual": {"count": 0, "sample_count": 0, "estimated_not_observed": True},
            "governance": {"count": 0, "sample_count": 0},
            "ml": {"count": 0, "sample_count": 0},
            "legacy": {"count": 0, "sample_count": 0},
        }
        for item in evidence:
            ev = StrategyEvidence.from_dict(item)
            bucket = "legacy"
            if ev.evidence_type.startswith("experiment"):
                bucket = "experiment"
            elif ev.evidence_type.startswith("replay"):
                bucket = "replay"
            elif ev.evidence_type.startswith("counterfactual"):
                bucket = "counterfactual"
            elif ev.evidence_type.startswith("governance"):
                bucket = "governance"
            elif ev.evidence_type == "ml_registry":
                bucket = "ml"
            summary[bucket]["count"] += 1
            summary[bucket]["sample_count"] += max(0, int(ev.sample_count or 0))
        return summary

    def generate_warnings(self, scores: list[StrategyScore], evidence: list[StrategyEvidence]) -> list[str]:
        warnings: list[str] = []
        if not any(item.evidence_type.startswith("replay") for item in evidence):
            warnings.append("replay_evidence_missing")
        if not any(item.evidence_type.startswith("counterfactual") for item in evidence):
            warnings.append("counterfactual_evidence_missing")
        if any(score.confidence == "insufficient" for score in scores):
            warnings.append("one_or_more_strategies_have_insufficient_evidence")
        if any(score.risk_level == "blocked" for score in scores):
            warnings.append("one_or_more_strategies_blocked_by_governance")
        for path_attr, warning in (("offline_replay_status_path", "offline_replay_report_missing"), ("counterfactual_status_path", "counterfactual_report_missing")):
            path_value = getattr(self.config, path_attr, None)
            if path_value:
                path = Path(path_value)
                if not path.is_absolute():
                    path = Path.cwd() / path
                if not path.exists():
                    warnings.append(warning)
        return list(dict.fromkeys(warnings))
