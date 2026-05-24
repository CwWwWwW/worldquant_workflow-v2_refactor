from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from wq_workflow.data.json_utils import json_loads_safe
from wq_workflow.time_utils import utc_now_strftime

from .availability import require_numpy, require_sklearn_model_selection
from .feature_schema import FeatureSchema, SimpleFeatureSchema


def hash_to_unit_float(value: Any) -> float:
    text = str(value or "")
    digest = hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:12]
    return int(digest, 16) / float(0xFFFFFFFFFFFF)


def hash_categorical_features(value: Any) -> float:
    return hash_to_unit_float(value)


def flatten_feature_dict(features: dict[str, Any] | None, *, prefix: str = "") -> dict[str, float]:
    out: dict[str, float] = {}
    if not isinstance(features, dict):
        return out
    for key, value in features.items():
        name = f"{prefix}{key}" if prefix else str(key)
        if isinstance(value, bool):
            out[name] = 1.0 if value else 0.0
        elif isinstance(value, (int, float)):
            try:
                out[name] = float(value)
            except Exception:
                continue
        elif isinstance(value, str):
            out[name + "_hash"] = hash_to_unit_float(value)
        elif isinstance(value, dict):
            # Flatten one level for representation summaries/features while keeping the matrix bounded.
            nested = flatten_feature_dict(value, prefix=name + ".")
            out.update(nested)
        else:
            continue
    return out


