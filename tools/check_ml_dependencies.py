from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wq_workflow.learning.ml.availability import get_ml_dependency_status


def main() -> int:
    status = get_ml_dependency_status()
    print(f"numpy available: {status.numpy_available}")
    print(f"sklearn available: {status.sklearn_available}")
    print(f"joblib available: {status.joblib_available}")
    print(f"pandas available optional: {status.pandas_available}")
    print(f"sklearn_model_available: {status.sklearn_model_available}")
    if status.sklearn_model_available:
        print("recommendation: ML training and prediction are available.")
    else:
        print("recommendation: install numpy scikit-learn joblib for model training; workflow will degrade safely.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
