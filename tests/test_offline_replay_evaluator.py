from types import SimpleNamespace

from wq_workflow.data.repositories import RepositoryBundle
from wq_workflow.offline.replay import OfflineReplayEvaluator


class DummyRegistry:
    pass


def _cfg(**overrides):
    base = {
        "offline_replay_min_decisions": 1,
        "offline_replay_max_decisions": 100,
        "promotion_min_support_coverage": 0.0,
        "promotion_min_reward_improvement": -999.0,
        "promotion_max_sc_risk_delta": 999.0,
        "promotion_max_failure_rate_delta": 999.0,
        "support_min_action_count": 1,
        "support_min_context_count": 1,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_replay_match_uses_real_outcome_and_writes_report(tmp_path):
    repos = RepositoryBundle.from_storage(db_path=tmp_path / "workflow.db")
    did = repos.decision.insert_decision_snapshot(
        decision_id="d1",
        decision_type="policy_action",
        context={"mutation_type": "m1"},
        available_actions=[{"action_id": "a1"}],
        chosen_action={"action_id": "a1"},
        action_scores={"a1": 1.0},
    )
    repos.decision.insert_decision_outcome(decision_id=did, decision_type="policy_action", reward_delta=1.0, success=True)
    report = OfflineReplayEvaluator(repos, DummyRegistry(), _cfg(), None).evaluate_policy_model()
    assert report["sample_count"] == 1
    assert report["model_match_rate"] == 1.0
    assert report["estimated_reward_delta"] == 1.0
    assert repos.replay.latest_offline_replay_report(task_name="policy") is not None


def test_replay_mismatch_uses_counterfactual_not_fake_reward(tmp_path):
    repos = RepositoryBundle.from_storage(db_path=tmp_path / "workflow.db")
    did = repos.decision.insert_decision_snapshot(
        decision_id="legacy",
        decision_type="policy_action",
        context={"mutation_type": "m1"},
        available_actions=[{"action_id": "a1"}, {"action_id": "a2"}],
        chosen_action={"action_id": "a1"},
        action_scores={"a1": 0.1, "a2": 2.0},
    )
    repos.decision.insert_decision_outcome(decision_id=did, decision_type="policy_action", reward_delta=10.0, success=True)
    cf = repos.decision.insert_decision_snapshot(decision_id="cf", decision_type="policy_action", context={"mutation_type": "m1"}, chosen_action={"action_id": "a2"})
    repos.decision.insert_decision_outcome(decision_id=cf, decision_type="policy_action", reward_delta=0.25, success=False)
    report = OfflineReplayEvaluator(repos, DummyRegistry(), _cfg(), None).evaluate_policy_model()
    mismatch = next(d for d in report["details"] if d["decision_id"] == "legacy")
    assert mismatch["outcome_source"] == "counterfactual_conservative_estimate"
    assert report["estimated_reward_delta"] != 10.0
