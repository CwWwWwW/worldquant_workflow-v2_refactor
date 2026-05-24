from wq_workflow.learning.outcome.policy import OutcomeSimulatorPolicy
from wq_workflow.learning.parent.policy import ParentLearningPolicy
from wq_workflow.learning.policy.policy import ActionLearningPolicy
from wq_workflow.models import WorkflowConfig


def test_parent_policy_defaults_to_legacy():
    config = WorkflowConfig()
    policy = ParentLearningPolicy(config=config)
    parent = {"alpha_id": "p1"}
    assert policy.can_decide() is False
    assert policy.select_parent([parent]) == parent


def test_simulator_policy_never_skips_by_default():
    config = WorkflowConfig(enable_simulator_model_skip=False)
    result = OutcomeSimulatorPolicy(config=config).evaluate_candidate({"alpha_id": "a1"})
    assert result["should_skip"] is False


def test_action_policy_defaults_to_legacy_action():
    config = WorkflowConfig(enable_policy_model_decision=False)
    legacy_action = {"action_id": "legacy_mutation"}
    chosen = ActionLearningPolicy(config=config).choose_action([{"action_id": "model_action"}], legacy_action=legacy_action)
    assert chosen == legacy_action
