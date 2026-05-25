from wq_workflow.offline.replay_repository import ReplayRepository
from wq_workflow.offline.schema import DecisionAction, ReplayComparison, ReplayPolicyDecision, ReplayPolicyMetrics, ReplayRun


def test_replay_repository_save_and_list_all(tmp_path):
    repo = ReplayRepository(db_path=tmp_path / "workflow.db")
    assert repo.initialize()["ok"]
    run = ReplayRun(replay_run_id="r1", name="test", policies=["legacy"])
    assert repo.save_replay_run(run)["ok"]
    assert repo.get_replay_run("r1").name == "test"
    assert repo.list_replay_runs()[0].replay_run_id == "r1"
    decision = ReplayPolicyDecision(policy_decision_id="pd1", replay_run_id="r1", decision_id="d1", policy_name="legacy", selected_action=DecisionAction(action_id="a1"), observable_outcome=True, reward=1.0)
    repo.save_policy_decision(decision)
    repo.save_policy_decision(decision)
    assert len(repo.list_policy_decisions("r1")) == 1
    metrics = ReplayPolicyMetrics(replay_run_id="r1", policy_name="legacy", sample_count=1, observable_count=1, coverage_rate=1.0)
    repo.save_policy_metrics(metrics)
    repo.save_policy_metrics(metrics)
    assert len(repo.list_policy_metrics("r1")) == 1
    comparison = ReplayComparison(comparison_id="c1", replay_run_id="r1", baseline_policy="legacy", challenger_policy="model_choice")
    repo.save_comparison(comparison)
    repo.save_comparison(comparison)
    assert len(repo.list_comparisons("r1")) == 1
