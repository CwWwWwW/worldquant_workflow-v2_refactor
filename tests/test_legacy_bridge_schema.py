from __future__ import annotations

import json
from datetime import UTC, datetime

from wq_workflow.legacy_bridge.schema import LegacyLearningEvidence, RuntimeEvent, RuntimeStateSnapshot
from wq_workflow.legacy_bridge.utils import summarize_payload


def test_runtime_state_snapshot_to_dict_from_dict_missing_fields_json_safe():
    snapshot = RuntimeStateSnapshot(current_state="WAIT_RESULT", current_iteration="3", raw_payload={"x": float("nan")})
    data = snapshot.to_dict()
    encoded = json.dumps(data, allow_nan=False)
    assert "WAIT_RESULT" in encoded
    loaded = RuntimeStateSnapshot.from_dict({"current_state": "PARSE_RESULT"})
    assert loaded.current_state == "PARSE_RESULT"
    assert loaded.ml_summary == {}


def test_runtime_event_truncates_and_redacts_sensitive_payload():
    event = RuntimeEvent(message="x" * 1000, raw_payload={"session_token": "secret", "html": "h" * 5000})
    data = event.to_dict()
    assert len(data["message"]) <= 300
    assert data["raw_payload"]["session_token"] == "[REDACTED]"
    assert "h" * 1000 not in json.dumps(data)


def test_legacy_learning_evidence_roundtrip_flags_and_time_utc():
    evidence = LegacyLearningEvidence(evidence_type="backtest_result", observed=True, estimated=False, advisory=False, reward=0.5)
    data = evidence.to_dict()
    loaded = LegacyLearningEvidence.from_dict(data)
    assert loaded.observed is True and loaded.estimated is False and loaded.reward == 0.5
    assert datetime.fromisoformat(loaded.timestamp).tzinfo is not None
    assert datetime.now(UTC).tzinfo is not None


def test_summarize_payload_redacts_sensitive_keys():
    payload = summarize_payload({"cookie": "abc", "prompt": "p" * 5000}, max_payload_chars=200)
    assert payload["cookie"] == "[REDACTED]"
    assert "p" * 500 not in json.dumps(payload)
