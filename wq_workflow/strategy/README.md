# Phase 6A Strategy Registry / Scoreboard

This package contains the Phase 6A advisory-only Strategy Registry / Scoreboard layer.

It registers strategy profiles for legacy baseline, random exploration, experiment budgeting, ML parent/mutation policies, replay-supported policies, counterfactual-supported policies, governance-safe policies, and manual/unknown fallbacks.

6A only reads evidence and scores strategies. It does **not**:

- run Champion/Challenger promotion,
- allocate or auto-apply strategy budgets,
- take over alpha generation or candidate selection,
- modify reward semantics or CandidatePool ranking,
- change browser/platform automation,
- change Governance hard-decision flags,
- treat counterfactual estimates as actual outcomes.

Counterfactual evidence is always marked as estimated-not-observed and remains advisory. Replay, counterfactual, experiment, governance, and ML evidence are read fail-open; missing sources produce warnings rather than blocking the legacy workflow.

The advisory report is written to `runtime/status/strategy_scoreboard.json` when `StrategyService.refresh_scoreboard()` is called, or when `strategy_scoreboard_auto_refresh=true` during bootstrap. By default auto refresh is disabled.

Future phases:

- 6B may add Champion/Challenger state management.
- 6C may add a Strategy Budget Allocator.

Both are explicitly disabled by default in 6A.
