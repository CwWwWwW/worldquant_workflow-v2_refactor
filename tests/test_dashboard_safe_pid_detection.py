from __future__ import annotations

import sys
from types import SimpleNamespace

from wq_workflow.dashboard import status_aggregator as sa
from wq_workflow.dashboard.status_aggregator import DashboardStatusAggregator


def test_process_running_does_not_call_os_kill(monkeypatch):
    monkeypatch.setattr(sa.os, "kill", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("os.kill must not be called")), raising=False)
    monkeypatch.setitem(sys.modules, "psutil", SimpleNamespace(pid_exists=lambda pid: False))
    assert sa._process_running(123456) is False


def test_safe_pid_invalid_values_return_false():
    assert sa._safe_pid_exists(0) is False
    assert sa._safe_pid_exists(-1) is False
    assert sa._safe_pid_exists("not-a-pid") is False  # type: ignore[arg-type]


def test_safe_pid_uses_psutil_when_available(monkeypatch):
    calls: list[int] = []

    def pid_exists(pid: int) -> bool:
        calls.append(pid)
        return True

    monkeypatch.setitem(sys.modules, "psutil", SimpleNamespace(pid_exists=pid_exists))
    assert sa._safe_pid_exists(42) is True
    assert calls == [42]


def test_windows_fallback_does_not_call_kill(monkeypatch):
    monkeypatch.delitem(sys.modules, "psutil", raising=False)
    real_import = __import__

    class FakeKernel32:
        def OpenProcess(self, access, inherit, pid):
            return 100

        def CloseHandle(self, handle):
            return True

    fake_ctypes = SimpleNamespace(windll=SimpleNamespace(kernel32=FakeKernel32()))

    def fake_import(name, *args, **kwargs):
        if name == "psutil":
            raise ImportError(name)
        if name == "ctypes":
            return fake_ctypes
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    monkeypatch.setattr(sa.os, "name", "nt", raising=False)
    monkeypatch.setattr(sa.os, "kill", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("os.kill must not be called")), raising=False)
    assert sa._safe_pid_exists(123) is True


def test_build_snapshot_pid_detection_failure_is_not_fatal(monkeypatch, tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "workflow_active.pid").write_text("123", encoding="utf-8")
    monkeypatch.setattr(sa, "_safe_pid_exists", lambda pid: (_ for _ in ()).throw(RuntimeError("boom")))
    snapshot = DashboardStatusAggregator(root=tmp_path, include_db=False, include_logs=False).build_snapshot()
    assert snapshot.runtime.current_state in {"IDLE", "UNKNOWN"}
