from types import SimpleNamespace

from wq_workflow.data.repositories import RepositoryBundle
from wq_workflow.offline.counterfactual import CounterfactualEstimator


def _cfg(min_count=2):
    return SimpleNamespace(support_min_action_count=min_count, offline_replay_max_decisions=100)


def test_counterfactual_sufficient_support_returns_estimate(tmp_path):
    repos = RepositoryBundle.from_storage(db_path=tmp_path / "workflow.db")
    for i, reward in enumerate([1.0, 0.5]):
        did = repos.decision.insert_decision_snapshot(decision_id=f"d{i}", decision_type="policy_action", context={"mutation_type": "m1"}, chosen_action={"action_id": "a1"})
        repos.decision.insert_decision_outcome(decision_id=did, decision_type="policy_action", reward_delta=reward, success=True, platform_sc_abs_max=0.1)
    result = CounterfactualEstimator(repos, _cfg(), None).estimate_action_outcome({"mutation_type": "m1"}, {"action_id": "a1"}, "policy_action")
    assert result["support_status"] == "sufficient"
    assert result["support_count"] == 2
    assert result["estimated_reward_delta"] == 0.75
    assert result["uses_real_unexecuted_reward"] is False


def test_counterfactual_insufficient_support_is_conservative(tmp_path):
    repos = RepositoryBundle.from_storage(db_path=tmp_path / "workflow.db")
    result = CounterfactualEstimator(repos, _cfg(min_count=3), None).estimate_policy_action_outcome({}, {"action_id": "missing"})
    assert result["support_status"] == "insufficient"
    assert result["estimated_reward_delta"] == 0.0
    assert result["confidence"] == 0.0


def test_confidence_increases_with_support(tmp_path):
    repos = RepositoryBundle.from_storage(db_path=tmp_path / "workflow.db")
    did = repos.decision.insert_decision_snapshot(decision_id="d1", decision_type="policy_action", chosen_action={"action_id": "a1"})
    repos.decision.insert_decision_outcome(decision_id=did, decision_type="policy_action", reward_delta=1.0, success=True)
    result = CounterfactualEstimator(repos, _cfg(min_count=3), None).estimate_policy_action_outcome({}, {"action_id": "a1"})
    assert 0.0 < result["confidence"] < 0.25
