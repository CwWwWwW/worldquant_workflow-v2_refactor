from __future__ import annotations

import json
from pathlib import Path

from wq_workflow.strategy.evidence_loader import StrategyEvidenceLoader


def test_relative_status_path_resolves_from_root_not_cwd(monkeypatch, tmp_path):
    root = tmp_path / "project"
    status_dir = root / "runtime" / "status"
    status_dir.mkdir(parents=True)
    (status_dir / "strategy_scoreboard.json").write_text(json.dumps({"assignment_count": 3}), encoding="utf-8")
    other_cwd = tmp_path / "other"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)

    loader = StrategyEvidenceLoader(root_dir=root)
    assert loader._read_status_json("runtime/status/strategy_scoreboard.json") == {"assignment_count": 3}


def test_absolute_status_path_still_reads(tmp_path):
    path = tmp_path / "status.json"
    path.write_text(json.dumps({"ok": True}), encoding="utf-8")
    loader = StrategyEvidenceLoader(root_dir=tmp_path / "unused")
    assert loader._read_status_json(path) == {"ok": True}


def test_missing_relative_status_warns_and_does_not_write(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    loader = StrategyEvidenceLoader(root_dir=root)
    assert loader._read_status_json("runtime/status/missing.json") == {}
    assert "missing_status:missing" in loader.warnings
    assert not (root / "runtime" / "status" / "missing.json").exists()


def test_status_resolution_does_not_use_path_cwd(monkeypatch, tmp_path):
    root = tmp_path / "project"
    status_dir = root / "runtime" / "status"
    status_dir.mkdir(parents=True)
    (status_dir / "ok.json").write_text(json.dumps({"ok": 1}), encoding="utf-8")

    def fail_cwd(cls):
        raise AssertionError("Path.cwd must not be used for status resolution")

    monkeypatch.setattr(Path, "cwd", classmethod(fail_cwd))
    loader = StrategyEvidenceLoader(root_dir=root)
    assert loader._read_status_json("runtime/status/ok.json") == {"ok": 1}
