# Legacy Bridge

The legacy bridge is a read-only, fail-open sidecar for the official legacy workflow. It writes small status files under `runtime/status/` so learning, observability, dashboard, and CLI readers can understand the current run without controlling execution.

Outputs:

- `runtime/status/runtime_state.json`: current runtime snapshot.
- `runtime/status/recent_events.jsonl`: short append-only event stream.
- `runtime/status/legacy_learning_evidence.jsonl`: observed legacy evidence for later advisory learning.

The observer does not change reward, CandidatePool behavior, template generation, alpha generation, platform automation, Governance hard flags, Strategy Budget, promotion, or rollback. All hooks are fail-open and redact/truncate sensitive or large payloads.
