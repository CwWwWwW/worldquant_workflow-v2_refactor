from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "clean_release.py"


def _write(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_project(tmp_path: Path) -> Path:
    _write(tmp_path / "README.md", "readme")
    _write(tmp_path / "config.example.json", "{}")
    _write(tmp_path / "requirements.txt", "pytest")
    _write(tmp_path / "tests" / "test_keep.py", "def test_keep(): pass")
    _write(tmp_path / "tools" / "keep.py", "print('keep')")
    _write(tmp_path / "wq_workflow" / "__init__.py", "")

    _write(tmp_path / "__pycache__" / "root.pyc", "cache")
    _write(tmp_path / "wq_workflow" / "__pycache__" / "mod.pyc", "cache")
    _write(tmp_path / ".pytest_cache" / "README.md", "cache")
    _write(tmp_path / ".ruff_cache" / "x", "cache")
    _write(tmp_path / "logs" / "workflow.log", "log")
    _write(tmp_path / "ui_logs" / "ui.log", "log")
    _write(tmp_path / "migration_logs" / "migration.log", "log")
    _write(tmp_path / "runtime" / "db" / "workflow.db", "db")
    _write(tmp_path / "runtime" / "models" / "model.bin", "model")
    _write(tmp_path / "runtime" / "logs" / "runtime.log", "log")
    _write(tmp_path / "scratch.tmp", "tmp")
    _write(tmp_path / "scratch.bak", "bak")
    _write(tmp_path / ".coverage", "coverage")
    return tmp_path


def test_clean_release_dry_run_does_not_delete_targets(tmp_path):
    project = _make_project(tmp_path)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(project)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Dry-run only" in result.stdout
    assert "DRY-RUN" in result.stdout
    assert (project / ".pytest_cache").exists()
    assert (project / "logs" / "workflow.log").exists()
    assert (project / "runtime" / "db" / "workflow.db").exists()


def test_clean_release_apply_removes_artifacts_and_keeps_project_files(tmp_path):
    project = _make_project(tmp_path)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(project), "--apply"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Clean completed" in result.stdout

    assert not (project / "__pycache__").exists()
    assert not (project / "wq_workflow" / "__pycache__").exists()
    assert not (project / ".pytest_cache").exists()
    assert not (project / ".ruff_cache").exists()
    assert not (project / "ui_logs").exists()
    assert not (project / "migration_logs").exists()
    assert not (project / "scratch.tmp").exists()
    assert not (project / "scratch.bak").exists()
    assert not (project / ".coverage").exists()
    assert not (project / "runtime" / "models").exists()
    assert not (project / "runtime" / "logs" / "runtime.log").exists()
    assert not (project / "runtime" / "db" / "workflow.db").exists()

    assert (project / "README.md").exists()
    assert (project / "config.example.json").exists()
    assert (project / "requirements.txt").exists()
    assert (project / "tests" / "test_keep.py").exists()
    assert (project / "tools" / "keep.py").exists()
    assert (project / "wq_workflow" / "__init__.py").exists()

    assert (project / "runtime" / ".gitkeep").exists()
    assert (project / "runtime" / "db" / ".gitkeep").exists()
    assert (project / "runtime" / "logs" / ".gitkeep").exists()
    assert (project / "logs" / ".gitkeep").exists()
