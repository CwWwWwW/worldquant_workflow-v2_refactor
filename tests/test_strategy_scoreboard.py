from types import SimpleNamespace

from wq_workflow.strategy.evidence_loader import StrategyEvidenceLoader
from wq_workflow.strategy.registry import StrategyRegistry
from wq_workflow.strategy.scoreboard import StrategyScoreboardBuilder
from wq_workflow.strategy.schema import StrategyEvidence
from wq_workflow.strategy.scorer import StrategyScorer


class FakeLoader(StrategyEvidenceLoader):
    def __init__(self, evidence):
        self._evidence = evidence
        self.warnings = []
    def load_all_evidence(self):
        return self._evidence


def test_strategy_scoreboard_build_rank_summary_warnings():
    evidence = [StrategyEvidence(strategy_id="legacy_baseline", evidence_type="legacy_baseline", sample_count=1000, success_rate=0.8)]
    builder = StrategyScoreboardBuilder(StrategyRegistry(None, SimpleNamespace()), FakeLoader(evidence), StrategyScorer(SimpleNamespace()), SimpleNamespace())
    board = builder.build_scoreboard()
    assert len(board.scores) >= 9
    assert board.evidence_summary["legacy"]["sample_count"] == 1000
    assert "replay_evidence_missing" in board.warnings
    assert board.scores[0].recommendation == "keep_baseline"
