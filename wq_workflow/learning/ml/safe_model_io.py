from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .availability import require_joblib


def save_model(model: Any, path: str | Path, logger: Any | None = None) -> bool:
    joblib = require_joblib()
    if joblib is None:
        if logger:
            logger.warning("joblib unavailable; model not saved")
        return False
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, path)
        return True
    except Exception as exc:
        if logger:
            logger.warning("failed to save model %s: %s", path, exc)
        return False


def load_model(path: str | Path, logger: Any | None = None) -> Any | None:
    joblib = require_joblib()
    if joblib is None:
        if logger:
            logger.warning("joblib unavailable; model not loaded")
        return None
    try:
        path = Path(path)
        if not path.exists():
            return None
        return joblib.load(path)
    except Exception as exc:
        if logger:
            logger.warning("failed to load model %s: %s", path, exc)
        return None


def write_json(path: str | Path, payload: dict[str, Any], logger: Any | None = None) -> bool:
    try:
        try:
            from wq_workflow.data.json_utils import to_jsonable
            safe_payload = to_jsonable(payload if isinstance(payload, dict) else {})
        except Exception:
            safe_payload = payload if isinstance(payload, dict) else {}
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(safe_payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return True
    except Exception as exc:
        if logger:
            logger.warning("failed to write json %s: %s", path, exc)
        return False


def read_json(path: str | Path, logger: Any | None = None) -> dict[str, Any] | None:
    try:
        path = Path(path)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception as exc:
        if logger:
            logger.warning("failed to read json %s: %s", path, exc)
        return None


def _default_model_root() -> Path:
    from wq_workflow.paths import RUNTIME_DIR

    return RUNTIME_DIR / "models"


def save_active_model_pointer(task_name: str, payload: dict[str, Any], model_root: str | Path | None = None, logger: Any | None = None) -> bool:
    root = Path(model_root) if model_root is not None else _default_model_root()
    return write_json(root / str(task_name or "") / "active_model.json", payload if isinstance(payload, dict) else {}, logger)


def load_active_model_pointer(task_name: str, model_root: str | Path | None = None, logger: Any | None = None) -> dict[str, Any] | None:
    root = Path(model_root) if model_root is not None else _default_model_root()
    return read_json(root / str(task_name or "") / "active_model.json", logger)
