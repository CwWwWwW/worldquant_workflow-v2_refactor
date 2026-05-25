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

## Phase 6B: Champion / Challenger Strategy Portfolio

Phase 6B adds an advisory Champion / Challenger Strategy Portfolio layer on top of the Phase 6A Strategy Registry / Scoreboard.

- The default champion is `legacy_baseline`.
- Strategies may be reported as `disabled`, `shadow`, `challenger`, `limited_active`, or `champion`.
- Transitions are recommendations only; every transition has `auto_apply_allowed=false`.
- `limited_active` is still advisory and does not change candidate generation, parent selection, mutation policy, reward, CandidatePool, platform automation, or Governance hard-decision flags.
- Champion replacement is not automatic in this phase; non-baseline strategies can only become future candidates.
- Strategy Budget Allocator remains a future 6C concern and is not called by the 6B service.
- Existing portfolio/champion/budget/promotion/rollback modules are retained for compatibility. Promotion and rollback tools remain manual and are not called by the 6B service.

Primary advisory status output: `runtime/status/strategy_portfolio_report.json`.

Conservative defaults:

- `enable_strategy_champion_challenger=false`
- `strategy_portfolio_auto_refresh=false`
- `strategy_portfolio_mode=advisory`
- `strategy_allow_auto_champion_promotion=false`
- `strategy_transition_auto_apply=false`
- `enable_strategy_budget_allocator=false`
- `strategy_budget_allocator_auto_apply=false`
