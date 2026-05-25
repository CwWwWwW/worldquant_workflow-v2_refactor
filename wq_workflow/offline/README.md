# Phase 5A / 5B / 5C Offline Evidence

This package provides the Phase 5A decision snapshot layer, the Phase 5B Offline Replay Engine, and the Phase 5C Conservative Counterfactual Evaluator.

Phase 5A records structured decision snapshots and later observed outcomes. Phase 5B loads those snapshots/outcomes and replays advisory policies (`actual_chosen`, `legacy`, `model_choice`, `experiment_choice`, `budget_choice`) to compare only outcomes that were actually observed.

Phase 5C uses observed Phase 5A outcomes and Phase 5B replay decisions marked `insufficient_counterfactual_evidence` to build conservative nearest-neighbor estimates for actions that were not actually selected. Estimates are written separately as counterfactual requests, evidence, estimates, summaries, and `runtime/status/counterfactual_report.json`.

Boundaries:

- Decision Snapshot records decisions and outcomes.
- Offline Replay only compares historical snapshots with observed outcomes.
- Counterfactual Evaluation only uses observed historical outcomes as neighbor evidence.
- Counterfactual Evaluation marks every estimate as `estimated_not_observed`.
- Evidence shortages return `insufficient_evidence`.
- High SC / low-success estimates are flagged as risk and cannot be treated as automatically better.
- Does not perform off-policy evaluation or doubly robust estimation.
- Does not promote strategies or take over production decisions.
- Does not change alpha generation, rewards, CandidatePool ranking, platform automation, WAIT_RESULT, PARSE_RESULT, or platform SC collection.
- Failures are fail-open/no-op so the legacy official workflow can continue.

Snapshots capture available actions, legacy/model/experiment choices, actual chosen action, governance/budget advisory context, and later true outcomes keyed by `alpha_id`. Governance remains the final safety layer and Experiment Budgeting remains advisory.

Replay output is written separately to `runtime/status/offline_replay_report.json`. Counterfactual output is written separately to `runtime/status/counterfactual_report.json`. Both are evidence for future governance/dashboard use only. `enable_offline_replay`, `offline_replay_auto_run`, `enable_counterfactual_evaluation`, and `counterfactual_auto_run` default to `false`; `offline_replay_mode` and `counterfactual_mode` default to `advisory`.
