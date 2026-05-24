from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "wq_workflow"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def modules_under(rel: str):
    for path in (ROOT / rel).rglob("*.py"):
        if "__pycache__" not in path.parts:
            yield path


def assert_no_import_prefix(rel: str, banned_prefixes: tuple[str, ...]):
    offenders = []
    for path in modules_under(rel):
        for name in imported_modules(path):
            if any(name == banned or name.startswith(banned + ".") for banned in banned_prefixes):
                offenders.append((str(path.relative_to(ROOT)), name))
    assert not offenders


def test_workflow_does_not_import_sqlite_or_playwright():
    assert_no_import_prefix("workflow", ("sqlite3", "playwright"))


def test_learning_does_not_import_playwright():
    assert_no_import_prefix("learning", ("playwright",))


def test_evaluation_does_not_import_sqlite_or_playwright():
    assert_no_import_prefix("evaluation", ("sqlite3", "playwright"))


def test_data_does_not_import_playwright():
    assert_no_import_prefix("data", ("playwright",))


def test_cli_package_does_not_import_browser_or_sqlite_directly():
    assert_no_import_prefix("cli", ("sqlite3", "playwright"))
