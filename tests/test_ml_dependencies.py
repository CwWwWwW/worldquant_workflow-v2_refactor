from wq_workflow.learning.ml.availability import (
    get_ml_dependency_status,
    require_joblib,
    require_numpy,
    require_sklearn_ensemble,
    require_sklearn_metrics,
    require_sklearn_model_selection,
)


def test_ml_dependency_helpers_do_not_raise():
    status = get_ml_dependency_status()
    assert isinstance(status.numpy_available, bool)
    assert isinstance(status.core_available, bool)
    assert isinstance(status.pandas_available, bool)
    np = require_numpy()
    joblib = require_joblib()
    ensemble = require_sklearn_ensemble()
    metrics = require_sklearn_metrics()
    model_selection = require_sklearn_model_selection()
    assert np is None or hasattr(np, "array")
    assert joblib is None or hasattr(joblib, "dump")
    assert ensemble is None or hasattr(ensemble, "RandomForestRegressor")
    assert ensemble is None or "RandomForestRegressor" in ensemble
    assert metrics is None or hasattr(metrics, "mean_absolute_error")
    assert metrics is None or "mean_absolute_error" in metrics
    assert model_selection is None or hasattr(model_selection, "train_test_split")
