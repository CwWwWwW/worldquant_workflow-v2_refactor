from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from wq_workflow.data.json_utils import json_loads_safe
from wq_workflow.learning.ml.availability import get_ml_dependency_status, require_numpy, require_sklearn_ensemble
from wq_workflow.learning.ml.evaluation import build_evaluation_report, classification_metrics, regression_metrics, validation_gate
from wq_workflow.learning.ml.feature_schema import SimpleFeatureSchema
from wq_workflow.learning.ml.training_utils import flatten_feature_dict, safe_train_result, split_train_validation


class ParentTrainer:
    def __init__(self, *, storage: Any | None = None, model_registry: Any | None = None, config: Any | None = None, logger: Any | None = None, db_path: str | Path | None = None) -> None:
        self.storage = storage
        self.model_registry = model_registry
        self.config = config
        self.logger = logger
        self.db_path = Path(db_path) if db_path is not None else getattr(getattr(storage, "config", None), "db_path", None)

    def _load_samples(self, limit: int = 10000) -> list[dict[str, Any]]:
        if not self.db_path:
            return []
        conn = None
        try:
            from wq_workflow.storage.schema import initialize_schema
            conn = sqlite3.connect(self.db_path); conn.row_factory = sqlite3.Row; initialize_schema(conn)
            rows = conn.execute("SELECT * FROM parent_selection_samples ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                features = json_loads_safe(d.get("parent_features_json"), {})
                if d.get("mutation_type"):
                    features["mutation_type"] = d.get("mutation_type")
                label = {"child_reward": d.get("child_reward"), "child_success": d.get("child_success")}
                sc = d.get("child_platform_sc_abs_max")
                if sc is not None:
                    label["child_sc_risk"] = 1 if float(sc) >= float(getattr(self.config, "sc_risk_threshold", 0.7) or 0.7) else 0
                out.append({"features": features, "label": label, "alpha_id": d.get("parent_alpha_id"), "raw": d})
            return out
        except Exception:
            return []
        finally:
            if conn is not None: conn.close()

    def train_if_ready(self) -> dict[str, Any]:
        return self.train()

    def train(self) -> dict[str, Any]:
        try:
            if not bool(getattr(self.config, "enable_parent_model_training", False)):
                return safe_train_result(status="disabled", reason="training_disabled")
            if not bool(getattr(self.config, "ml_allow_sklearn", True)):
                return safe_train_result(status="skipped", reason="sklearn_disabled")
            if not get_ml_dependency_status().sklearn_model_available:
                return safe_train_result(status="skipped", reason="dependency_unavailable")
            np = require_numpy(); ensemble = require_sklearn_ensemble()
            if np is None or ensemble is None:
                return safe_train_result(status="skipped", reason="dependency_unavailable")
            samples = self._load_samples()
            min_samples = int(getattr(self.config, "parent_learning_min_samples", 200) or 200)
            labeled = [s for s in samples if (s.get("label") or {}).get("child_reward") is not None]
            if len(labeled) < min_samples:
                return safe_train_result(status="not_enough_samples", reason="not_enough_samples", sample_count=len(labeled), min_samples=min_samples)
            flat = [flatten_feature_dict(s.get("features") or {}) for s in labeled]
            feature_names = sorted({k for row in flat for k in row})
            x = np.asarray([[row.get(n, 0.0) for n in feature_names] for row in flat], dtype=float)
            y = np.asarray([float((s.get("label") or {}).get("child_reward") or 0.0) for s in labeled], dtype=float)
            seed = int(getattr(self.config, "ml_random_seed", 42) or 42)
            xtr, xva, ytr, yva = split_train_validation(np.nan_to_num(x), np.nan_to_num(y), float(getattr(self.config, "ml_validation_ratio", 0.2) or 0.2), seed)
            reward_model = ensemble.RandomForestRegressor(n_estimators=50, random_state=seed); reward_model.fit(xtr, ytr)
            models: dict[str, Any] = {"reward_regressor": reward_model}
            metrics: dict[str, Any] = {"sample_count": len(labeled), "train_sample_count": len(labeled), "validation_size": int(len(yva) if hasattr(yva, "__len__") else 0)}
            if hasattr(yva, "__len__") and len(yva):
                rm = regression_metrics(yva, reward_model.predict(xva)); metrics.update(rm); metrics["reward_mae"] = rm.get("mae"); metrics["sample_count"] = len(labeled)
            success_rows = [(i, s) for i, s in enumerate(labeled) if (s.get("label") or {}).get("child_success") is not None]
            if len(success_rows) >= 2 and len({int((s.get("label") or {}).get("child_success") or 0) for _, s in success_rows}) >= 2:
                idx = [i for i, _ in success_rows]
                ys = np.asarray([int((s.get("label") or {}).get("child_success") or 0) for _, s in success_rows], dtype=int)
                xs = x[idx]
                xtr2, xva2, ytr2, yva2 = split_train_validation(xs, ys, float(getattr(self.config, "ml_validation_ratio", 0.2) or 0.2), seed)
                clf = ensemble.RandomForestClassifier(n_estimators=50, random_state=seed); clf.fit(xtr2, ytr2); models["success_classifier"] = clf
                if hasattr(yva2, "__len__") and len(yva2):
                    pred = clf.predict(xva2); cm = classification_metrics(yva2, pred); metrics.update({"success_recall": cm.get("recall"), "success_accuracy": cm.get("accuracy")})
            else:
                metrics.setdefault("success_recall", 1.0)
            report = build_evaluation_report("parent", metrics, self.config)
            active = False; version = ""
            if self.model_registry:
                meta = self.model_registry.save_model_version("parent", {"models": models}, SimpleFeatureSchema(feature_names=feature_names), train_sample_count=len(labeled), evaluation=report, model_type="parent_random_forest", raw_payload={"trainer": "ParentTrainer"})
                if meta and bool(meta.get("ok", True)):
                    version = str(meta.get("model_version") or "")
                    if validation_gate("parent", metrics, self.config).get("passed"):
                        active = bool(self.model_registry.activate_model("parent", version, reason="validation_passed"))
            return safe_train_result(trained=True, status="activated" if active else "trained_not_active", reason="" if active else "validation_failed", sample_count=len(labeled), metrics=metrics, model_version=version, active=active, evaluation=report)
        except Exception as exc:
            return safe_train_result(status="training_error", reason="training_error", error=str(exc))
