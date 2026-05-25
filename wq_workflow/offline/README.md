# Phase 5A / 5B Offline Evidence

This package provides the Phase 5A decision snapshot layer and the Phase 5B Offline Replay Engine.

Phase 5A records structured decision snapshots and later observed outcomes. Phase 5B loads those snapshots/outcomes and replays advisory policies (`actual_chosen`, `legacy`, `model_choice`, `experiment_choice`, `budget_choice`) to compare only outcomes that were actually observed.

Boundaries:

- Decision Snapshot records decisions and outcomes.
- Offline Replay only compares historical snapshots with observed outcomes.
- Does not run Counterfactual Evaluation.
- Does not estimate the result of an action that was not actually selected.
- Unobserved policy actions are marked `insufficient_counterfactual_evidence`.
- Does not perform off-policy evaluation or doubly robust estimation.
- Does not promote strategies or take over production decisions.
- Does not change alpha generation, rewards, CandidatePool ranking, platform automation, WAIT_RESULT, PARSE_RESULT, or platform SC collection.
- Failures are fail-open/no-op so the legacy official workflow can continue.

Snapshots capture available actions, legacy/model/experiment choices, actual chosen action, governance/budget advisory context, and later true outcomes keyed by `alpha_id`. Governance remains the final safety layer and Experiment Budgeting remains advisory.

Replay output is written separately to `runtime/status/offline_replay_report.json`. It is evidence for future governance/dashboard use only. `enable_offline_replay` and `offline_replay_auto_run` default to `false`; `enable_counterfactual_evaluation` remains `false`. Phase 5C is reserved for any future counterfactual evaluator.
