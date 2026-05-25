# WorldQuant DeepSeek 自动迭代工作流

本项目使用 Python + Playwright + BeautifulSoup4 + DeepSeek API。

合规边界：脚本只做已授权的研究辅助，不执行任何 Submit/提交 操作。只有平台质量要求通过且本地自相关红线通过后，才会 Add to Favorites。

## 运行

```powershell
pip install -r requirements.txt
playwright install chromium
python .\worldquant_auto_workflow.py
```

默认进入中文 CLI 菜单。菜单可完成：

- 启动工作流
- 分割模板
- 配置 WorldQuant 账号、密码、DeepSeek API Key
- 查看状态与日志

命令行方式仍可用：

```powershell
python .\worldquant_auto_workflow.py split --template-file .\input_templates\test.txt --max-templates 2
python .\worldquant_auto_workflow.py run --use-split --max-templates 2
python .\worldquant_auto_workflow.py status
```

## 当前流程

1. 读取 `input_templates/`、`--template-file` 或 `--template-text` 中的用户模板混合文本。
2. DeepSeek 筛选所有可用模板，逐个分割，保存到 `templates/ds_template_*.py`，并写入 `templates/last_split_manifest.json`。
3. 按顺序取出模板，由 DeepSeek 先整理成可用 Alpha。
4. 登录 WorldQuant，进入 Simulate，填入因子并运行真实回测。
5. 等待平台回测完成，读取平台错误或 IS Summary / IS Testing Status；不主动退出 Tutorial mode，而是聚焦真实结果元素读取。
6. 若平台返回错误，将错误和当前因子交回 DeepSeek 修复后继续回测。
7. 若回测成功但质量未达标，将 IS Summary / IS Testing Status 交回 DeepSeek 继续迭代。
8. 平台质量通过且本地自相关红线通过后，加入 Favorites，并立即在 CLI 打印 `SUCCESS_RESULT ...`。
9. 当前模板成功后才进入下一个模板。

## 模块拆分

- `wq_workflow/config.py`：配置与选择器
- `wq_workflow/templates.py`：用户文本读取、DeepSeek 模板筛选和文件保存
- `wq_workflow/deepseek_client.py`：DeepSeek 调用、模板整理、错误修复、质量迭代
- `wq_workflow/browser_ops.py`：登录、通用网页操作、禁止 Submit 点击
- `wq_workflow/simulate.py`：Simulate 回测、进度等待、平台错误采集
- `wq_workflow/quality.py`：IS Summary / IS Testing Status 解析
- `wq_workflow/correlation.py`：强制本地自相关检查和持久化因子库
- `wq_workflow/favorites.py`：Add to Favorites 和收藏日志
- `wq_workflow/orchestrator.py`：主流程编排

## 运行产物

- `templates/`：DeepSeek 分割后的模板
- `templates/last_split_manifest.json`：上次分割模板清单，`--use-split` 优先读取它
- `iterations/`：每轮回测截图
- `favorites/`：收藏成功截图
- `iteration_log.csv`：每轮代码、平台错误、质量解析、DeepSeek 返回
- `favorite_alphas.csv`：成功收藏记录
- `local_alpha_library.csv`：本地持久化因子库
- `correlation_check.log`：自相关红线日志
- `workflow.log`：CLI 同步主日志

## Refactored Pipeline Status

The refactored pipeline is currently a structural/shadow pipeline. It is not the production official default execution path.

Production execution still defaults to the legacy official workflow path. Recommended production settings:

```json
{
  "enable_refactored_pipeline": false,
  "enable_refactored_pipeline_shadow": true,
  "allow_observe_only_pipeline": false
}
```

Do not enable `enable_refactored_pipeline=true` for production unless all critical steps are no longer observe-only and the full regression suite passes.

The Config Safety Gate / pipeline safety checks will force fallback to the legacy official workflow if critical observe-only steps are detected and `allow_observe_only_pipeline=false`.

## Phase 4A Experiment Tracking

Phase 4A adds experiment tracking only. Each alpha candidate can be tagged with an `experiment_id` / `arm_id`, and completed backtest metrics can be written to experiment result tables and summarized in `runtime/status/experiment_report.json`.

