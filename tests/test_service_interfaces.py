from __future__ import annotations


def test_platform_service_interface():
    from wq_workflow.platform.service import PlatformService

    for name in ["submit_backtest", "wait_result", "parse_result", "collect_sc"]:
        assert callable(getattr(PlatformService, name))


def test_repository_interfaces():
    from wq_workflow.data.repositories import CandidateRepository, IterationRepository, MLRepository

    for name in ["save_candidate", "load_candidates", "select_parent_candidates", "update_candidate", "rebuild_from_sqlite_if_json_broken"]:
        assert callable(getattr(CandidateRepository, name))
    for name in ["append_iteration", "load_recent_iterations", "append_workflow_event"]:
        assert callable(getattr(IterationRepository, name))
    for name in ["insert_training_sample", "load_training_samples", "audit_prediction"]:
        assert callable(getattr(MLRepository, name))


def test_evaluation_and_learning_interfaces():
    from wq_workflow.evaluation import QualityService, RewardService, SCService, SuccessDetector
    from wq_workflow.learning.base import LearningTaskService

    assert callable(getattr(QualityService, "evaluate"))
    assert callable(getattr(RewardService, "compute"))
    assert callable(getattr(SCService, "resolve"))
    assert callable(getattr(SuccessDetector, "detect_backtest_success"))
    for name in ["record_sample", "maybe_train", "predict", "audit_prediction"]:
        assert callable(getattr(LearningTaskService, name))
