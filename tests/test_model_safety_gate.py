from types import SimpleNamespace

from wq_workflow.data.repositories import RepositoryBundle
from wq_workflow.strategy.champion_challenger import ModelSafetyGate


class Registry:
    def __init__(self, validation=True, active=True):
        self.validation = validation
        self.active = active

    def get_model_metadata(self, task, version):
        return {"validation_passed": self.validation}

    def load_active_model(self, task):
        return {"model_version": "v1", "payload": {"validation_passed": self.validation}} if self.active else None


class Support:
    def __init__(self, passed=True):
        self.passed = passed

    def check_strategy_support(self, strategy_id):
        return {"support_pass": self.passed}


def _repos(tmp_path, replay_pass=True):
    repos = RepositoryBundle.from_storage(db_path=tmp_path / "workflow.db")
    repos.replay.insert_offline_replay_report({"task_name": "parent", "strategy_id": "parent_learning_challenger", "model_version": "v1", "replay_pass": replay_pass, "sample_count": 10})
    return repos


def test_safety_gate_failures_and_pass_write_report(tmp_path):
    assert "validation_fail" in ModelSafetyGate(_repos(tmp_path / "v"), SimpleNamespace(), None, Registry(False), Support(True)).evaluate("parent", "v1", "parent_learning_challenger")["reasons"]
    assert "replay_fail" in ModelSafetyGate(_repos(tmp_path / "r", False), SimpleNamespace(), None, Registry(True), Support(True)).evaluate("parent", "v1", "parent_learning_challenger")["reasons"]
    assert "support_fail" in ModelSafetyGate(_repos(tmp_path / "s"), SimpleNamespace(), None, Registry(True), Support(False)).evaluate("parent", "v1", "parent_learning_challenger")["reasons"]
    repos = _repos(tmp_path / "ok")
    result = ModelSafetyGate(repos, SimpleNamespace(), None, Registry(True), Support(True)).evaluate("parent", "v1", "parent_learning_challenger")
    assert result["safety_pass"] is True
    assert repos.replay.latest_model_safety_report(strategy_id="parent_learning_challenger")["safety_pass"] is True