This phase does **not** change alpha generation, reward semantics, CandidatePool scoring, WAIT_RESULT / PARSE_RESULT, platform automation, SC collection, or the legacy official workflow default path. Dynamic budgeting, Bayesian optimization, multi-armed bandits, offline replay, strategy portfolio changes, and dashboards are intentionally deferred to later phases.

## Phase 4 Experiment Layer

Phase 4A adds experiment tracking tables and reports. Phase 4B adds advisory experiment planning and budgeting on top of those summaries. Budget plans protect `legacy_baseline` and `random_exploration`, cap treatment arms, down-weight high-failure/high-SC-risk arms, and up-weight positive-reward/high-quality arms. The budget layer writes SQLite snapshots and the `budgeting` section of `runtime/status/experiment_report.json`.

This layer remains advisory: it does not hard-take over alpha generation, reward semantics, CandidatePool scoring, platform automation, WAIT_RESULT/PARSE_RESULT, SC collection, or the production legacy workflow. Offline Replay, Counterfactual Evaluation, Strategy Portfolio, Observability dashboard, Bayesian optimization, and complex multi-armed bandits are future phases, not Phase 4B.


## Phase 5A Decision Snapshot

Phase 5A adds a standardized Decision Snapshot layer under `wq_workflow/offline/`. It records structured snapshots for candidate acceptance, experiment arm selection, budget plan selection, and compatible legacy/shadow decision hooks, then writes true outcomes back by `alpha_id` after results are available.

The status report is written to `runtime/status/decision_snapshot_status.json`. Recording is fail-open and does not change alpha generation, reward semantics, CandidatePool ranking, Governance veto behavior, Experiment Budget advisory behavior, platform automation, WAIT_RESULT/PARSE_RESULT, SC collection, or the production legacy workflow default path.

This phase does **not** implement Replay Engine, Counterfactual Evaluation, off-policy evaluation, strategy promotion, or hard takeover. Those remain future phases.

## Phase 5B Offline Replay Engine

Phase 5B adds an advisory Offline Replay Engine on top of Phase 5A decision snapshots and outcomes. It loads `decision_snapshots` / `decision_outcomes`, replays `actual_chosen`, `legacy`, `model_choice`, `experiment_choice`, and `budget_choice`, and writes replay runs, policy decisions, metrics, baseline comparisons, and `runtime/status/offline_replay_report.json`.

Replay only uses observed outcomes. If a replay policy selects an action different from the historical chosen action, the engine does not copy the historical outcome onto that unexecuted action; it marks the decision with `insufficient_counterfactual_evidence`. Counterfactual evaluation, off-policy estimation, doubly robust estimation, strategy promotion, and hard takeover remain out of scope for Phase 5B.

Defaults remain conservative: `enable_offline_replay=false`, `offline_replay_auto_run=false`, `offline_replay_mode=advisory`, and `enable_counterfactual_evaluation=false`. Replay failures are fail-open and do not change alpha generation, reward semantics, platform automation, CandidatePool behavior, WAIT_RESULT/PARSE_RESULT, SC collection, Governance hard-decision flags, or the production legacy workflow default path.

## Phase 5C Conservative Counterfactual Evaluator

Phase 5C adds an advisory Counterfactual Evaluator under `wq_workflow/offline/`. It consumes Phase 5A decision snapshots/outcomes and Phase 5B replay policy decisions marked `insufficient_counterfactual_evidence`, then uses lightweight nearest-neighbor matching against observed historical outcomes to produce separate counterfactual requests, evidence, estimates, summaries, and `runtime/status/counterfactual_report.json`.

All counterfactual estimates are marked `estimated_not_observed`. Evidence must come from records with real observed outcomes; insufficient support returns `insufficient_evidence`, and high-risk estimates are flagged rather than promoted. Defaults remain conservative: `enable_counterfactual_evaluation=false`, `counterfactual_auto_run=false`, and `counterfactual_mode=advisory`.

