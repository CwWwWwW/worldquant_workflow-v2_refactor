from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "wq_workflow" / "experiment"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_experiment_budget_boundaries():
    offenders = []
    banned_imports = ("playwright", "wq_workflow.platform", "wq_workflow.browser_ops", "wq_workflow.candidate_pool")
    for path in ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8-sig").lower()
        imports = _imports(path)
        for banned in banned_imports:
            if any(name == banned or name.startswith(banned + ".") for name in imports):
                offenders.append((path.name, banned))
        assert "page." not in text
        assert "browser." not in text
        assert "submit" not in text or path.name == "README.md"
        assert "hard_budget" not in text
    assert not offenders
