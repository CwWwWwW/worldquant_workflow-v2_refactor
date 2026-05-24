import subprocess
import sys


def test_check_ml_dependencies_returns_within_timeout():
    result = subprocess.run([sys.executable, "tools/check_ml_dependencies.py"], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0
    assert "sklearn_model_available" in result.stdout


def test_check_ml_registry_returns_within_timeout_without_platform():
    result = subprocess.run([sys.executable, "tools/check_ml_registry.py"], capture_output=True, text=True, timeout=15)
    assert result.returncode in {0, 1}
    assert "issues" in result.stdout
