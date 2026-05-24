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
