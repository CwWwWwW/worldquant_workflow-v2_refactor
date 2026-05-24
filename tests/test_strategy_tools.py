import subprocess
import sys
import os


def test_strategy_tools_help_runs():
    for script in [
        "tools/run_offline_replay.py",
        "tools/show_strategy_portfolio.py",
        "tools/promote_strategy.py",
        "tools/rollback_strategy.py",
    ]:
        result = subprocess.run([sys.executable, script, "--help"], capture_output=True, text=True)
        assert result.returncode == 0


def _env(tmp_path):
    env = os.environ.copy()
    env["WQ_STORAGE_DB_PATH"] = str(tmp_path / "workflow.db")
    return env


def test_run_offline_replay_and_show_strategy_portfolio(tmp_path):
    env = _env(tmp_path)
    replay = subprocess.run([sys.executable, "tools/run_offline_replay.py", "--task", "all"], capture_output=True, text=True, env=env)
    assert replay.returncode == 0
    assert '"parent"' in replay.stdout
    result = subprocess.run([sys.executable, "tools/show_strategy_portfolio.py"], capture_output=True, text=True, env=env)
    assert result.returncode == 0
    assert "legacy_champion" in result.stdout


def test_promote_strategy_not_eligible_does_not_promote(tmp_path):
    result = subprocess.run([sys.executable, "tools/promote_strategy.py", "--strategy-id", "parent_learning_challenger"], capture_output=True, text=True, env=_env(tmp_path))
    assert result.returncode != 0
    assert '"promoted": false' in result.stdout.lower()


def test_rollback_strategy_updates_role(tmp_path):
    env = _env(tmp_path)
    result = subprocess.run([sys.executable, "tools/rollback_strategy.py", "--to", "legacy_champion", "--reason", "test"], capture_output=True, text=True, env=env)
    assert result.returncode == 0
    assert '"rolled_back": true' in result.stdout.lower()
