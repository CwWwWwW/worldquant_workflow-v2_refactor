from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MLTrainingSample:
    sample_id: str
    task_name: str
    alpha_id: str | None
    features: dict[str, Any]
    label: dict[str, Any]
    context: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class MLPrediction:
    task_name: str
    alpha_id: str | None
    model_version: str = ""
    prediction: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None
    final_decision: str = ""
    final_source: str = ""
    features: dict[str, Any] = field(default_factory=dict)


@dataclass
class MLModelMetadata:
    model_id: str
    task_name: str
    model_version: str
    model_path: str
    feature_schema_json: str = ""
    train_sample_count: int = 0
    validation_metric_json: str = ""
    is_active: bool = False
    created_at: str = ""
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class MLTaskConfig:
    task_name: str
    enabled: bool = True
    training_enabled: bool = True
    prediction_enabled: bool = True
    decision_enabled: bool = False
    min_samples: int = 200
    validation_ratio: float = 0.2
    min_confidence: float = 0.65
    raw_payload: dict[str, Any] = field(default_factory=dict)
