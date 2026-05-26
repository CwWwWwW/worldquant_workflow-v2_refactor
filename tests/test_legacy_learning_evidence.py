from __future__ import annotations

from wq_workflow.legacy_bridge.evidence import LegacyLearningEvidenceBuilder, LegacyLearningEvidenceReader, LegacyLearningEvidenceWriter


def test_learning_evidence_builder_observed_and_metrics(tmp_path):
    builder = LegacyLearningEvidenceBuilder()
    ev = builder.from_backtest_result(alpha_id="a", iteration=1, metrics={"sharpe": 1.2, "fitness": 0.9}, platform_sc={"abs_max": 0.4}, reward=0.7)
    assert ev.observed is True and ev.estimated is False and ev.sc_value == 0.4 and ev.reward == 0.7
    writer = LegacyLearningEvidenceWriter(tmp_path / "runtime/status/legacy_learning_evidence.jsonl")
    assert writer.append_evidence(ev)
    rows = LegacyLearningEvidenceReader(writer.path).read_tail(limit=10)
    assert rows[0].alpha_id == "a"
    assert LegacyLearningEvidenceReader(writer.path).summarize_by_type()["backtest_result"]["observed"] == 1


def test_failure_and_reward_evidence_do_not_mutate_inputs(tmp_path):
    candidate_pool = {"rows": [1]}
    builder = LegacyLearningEvidenceBuilder()
    reward = 0.5
    ev = builder.from_reward_update(reward=reward, raw_payload={"candidate_pool": candidate_pool})
    failure = builder.from_failure(failure_reason="bad", observed=True)
    assert reward == 0.5 and candidate_pool == {"rows": [1]}
    assert ev.reward == 0.5 and failure.observed is True and failure.estimated is False
