from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any


class _LazyImportMap(dict):
    """Small compatibility wrapper: supports both dict and attribute access."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


@dataclass(frozen=True)
class MLDependencyStatus:
    numpy_available: bool
    sklearn_available: bool
    joblib_available: bool
    pandas_available: bool = False

    @property
    def core_available(self) -> bool:
        return self.numpy_available

    @property
    def sklearn_model_available(self) -> bool:
        return self.numpy_available and self.sklearn_available and self.joblib_available


@lru_cache(maxsize=1)
def get_ml_dependency_status() -> MLDependencyStatus:
    def has_module(name: str) -> bool:
        try:
            __import__(name)
            return True
        except Exception:
            return False

    return MLDependencyStatus(
        numpy_available=has_module("numpy"),
        sklearn_available=has_module("sklearn"),
        joblib_available=has_module("joblib"),
        pandas_available=has_module("pandas"),
    )


def require_numpy() -> Any | None:
    try:
        import numpy as np
        return np
    except Exception:
        return None


def require_joblib() -> Any | None:
    try:
        import joblib
        return joblib
    except Exception:
        return None


def require_sklearn_ensemble() -> Any | None:
    try:
        from sklearn.ensemble import (
            HistGradientBoostingClassifier,
            HistGradientBoostingRegressor,
            RandomForestClassifier,
            RandomForestRegressor,
        )
        return _LazyImportMap(
            RandomForestRegressor=RandomForestRegressor,
            RandomForestClassifier=RandomForestClassifier,
            HistGradientBoostingRegressor=HistGradientBoostingRegressor,
            HistGradientBoostingClassifier=HistGradientBoostingClassifier,
        )
    except Exception:
        return None


def require_sklearn_metrics() -> Any | None:
    try:
        from sklearn.metrics import mean_absolute_error, mean_squared_error, precision_score, recall_score
        return _LazyImportMap(
            mean_absolute_error=mean_absolute_error,
            mean_squared_error=mean_squared_error,
            precision_score=precision_score,
            recall_score=recall_score,
        )
    except Exception:
        return None


def require_sklearn_model_selection() -> Any | None:
    try:
        from sklearn.model_selection import train_test_split
        return _LazyImportMap(train_test_split=train_test_split)
    except Exception:
        return None



def require_sklearn_neighbors() -> Any | None:
    try:
        from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
        return _LazyImportMap(
            KNeighborsClassifier=KNeighborsClassifier,
            KNeighborsRegressor=KNeighborsRegressor,
        )
    except Exception:
        return None