def clean_feature_matrix(x: Any) -> Any:
    np = require_numpy()
    if np is None:
        return x
    try:
        return np.nan_to_num(np.asarray(x, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
    except Exception:
        return x


def new_model_version(task_name: str) -> str:
    ts = utc_now_strftime("%Y%m%d_%H%M%S")
    return f"{str(task_name or 'model')}_v{ts}"


def has_enough_samples(samples: list[dict[str, Any]] | None, min_samples: int) -> bool:
    return len(samples or []) >= int(min_samples or 0)


def build_feature_schema(samples: list[dict[str, Any]] | None, schema_version: str = "v1") -> FeatureSchema:
    feature_names = sorted(
        {
            str(key)
            for sample in samples or []
            for key, value in ((sample or {}).get("features") or {}).items()
            if isinstance(value, (int, float, bool))
        }
    )
    return FeatureSchema(schema_version=schema_version, feature_names=feature_names, numeric_features=feature_names)


def build_xy_from_samples(samples: list[dict[str, Any]], label_key: str) -> tuple[Any, Any, FeatureSchema | None]:
    np = require_numpy()
    if np is None:
        return None, None, None
    flattened: list[dict[str, float]] = []
    labels: list[float] = []
    for sample in samples or []:
        features = flatten_feature_dict(sample.get("features") or {})
        label = (sample.get("label") or {}).get(label_key)
        if label is None:
            continue
        try:
            label_value = float(label)
        except Exception:
            continue
        flattened.append(features)
        labels.append(label_value)
    if not flattened:
        empty_schema = FeatureSchema(schema_version="v1", feature_names=[], numeric_features=[])
        return np.asarray([], dtype=float).reshape(0, 0), np.asarray([], dtype=float), empty_schema
    feature_names = sorted({k for row in flattened for k in row.keys()})
    rows = [[float(row.get(name) or 0.0) for name in feature_names] for row in flattened]
    x = np.asarray(rows, dtype=float)
    y = np.asarray(labels, dtype=float)
    x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)
    schema = FeatureSchema(schema_version="v1", feature_names=feature_names, numeric_features=feature_names, metadata={"source": "flatten_feature_dict"})
    return x, y, schema


def build_classification_y(samples: list[dict[str, Any]], label_key: str, *, threshold: float = 0.5) -> Any:
    np = require_numpy()
    if np is None:
        return None
    labels: list[int] = []
    for sample in samples or []:
        label = (sample.get("label") or {}).get(label_key)
        if label is None:
            continue
        try:
            labels.append(1 if float(label) >= threshold else 0)
        except Exception:
            continue
    return np.asarray(labels, dtype=int)


def split_train_validation(x: Any, y: Any, validation_ratio: float = 0.2, random_state: int = 42) -> tuple[Any, Any, Any, Any]:
    try:
        n = len(y)
    except Exception:
        n = 0
    if n < 2 or validation_ratio <= 0:
        return x, [], y, []
    model_selection = require_sklearn_model_selection()
    if model_selection is None:
        split = max(1, int(n * (1.0 - validation_ratio)))
        return x[:split], x[split:], y[:split], y[split:]
    try:
        return model_selection.train_test_split(x, y, test_size=validation_ratio, random_state=random_state)
    except Exception:
        split = max(1, int(n * (1.0 - validation_ratio)))
        return x[:split], x[split:], y[:split], y[split:]


def check_min_samples(samples_or_count: Any, min_samples: int) -> tuple[bool, int, int]:
    try:
        count = int(samples_or_count if isinstance(samples_or_count, int) else len(samples_or_count or []))
    except Exception:
        count = 0
    need = max(1, int(min_samples or 1))
    return count >= need, count, need


def build_feature_schema_from_samples(samples: list[dict[str, Any]]) -> SimpleFeatureSchema:
    flattened = [flatten_feature_dict((sample or {}).get("features") or {}) for sample in samples or []]
    feature_names = sorted({k for row in flattened for k in row.keys()})
    defaults = {name: 0.0 for name in feature_names}
    return SimpleFeatureSchema(feature_names=feature_names, defaults=defaults)


def safe_train_result(*, trained: bool = False, status: str | None = None, reason: str = "", sample_count: int = 0, metrics: dict[str, Any] | None = None, model_version: str = "", active: bool = False, error: str = "", **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "trained": bool(trained),
        "status": status or ("trained" if trained else "skipped"),
        "reason": reason,
        "sample_count": int(sample_count or 0),
        "metrics": metrics or {},
        "model_version": model_version or "",
        "active": bool(active),
    }
    if error:
        payload["error"] = error
    payload.update(extra)
    return payload


def _query_rows(db_path: str | Path, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    conn = None
    try:
        from wq_workflow.storage.schema import initialize_schema
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        initialize_schema(conn)
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    except Exception:
        return []
    finally:
        if conn is not None:
            conn.close()


def load_task_samples(task_name: str, *, repository: Any | None = None, storage: Any | None = None, db_path: str | Path | None = None, limit: int = 5000) -> list[dict[str, Any]]:
    if repository is not None:
        try:
            return repository.load_training_samples(task_name, limit=limit)
        except Exception:
            pass
    if db_path is None:
        db_path = getattr(getattr(storage, "config", None), "db_path", None)
    if db_path is None:
        return []
    task = str(task_name or "")
    if task == "sc":
        rows = _query_rows(db_path, "SELECT * FROM ml_training_samples WHERE task_name=? ORDER BY created_at DESC LIMIT ?", ("sc", max(1, int(limit))))
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append({"sample_id": row.get("sample_id"), "alpha_id": row.get("alpha_id"), "features": json_loads_safe(row.get("features_json"), {}), "label": json_loads_safe(row.get("label_json"), {}), "context": json_loads_safe(row.get("context_json"), {}), "raw": json_loads_safe(row.get("raw_payload"), {})})
        if out:
            return out
        rows = _query_rows(db_path, "SELECT * FROM sc_training_samples ORDER BY created_at DESC LIMIT ?", (max(1, int(limit)),))
        return [{"sample_id": r.get("sample_id"), "alpha_id": r.get("alpha_id"), "features": json_loads_safe(r.get("features_json"), {}), "label": json_loads_safe(r.get("label_json"), {"platform_sc_abs_max": r.get("platform_sc_abs_max")}), "context": json_loads_safe(r.get("context_json"), {}), "raw": json_loads_safe(r.get("raw_payload"), {})} for r in rows]
    return []


# Backward-compatible names used by phase-1 tests/code.
def train_validation_split(X: list[list[float]], y: list[float], validation_ratio: float = 0.2, random_state: int = 42) -> tuple[Any, Any, Any, Any]:
    return split_train_validation(X, y, validation_ratio, random_state)


def mean_absolute_error(y_true: Any, y_pred: Any) -> float | None:
    from .availability import require_sklearn_metrics
    metrics = require_sklearn_metrics()
    if metrics is None:
        return None
    try:
        return float(metrics.mean_absolute_error(y_true, y_pred))
    except Exception:
        return None


def as_matrix(rows: Any) -> Any:
    return clean_feature_matrix(rows)
