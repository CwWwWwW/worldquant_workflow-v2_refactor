# Phase 7A Observability Metrics

This package is the Phase 7A metrics-only observability layer.

It collects read-only runtime metrics from workflow, ML, Governance, Experiment, Offline Replay, Counterfactual, Strategy Portfolio/Budget, and system sources, persists them in SQLite observability tables, and writes `runtime/status/observability_metrics.json`.

7A deliberately does **not** implement drift detection, alerts, health diagnosis, explainability, run reports, automatic remediation, hard takeover, model training, reward changes, CandidatePool changes, Governance hard-flag changes, promotion/rollback, or Strategy budget application.

`observability_auto_collect` defaults to `false`; manual collection is available through `ObservabilityService.collect_metrics()`.
