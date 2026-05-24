# Experiment Tracking, Planning & Budgeting

This package contains the Phase 4 experiment layer.

- Phase 4A records experiment plans, arms, assignments, results and summaries.
- Phase 4B adds advisory planning and budgeting from `experiment_summaries`.
- Budget plans are recommendations only; they do not hard-take over candidate generation, submission, reward, CandidatePool scoring, WAIT_RESULT, PARSE_RESULT, platform automation, or platform SC collection.

Runtime output:

- Phase 4A tables: `experiment_plans`, `experiment_assignments`, `experiment_results`, `experiment_summaries`.
- Phase 4B tables: `experiment_budget_plans`, `experiment_budget_allocations`, `experiment_budget_snapshots`.
- Status report: `runtime/status/experiment_report.json`, including a `budgeting` section.

Budgeting behavior:

- `legacy_baseline` keeps a minimum advisory ratio.
- `random_exploration` keeps a minimum advisory ratio.
- treatment arms are capped so one treatment cannot consume all budget.
- insufficient samples prevent aggressive up-weighting.
- high failure rate and high SC risk are down-weighted.
- positive average reward and high quality pass rate are up-weighted.
- Governance may veto an unsafe arm; the arm is marked `governance_blocked` and receives zero advisory ratio.

Default configuration:

```json
{
  "enable_experiment_tracking": true,
  "enable_experiment_design": true,
  "enable_experiment_budgeting": true,
  "experiment_assignment_mode": "tracking_only",
  "experiment_budget_mode": "advisory"
}
```

Future phases may add Offline Replay, Counterfactual Evaluation, Strategy Portfolio, and Observability/Explainability. They are intentionally not implemented here.
