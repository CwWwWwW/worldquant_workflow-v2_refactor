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


def test_experiment_layer_boundaries():
    offenders = []
    for path in ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        imports = _imports(path)
        text = path.read_text(encoding="utf-8-sig").lower()
        for banned in ("playwright", "wq_workflow.platform", "wq_workflow.browser_ops", "wq_workflow.strategy.budget_allocator"):
            if any(name == banned or name.startswith(banned + ".") for name in imports):
                offenders.append((path.name, banned))
        assert "page." not in text
        assert "browser." not in text
        assert "budgetallocator" not in text
        assert "multiarmed" not in text.replace("multi-armed", "")
    assert not offenders
