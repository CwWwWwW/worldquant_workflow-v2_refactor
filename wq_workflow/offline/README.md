# Phase 5A Decision Snapshot

This package provides the Phase 5A decision snapshot layer. It records structured, replayable decision snapshots and later observed outcomes for audit and future offline replay work.

Boundaries:

- Records decisions only.
- Does not run an Offline Replay Engine.
- Does not run Counterfactual Evaluation.
- Does not perform off-policy evaluation or doubly robust estimation.
- Does not promote strategies or take over production decisions.
- Does not change alpha generation, rewards, CandidatePool ranking, platform automation, WAIT_RESULT, PARSE_RESULT, or platform SC collection.
- Failures are fail-open/no-op so the legacy official workflow can continue.

Snapshots capture available actions, legacy/model/experiment choices, actual chosen action, governance/budget advisory context, and later true outcomes keyed by `alpha_id`. Governance remains the final safety layer and Experiment Budgeting remains advisory.
