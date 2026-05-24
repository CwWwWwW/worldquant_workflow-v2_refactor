from __future__ import annotations

from typing import Any

from wq_workflow.learning.ml.availability import get_ml_dependency_status, require_sklearn_ensemble
from wq_workflow.learning.ml.evaluation import build_evaluation_report, regression_metrics, validation_gate
from wq_workflow.learning.ml.training_utils import build_xy_from_samples, load_task_samples, safe_train_result, split_train_validation


class SCTrainer:
    def __init__(self, *, storage: Any | None = None, model_registry: Any | None = None, config: Any | None = None, logger: Any | None = None, repository: Any | None = None) -> None:
        self.storage = storage
        self.model_registry = model_registry
        self.config = config
        self.logger = logger
        self.repository = repository
        self.db_path = getattr(getattr(storage, "config", None), "db_path", None)

    def train_if_ready(self) -> dict[str, Any]:
        return self.train()

    def train(self) -> dict[str, Any]:
        try:
            if not bool(getattr(self.config, "enable_sc_model_training", True)):
                return safe_train_result(status="disabled", reason="training_disabled")
            if not bool(getattr(self.config, "ml_allow_sklearn", True)):
                return safe_train_result(status="skipped", reason="sklearn_disabled")
            status = get_ml_dependency_status()
            if not status.sklearn_model_available:
                return safe_train_result(status="skipped", reason="dependency_unavailable")
            samples = load_task_samples("sc", repository=self.repository, storage=self.storage, db_path=self.db_path, limit=10000)
            min_samples = int(getattr(self.config, "sc_learning_min_samples", getattr(self.config, "ml_min_samples", 200)) or 200)
            if len(samples) < min_samples:
                return safe_train_result(status="not_enough_samples", reason="not_enough_samples", sample_count=len(samples), min_samples=min_samples)
            x, y, feature_names = build_xy_from_samples(samples, "platform_sc_abs_max")
            if x is None or y is None or feature_names is None:
                return safe_train_result(status="skipped", reason="dependency_unavailable", sample_count=len(samples))
            if len(y) < min_samples:
                return safe_train_result(status="not_enough_samples", reason="not_enough_labeled_samples", sample_count=len(y), min_samples=min_samples)
            ensemble = require_sklearn_ensemble()
            if ensemble is None:
                return safe_train_result(status="skipped", reason="dependency_unavailable", sample_count=len(y))
            seed = int(getattr(self.config, "ml_random_seed", 42) or 42)
            ratio = float(getattr(self.config, "ml_validation_ratio", 0.2) or 0.2)
            x_train, x_val, y_train, y_val = split_train_validation(x, y, ratio, seed)
            model = ensemble.RandomForestRegressor(n_estimators=50, random_state=seed)
            model.fit(x_train, y_train)
            metrics: dict[str, Any] = {"sample_count": int(len(y)), "train_sample_count": int(len(y)), "validation_size": int(len(y_val) if hasattr(y_val, "__len__") else 0)}
            if hasattr(y_val, "__len__") and len(y_val):
                pred = model.predict(x_val)
                metrics.update(regression_metrics(y_val, pred))
                metrics["sample_count"] = int(len(y))
            else:
                metrics.update({"mae": 0.0, "rmse": 0.0})
            report = build_evaluation_report("sc", metrics, self.config)
            active = False
            model_version = ""
            if self.model_registry:
                from wq_workflow.learning.ml.feature_schema import SimpleFeatureSchema
                schema = SimpleFeatureSchema(feature_names=list(feature_names), defaults={name: 0.0 for name in feature_names})
                meta = self.model_registry.save_model_version("sc", model, schema, train_sample_count=len(y), evaluation=report, model_type="RandomForestRegressor", raw_payload={"trainer": "SCTrainer"})
                if meta and bool(meta.get("ok", True)):
                    model_version = str(meta.get("model_version") or "")
                    gate = validation_gate("sc", metrics, self.config)
                    if gate.get("passed"):
                        active = bool(self.model_registry.activate_model("sc", model_version, reason="validation_passed"))
            return safe_train_result(trained=True, status="activated" if active else "trained_not_active", reason="" if active else "validation_failed", sample_count=len(y), metrics=metrics, model_version=model_version, active=active, evaluation=report)
        except Exception as exc:
            if self.logger:
                try:
                    self.logger.warning("SC training skipped: %s", exc)
                except Exception:
                    pass
            return safe_train_result(status="training_error", reason="training_error", error=str(exc))
