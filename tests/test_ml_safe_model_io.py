from wq_workflow.learning.ml import safe_model_io
from wq_workflow.learning.ml.availability import require_joblib


def test_json_helpers_and_missing_model(tmp_path):
    path = tmp_path / "nested" / "payload.json"
    assert safe_model_io.write_json(path, {"a": 1}) is True
    assert safe_model_io.read_json(path) == {"a": 1}
    assert safe_model_io.read_json(tmp_path / "missing.json") is None
    assert safe_model_io.load_model(tmp_path / "missing.joblib") is None


def test_save_model_degrades_when_joblib_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(safe_model_io, "require_joblib", lambda: None)
    assert safe_model_io.save_model({"x": 1}, tmp_path / "m.joblib") is False
    assert safe_model_io.load_model(tmp_path / "m.joblib") is None


def test_save_and_load_model_when_joblib_available(tmp_path):
    if require_joblib() is None:
        return
    path = tmp_path / "m.joblib"
    assert safe_model_io.save_model({"x": [1, 2]}, path) is True
    assert safe_model_io.load_model(path) == {"x": [1, 2]}


def test_active_model_pointer_helpers(tmp_path):
    assert safe_model_io.save_active_model_pointer("task", {"model_version": "v1"}, model_root=tmp_path) is True
    assert safe_model_io.load_active_model_pointer("task", model_root=tmp_path)["model_version"] == "v1"
