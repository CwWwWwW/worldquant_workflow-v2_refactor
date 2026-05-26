# Legacy Bridge

The legacy bridge is a read-only, fail-open sidecar for the official legacy workflow. It writes small status files under `runtime/status/` so learning, observability, dashboard, and CLI readers can understand the current run without controlling execution.

Outputs:

- `runtime/status/runtime_state.json`: current runtime snapshot.
- `runtime/status/recent_events.jsonl`: short append-only event stream.
- `runtime/status/legacy_learning_evidence.jsonl`: observed legacy evidence for later advisory learning.

The observer does not change reward, CandidatePool behavior, template generation, alpha generation, platform automation, Governance hard flags, Strategy Budget, promotion, or rollback. All hooks are fail-open and redact/truncate sensitive or large payloads.

Concurrency note: the bridge JSONL files are designed for exactly one main-process writer per `runtime/status` directory. Appends are one-record `open("a")` / write / flush operations and fail open; optional `fsync` is available for deployments that prefer durability over throughput, but defaults to off. Rotation is only safe under this single-writer contract and rotation failures are ignored so the legacy workflow is not interrupted.

Dashboard, CLI, observability, and advisory learning integrations must treat these JSONL files as read-only sources. If multiple main workflow processes run at the same time, each process must use a different `runtime/status` directory. Do not configure multiple main processes to append to the same bridge JSONL files. Readers skip corrupt or partial lines with a single warning per read instead of blocking the legacy workflow.
