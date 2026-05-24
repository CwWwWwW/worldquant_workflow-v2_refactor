from wq_workflow.app.self_healing import SelfHealingGuard


def test_safe_call_success_returns_result():
    guard = SelfHealingGuard()
    assert guard.safe_call("ok", lambda: 3) == 3


def test_safe_call_returns_fallback_on_exception():
    guard = SelfHealingGuard()
    assert guard.safe_call("boom", lambda: (_ for _ in ()).throw(RuntimeError("x")), fallback={"ok": False}) == {"ok": False}


def test_safe_call_invokes_on_error():
    guard = SelfHealingGuard()
    called = {}

    def on_error(exc):
        called["error"] = str(exc)

    assert guard.safe_call("boom", lambda: (_ for _ in ()).throw(RuntimeError("x")), fallback=1, on_error=on_error) == 1
    assert called["error"] == "x"


def test_safe_call_does_not_raise_to_main_flow():
    guard = SelfHealingGuard()
    assert guard.safe_call("boom", lambda: (_ for _ in ()).throw(RuntimeError("x"))) is None
