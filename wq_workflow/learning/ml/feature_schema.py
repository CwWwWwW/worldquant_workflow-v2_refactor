from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FeatureSchema:
    schema_version: str
    feature_names: list[str]
    numeric_features: list[str] = field(default_factory=list)
    categorical_features: list[str] = field(default_factory=list)
    boolean_features: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __iter__(self):
        return iter(self.feature_names)

    def __len__(self) -> int:
        return len(self.feature_names)

    def transform_one(self, features: dict[str, Any] | None) -> list[float]:
        data = features if isinstance(features, dict) else {}
        return [self._to_float(data.get(name, 0.0)) for name in self.feature_names]

    def transform_many(self, rows: list[dict[str, Any]] | None) -> list[list[float]]:
        return [self.transform_one(row) for row in rows or []]

    def _to_float(self, value: Any) -> float:
        try:
            if value is None:
                return 0.0
            if isinstance(value, bool):
                return 1.0 if value else 0.0
            if hasattr(value, "item"):
                value = value.item()
            v = float(value)
            if v != v or v in {float("inf"), float("-inf")}:
                return 0.0
            return v
        except Exception:
            return 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "feature_names": list(self.feature_names),
            "numeric_features": list(self.numeric_features),
            "categorical_features": list(self.categorical_features),
            "boolean_features": list(self.boolean_features),
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "FeatureSchema":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            schema_version=str(data.get("schema_version") or "v1"),
            feature_names=[str(name) for name in (data.get("feature_names") or [])],
            numeric_features=[str(name) for name in (data.get("numeric_features") or [])],
            categorical_features=[str(name) for name in (data.get("categorical_features") or [])],
            boolean_features=[str(name) for name in (data.get("boolean_features") or [])],
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class SimpleFeatureSchema:
    feature_names: list[str] = field(default_factory=list)
    defaults: dict[str, float] = field(default_factory=dict)

    def transform_one(self, features: dict[str, Any] | None) -> list[float]:
        features = features if isinstance(features, dict) else {}
        values: list[float] = []
        for name in self.feature_names:
            raw = features.get(name, self.defaults.get(name, 0.0))
            try:
                if raw is None:
                    raw = self.defaults.get(name, 0.0)
                if isinstance(raw, bool):
                    value = 1.0 if raw else 0.0
                elif hasattr(raw, "item"):
                    value = float(raw.item())
                else:
                    value = float(raw)
            except (TypeError, ValueError):
                value = float(self.defaults.get(name, 0.0))
            if value != value or value in {float("inf"), float("-inf")}:
                value = float(self.defaults.get(name, 0.0))
            values.append(value)
        return values

    def transform_many(self, rows: list[dict[str, Any]] | None) -> list[list[float]]:
        return [self.transform_one(row) for row in rows or []]

    def to_dict(self) -> dict[str, Any]:
        return {"feature_names": list(self.feature_names), "defaults": dict(self.defaults)}

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "SimpleFeatureSchema":
        return cls.from_json(payload)

    def to_feature_schema(self, schema_version: str = "v1") -> FeatureSchema:
        return FeatureSchema(
            schema_version=schema_version,
            feature_names=list(self.feature_names),
            numeric_features=list(self.feature_names),
            metadata={"defaults": dict(self.defaults)},
        )

    def to_json(self) -> str:
        return json.dumps({"feature_names": self.feature_names, "defaults": self.defaults}, ensure_ascii=False)

    @classmethod
    def from_json(cls, payload: str | dict[str, Any] | None) -> "SimpleFeatureSchema":
        if isinstance(payload, str):
            try:
                data = json.loads(payload)
            except Exception:
                data = {}
        elif isinstance(payload, dict):
            data = payload
        else:
            data = {}
        names = data.get("feature_names") if isinstance(data.get("feature_names"), list) else []
        defaults = data.get("defaults") if isinstance(data.get("defaults"), dict) else {}
        safe_defaults: dict[str, float] = {}
        for key, value in defaults.items():
            try:
                safe_defaults[str(key)] = float(value)
            except Exception:
                continue
        return cls(feature_names=[str(name) for name in names], defaults=safe_defaults)
