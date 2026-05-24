import subprocess
import sys


def test_ml_tools_run():
    assert subprocess.run([sys.executable, "tools/check_ml_dependencies.py"], capture_output=True, text=True).returncode == 0
    assert subprocess.run([sys.executable, "tools/show_ml_registry.py"], capture_output=True, text=True).returncode == 0
    assert subprocess.run([sys.executable, "tools/train_ml_models.py", "--task", "sc"], capture_output=True, text=True).returncode == 0
