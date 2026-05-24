from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from wq_workflow.data.json_utils import json_loads_safe
from wq_workflow.learning.ml.availability import get_ml_dependency_status, require_numpy, require_sklearn_ensemble
from wq_workflow.learning.ml.evaluation import build_evaluation_report, classification_metrics, coverage_metrics, regression_metrics, validation_gate
from wq_workflow.learning.ml.feature_schema import SimpleFeatureSchema
from wq_workflow.learning.ml.training_utils import flatten_feature_dict, safe_train_result, split_train_validation


class PolicyTrainer:
    def __init__(self, *, storage: Any | None = None, model_registry: Any | None = None, config: Any | None = None, logger: Any | None = None, db_path: str | Path | None = None) -> None:
        self.storage = storage; self.model_registry = model_registry; self.config = config; self.logger = logger
        self.db_path = Path(db_path) if db_path is not None else getattr(getattr(storage, "config", None), "db_path", None)

    def _load_samples(self, limit: int = 10000) -> list[dict[str, Any]]:
        if not self.db_path: return []
        conn = None
        try:
            from wq_workflow.storage.schema import initialize_schema
            conn = sqlite3.connect(self.db_path); conn.row_factory = sqlite3.Row; initialize_schema(conn)
            rows = conn.execute("SELECT * FROM policy_training_samples ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
            out = []
            for r in rows:
                d = dict(r); ctx = json_loads_safe(d.get("context_json"), {}); chosen = json_loads_safe(d.get("chosen_action_json"), {})
                features = {}
                if isinstance(ctx, dict): features.update(ctx)
                if isinstance(chosen, dict):
                    for k, v in chosen.items(): features["action_" + str(k)] = v
                    features.setdefault("action_type", chosen.get("action_type") or chosen.get("type") or chosen.get("action_id"))
                    features.setdefault("legacy_score", chosen.get("legacy_score"))
                label = {"reward_delta": d.get("reward_delta"), "success": d.get("success")}
                sc = d.get("platform_sc_abs_max")
                if sc is not None: label["action_sc_risk"] = 1 if float(sc) >= float(getattr(self.config, "sc_risk_threshold", 0.7) or 0.7) else 0
                out.append({"features": features, "label": label, "action_type": features.get("action_type"), "alpha_id": d.get("alpha_id"), "raw": d})
            return out
        except Exception:
            return []
        finally:
            if conn is not None: conn.close()

    def train_if_ready(self) -> dict[str, Any]: return self.train()

    def train(self) -> dict[str, Any]:
        try:
            if not bool(getattr(self.config, "enable_policy_model_training", False)):
                return safe_train_result(status="disabled", reason="training_disabled")
            if not bool(getattr(self.config, "ml_allow_sklearn", True)):
                return safe_train_result(status="skipped", reason="sklearn_disabled")
            if not get_ml_dependency_status().sklearn_model_available:
                return safe_train_result(status="skipped", reason="dependency_unavailable")
            np = require_numpy(); ensemble = require_sklearn_ensemble()
            if np is None or ensemble is None: return safe_train_result(status="skipped", reason="dependency_unavailable")
            samples = self._load_samples(); min_samples = int(getattr(self.config, "policy_learning_min_samples", 200) or 200)
            labeled = [s for s in samples if (s.get("label") or {}).get("reward_delta") is not None]
            if len(labeled) < min_samples:
                return safe_train_result(status="not_enough_samples", reason="not_enough_samples", sample_count=len(labeled), min_samples=min_samples)
            flat = [flatten_feature_dict(s.get("features") or {}) for s in labeled]; names = sorted({k for row in flat for k in row})
            x = np.asarray([[row.get(n, 0.0) for n in names] for row in flat], dtype=float); y = np.asarray([float((s.get("label") or {}).get("reward_delta") or 0.0) for s in labeled], dtype=float)
            seed = int(getattr(self.config, "ml_random_seed", 42) or 42); ratio = float(getattr(self.config, "ml_validation_ratio", 0.2) or 0.2)
            xtr, xva, ytr, yva = split_train_validation(np.nan_to_num(x), np.nan_to_num(y), ratio, seed)
            reward_model = ensemble.RandomForestRegressor(n_estimators=50, random_state=seed); reward_model.fit(xtr, ytr); models = {"reward_regressor": reward_model}
            metrics: dict[str, Any] = {"sample_count": len(labeled), "train_sample_count": len(labeled), "action_coverage": coverage_metrics([s.get("action_type") for s in labeled]).get("coverage")}
            if hasattr(yva, "__len__") and len(yva):
                rm = regression_metrics(yva, reward_model.predict(xva)); metrics.update(rm); metrics["reward_mae"] = rm.get("mae"); metrics["sample_count"] = len(labeled); metrics["action_coverage"] = coverage_metrics([s.get("action_type") for s in labeled]).get("coverage")
            success_rows = [(i, s) for i, s in enumerate(labeled) if (s.get("label") or {}).get("success") is not None]
            if len(success_rows) >= 2 and len({int((s.get("label") or {}).get("success") or 0) for _, s in success_rows}) >= 2:
                idx = [i for i, _ in success_rows]; ys = np.asarray([int((s.get("label") or {}).get("success") or 0) for _, s in success_rows], dtype=int); xs = x[idx]
                xtr2, xva2, ytr2, yva2 = split_train_validation(xs, ys, ratio, seed); clf = ensemble.RandomForestClassifier(n_estimators=50, random_state=seed); clf.fit(xtr2, ytr2); models["success_classifier"] = clf
                if hasattr(yva2, "__len__") and len(yva2):
                    cm = classification_metrics(yva2, clf.predict(xva2)); metrics["success_recall"] = cm.get("recall")
            report = build_evaluation_report("policy", metrics, self.config)
            active = False; version = ""
            if self.model_registry:
                meta = self.model_registry.save_model_version("policy", {"models": models}, SimpleFeatureSchema(feature_names=names), train_sample_count=len(labeled), evaluation=report, model_type="policy_random_forest", raw_payload={"trainer": "PolicyTrainer"})
                if meta and bool(meta.get("ok", True)):
                    version = str(meta.get("model_version") or "")
                    if validation_gate("policy", metrics, self.config).get("passed"):
                        active = bool(self.model_registry.activate_model("policy", version, reason="validation_passed"))
            return safe_train_result(trained=True, status="activated" if active else "trained_not_active", reason="" if active else "validation_failed", sample_count=len(labeled), metrics=metrics, model_version=version, active=active, evaluation=report)
        except Exception as exc:
            return safe_train_result(status="training_error", reason="training_error", error=str(exc))
