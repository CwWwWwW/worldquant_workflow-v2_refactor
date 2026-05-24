from __future__ import annotations


def test_platform_sc_result_payload_and_metrics():
    from wq_workflow.platform.sc_collector import PlatformSCResult

    result = PlatformSCResult(status="complete", max=0.2, min=-0.3, abs_max=0.3, selector="x")
    assert result.to_payload()["status"] == "complete"
    assert result.to_metrics()["platform_sc_abs_max"] == 0.3


def test_simulate_and_platform_facades_have_expected_functions():
    import wq_workflow.platform_sc as platform_sc
    import wq_workflow.simulate as simulate

    assert callable(platform_sc.collect_platform_sc_safely)
    assert callable(simulate.run_platform_backtest)
    assert callable(simulate.collect_platform_sc_safely)
