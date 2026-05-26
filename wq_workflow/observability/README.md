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


## Phase 7C: Explainability / Run Report / Decision Trace

7C builds on 7A metrics and 7B advisory alerts/diagnosis. It loads read-only evidence from workflow, ML, Governance, Experiment, Decision Snapshot, Offline Replay, Counterfactual, Strategy Scoreboard, Strategy Portfolio, Strategy Budget, and Observability reports, then produces explain-only artifacts:

- `runtime/status/run_explain_report.json`
- `runtime/status/daily_observability_report.json`
- `runtime/status/stage7_summary_report.json`

The 7C layer is for human review. It does not send external notifications, does not perform automatic remediation, does not stop or roll back the workflow, does not change reward semantics or CandidatePool state, does not modify Governance hard-decision flags, does not apply Strategy budget, does not execute promotion or rollback, does not train models, and does not treat counterfactual estimates as actual outcomes.

Defaults are conservative: `enable_run_explainability=false`, `observability_explainability_auto_run=false`, `observability_explainability_mode=explain_only`, and `observability_explanation_auto_action=false`. Phase 7A/7B/7C completion should wait for explicit user instruction before merging to `main`.
### Legacy bridge source

Observability can read `runtime/status/runtime_state.json` and `runtime/status/recent_events.jsonl` as read-only workflow context. These sources report availability, staleness, latest state, iteration, and recent error counts only; they do not trigger collect, diagnose, explain, remediation, promotion, rollback, or legacy workflow actions.