This phase does **not** treat estimates as actual outcomes, overwrite `decision_outcomes`, overwrite replay observed outcomes, change reward semantics, change CandidatePool ranking, modify Governance hard-decision flags, promote strategies, perform hard takeover, run doubly robust/off-policy evaluation, train models, alter alpha generation, or change platform automation / WAIT_RESULT / PARSE_RESULT / SC collection.

## Phase 6A Strategy Registry / Scoreboard

Phase 6A adds an advisory-only Strategy Registry / Scoreboard layer under `wq_workflow/strategy/`. It registers legacy, random exploration, experiment budget, ML parent/mutation, replay-supported, counterfactual-supported, governance-safe, and manual/unknown strategy profiles, then reads Experiment / Replay / Counterfactual / Governance / ML evidence to produce conservative strategy scores and `runtime/status/strategy_scoreboard.json`.

Recommendations are advisory only. This phase does **not** implement Champion/Challenger, Strategy Budget Allocator, hard takeover, strategy promotion, model training, automatic budget apply, reward changes, CandidatePool changes, platform automation changes, or Governance hard-decision flag changes. Counterfactual evidence remains estimated-not-observed and is never treated as an actual outcome.

### Phase 6B: Champion / Challenger Strategy Portfolio

Phase 6B introduces an advisory-only Strategy Portfolio layer. It reads Phase 6A strategy scores plus risk evidence and writes `runtime/status/strategy_portfolio_report.json` with conservative `disabled` / `shadow` / `challenger` / `limited_active` / `champion` state recommendations.

The default champion is `legacy_baseline`. This phase does not perform strategy budget allocation, automatic budget apply, hard takeover, true champion replacement, promotion execution, rollback execution, model training, reward changes, CandidatePool changes, platform automation changes, or Governance hard-flag changes. Legacy portfolio/champion/budget modules remain available but isolated.

## Phase 6C Strategy Budget Allocator

Phase 6C adds an advisory-only Strategy Budget Allocator under `wq_workflow/strategy/`. It reads Phase 6B portfolio states and emits conservative budget recommendations to `runtime/status/strategy_budget_report.json`.

The allocator is report-only: every allocation has `auto_apply_allowed=false`; `strategy_budget_auto_apply=false` and `strategy_budget_allocator_auto_apply=false` by default. It does not change real backtest submission logic, alpha generation, parent selection, mutation policy, reward semantics, CandidatePool ranking, platform automation, WAIT_RESULT/PARSE_RESULT, SC collection, or Governance hard-decision flags.

Default policy keeps `legacy_baseline` at a minimum floor of `0.40` and `random_exploration` at a minimum floor of `0.05`. Disabled, governance-blocked, and blocked-risk strategies are reported with zero advisory budget. Shadow, challenger, and limited-active states receive observe/test/scale-limited caps; high-risk, high-SC-risk, and insufficient-evidence strategies are capped conservatively. Ratios are normalized for dashboard/Governance visibility only and are never applied to the workflow scheduler.

Legacy `portfolio`, `champion_challenger`, `budget_allocator`, `promotion`, and `rollback` modules remain import-compatible and isolated. Promotion/rollback tools remain manual and are not called by Phase 6C. The refactored pipeline remains non-production-official by default until a later explicit phase.

## Phase 7A Observability Metrics

Phase 7A adds a metrics-only observability layer in `wq_workflow/observability/`. It reads workflow, ML, Governance, Experiment, Offline Replay, Counterfactual, Strategy/Portfolio/Budget, and System status from existing JSON files and SQLite summaries, persists read-only observations into observability tables, and writes `runtime/status/observability_metrics.json`.

7A does not perform Drift Detection, Alerts, Health Diagnosis, Explainability, Run Reports, automatic remediation, hard takeover, model training, reward changes, CandidatePool changes, Governance hard-flag changes, promotion/rollback, or Strategy budget application. `observability_auto_collect` defaults to `false`; alert, drift, diagnosis, explainability, and remediation flags default to `false`. The refactored pipeline remains non-production by default. Phase 7B is reserved for Drift / Alert / Health Diagnosis, and Phase 7C is reserved for Explainability / Run Report / Decision Trace. Phase 7 work continues on `phase7-observability` until all Phase 7 sub-phases are complete.
