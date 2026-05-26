# Phase 7 Observability

This package contains the Phase 7 observability layer.

## Phase 7A: Observability Metrics

7A collects read-only runtime metrics from workflow, ML, Governance, Experiment, Offline Replay, Counterfactual, Strategy Portfolio/Budget, and system sources. It persists metrics in SQLite observability tables and writes `runtime/status/observability_metrics.json`.

## Phase 7B: Drift / Alert / Health Diagnosis

7B builds on 7A metrics and adds advisory-only drift signals, local alert events, and health diagnosis reports. It can generate:

- `runtime/status/observability_alerts.json`
- `runtime/status/health_diagnosis.json`

7B remains conservative and fail-open. It does not send external notifications, does not perform automatic remediation, does not stop or roll back the workflow, does not change reward semantics or CandidatePool state, does not modify Governance hard-decision flags, does not apply Strategy budget, and does not call promotion or rollback execution.

7C is reserved for Explainability / Run Report / Decision Trace. Phase 7 work continues on `phase7-observability` until all Phase 7 sub-phases are complete; do not merge main before Phase 7 is complete.

`observability_auto_collect`, `observability_diagnostics_auto_run`, external alert emit, and automatic remediation all default to `false`.
