# Experiment Tracking (Phase 4A)

This package is the Phase 4A Experiment Tracking layer. It records experiment plans, arms, candidate assignments, backtest results, summaries, and a runtime report.

Boundaries:

- Tracking only: no dynamic budget allocation, Bayesian optimization, multi-armed bandits, offline replay, strategy portfolio, or observability dashboard.
- Does not change alpha generation, reward semantics, CandidatePool scoring, WAIT_RESULT, PARSE_RESULT, platform automation, or SC collection.
- Legacy official workflow remains the default production path; refactored pipeline is still not enabled for production by this layer.
- ExperimentService is the only intended workflow-facing entry point. Workflow, alpha, and evaluation code should not write experiment tables directly.

Runtime output:

- SQLite tables: `experiment_plans`, `experiment_assignments`, `experiment_results`, `experiment_summaries`.
- Status report: `runtime/status/experiment_report.json`.

Default configuration:

```json
{
  "enable_experiment_tracking": true,
  "enable_experiment_design": false,
  "enable_experiment_budgeting": false,
  "experiment_assignment_mode": "tracking_only"
}
```

Phase 4B may add planning and budgeting on top of this data. This phase deliberately does not let the experiment layer decide whether a candidate is generated or submitted.
