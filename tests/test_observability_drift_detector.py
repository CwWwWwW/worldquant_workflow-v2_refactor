from __future__ import annotations

from wq_workflow.observability.drift_detector import DriftDetector
from wq_workflow.observability.schema import ObservabilityMetric, ObservabilitySourceStatus


def _metric(name, value, i, source="workflow"):
    return ObservabilityMetric(source=source, metric_name=name, value=value, timestamp=f"2026-01-01T00:00:{i:02d}+00:00")


def test_observability_drift_detector_defaults_and_safe_cases():
    detector = DriftDetector()
    assert detector.default_rules()
    original = [_metric("workflow.recent_failure_count", v, i) for i, v in enumerate([1, 1, 1, 10])]
    signals = detector.detect(original, [ObservabilitySourceStatus(source="workflow", available=True, is_stale=True)])
    assert any(s.triggered and s.rule_id == "workflow_recent_failure_spike" for s in signals)
    assert any(s.triggered and "source_stale" in s.reason_codes for s in signals)
    assert original[0].value == 1
    assert detector.detect([_metric("x", "not-number", 1)], [])


def test_observability_drift_detector_success_drop_and_missing_nonfatal():
    detector = DriftDetector()
    metrics = [_metric("workflow.recent_success_count", v, i) for i, v in enumerate([10, 10, 10, 1])]
    signals = detector.detect(metrics, [ObservabilitySourceStatus(source="database", available=False)])
    assert any(s.triggered and s.rule_id == "workflow_success_drop" for s in signals)
    assert any(s.triggered and "source_unavailable" in s.reason_codes for s in signals)
