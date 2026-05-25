
from types import SimpleNamespace
from wq_workflow.offline.repository import DecisionSnapshotRepository
from wq_workflow.offline.replay_repository import ReplayRepository
from wq_workflow.offline.schema import DecisionAction, DecisionOutcome, DecisionSnapshot, ReplayPolicyDecision, ReplayRun


def cfg(db_path, min_evidence=2):
    return SimpleNamespace(storage_db_path=str(db_path), enable_counterfactual_evaluation=False, counterfactual_auto_run=False, counterfactual_mode='advisory', counterfactual_status_path=str(db_path.parent/'counterfactual_report.json'), counterfactual_default_limit=100, counterfactual_min_evidence=min_evidence, counterfactual_min_effective_evidence=1, counterfactual_similarity_threshold=0.1, counterfactual_high_sc_abs_max_threshold=0.7, counterfactual_low_success_rate_threshold=0.02, counterfactual_medium_confidence_evidence=5, counterfactual_high_confidence_evidence=10, counterfactual_fail_open=True)


def seed_observed(db_path, count=3, reward=1.0, sc=0.1, success=True):
    repo=DecisionSnapshotRepository(db_path=db_path)
    action=DecisionAction(action_id='arm_a', action_type='arm', source='experiment', metadata={'operator_family':'op','behavior_family':'beh'})
    for i in range(count):
        repo.save_snapshot(DecisionSnapshot(decision_id=f'obs{i}', decision_type='experiment_arm_selection', alpha_id=f'a{i}', experiment_id='exp', arm_id='arm_a', chosen_action=action, features={'operator_family':'op'}, context={'behavior_family':'beh'}))
        repo.save_outcome(DecisionOutcome(outcome_id=f'o{i}', decision_id=f'obs{i}', alpha_id=f'a{i}', reward=reward, success=success, platform_sc_abs_max=sc, quality_passed=success))
    repo.save_snapshot(DecisionSnapshot(decision_id='no_outcome', decision_type='experiment_arm_selection', chosen_action=action))
    return action


def seed_replay_decision(db_path):
    action=seed_observed(db_path)
    repo=DecisionSnapshotRepository(db_path=db_path)
    actual=DecisionAction(action_id='actual', action_type='arm', source='actual')
    target=DecisionAction(action_id='arm_a', action_type='arm', source='experiment', metadata={'operator_family':'op','behavior_family':'beh'})
    repo.save_snapshot(DecisionSnapshot(decision_id='target_decision', decision_type='experiment_arm_selection', alpha_id='alpha_target', experiment_id='exp', arm_id='actual', chosen_action=actual, features={'operator_family':'op'}, context={'behavior_family':'beh','baseline_reward':0.0}))
    rrepo=ReplayRepository(db_path=db_path)
    rrepo.save_replay_run(ReplayRun(replay_run_id='run1', name='run'))
    pd=ReplayPolicyDecision(policy_decision_id='pd1', replay_run_id='run1', decision_id='target_decision', policy_name='experiment_choice', selected_action=target, selected_matches_actual=False, observable_outcome=False, reason_codes=['insufficient_counterfactual_evidence'])
    rrepo.save_policy_decision(pd)
    return pd
