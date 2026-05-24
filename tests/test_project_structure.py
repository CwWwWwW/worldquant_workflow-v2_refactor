from __future__ import annotations

from pathlib import Path


def test_project_structure_exists():
    root = Path(__file__).resolve().parents[1]
    assert (root / "worldquant_auto_workflow.py").is_file()
    assert (root / "run_workflow.bat").is_file()
    assert (root / "config.example.json").is_file()
    assert (root / "requirements.txt").is_file()
    for rel in [
        "wq_workflow/app",
        "wq_workflow/cli",
        "wq_workflow/workflow",
        "wq_workflow/platform",
        "wq_workflow/alpha",
        "wq_workflow/evaluation",
        "wq_workflow/data",
        "wq_workflow/learning",
        "wq_workflow/offline",
        "wq_workflow/strategy",
        "wq_workflow/monitoring",
        "wq_workflow/adapters",
        "wq_workflow/core_types",
        "runtime",
        "logs",
    ]:
        assert (root / rel).exists(), rel
