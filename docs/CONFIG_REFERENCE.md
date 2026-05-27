# Configuration Reference

`config.example.json` is the public configuration template. Copy it to `config.json` for local use.

`config.json` is private local configuration and must remain excluded from git. Do not commit credentials, tokens, cookies, browser storage, private datasets, runtime databases, private Alpha results, or platform-owned data.

The current template contains 289 top-level keys. This reference groups the real public template keys by category without inventing additional fields.

## Account, platform, and browser

- `email`
- `password`
- `login_url`
- `headless`
- `slow_mo`
- `browser_executable_path`
- `platform_sc`

## Workflow timing and result validation

- `max_templates`
- `max_iterations_per_template`
- `simulation_wait_seconds`
- `wait_result_max_seconds`
- `wait_result_start_timeout_seconds`
- `result_stable_reads`
- `result_poll_interval_seconds`
- `result_dom_stable_window_seconds`
- `freshness_accept_score`

## Refactored pipeline and services

- `refactored_pipeline_note`
- `enable_refactored_pipeline`
- `enable_app_context`
- `enable_platform_services`
- `enable_data_services`
- `enable_refactored_pipeline_shadow`

## Learning, ML, governance, and samples

- `enable_learning_governance`
- `enable_long_term_learning_guard`
- `enable_auto_model_disable`
- `enable_auto_model_rollback`
- `enable_auto_retrain`
- `enable_model_lifecycle`
- `enable_online_model_evaluation`
- `enable_sample_quality_check`
- `force_enable_unsafe_ml_decisions`
- `enable_ml_system`
- `enable_ml_dependencies_required`
- `enable_sc_learning`
- `enable_sc_model_training`
- `enable_sc_model_prediction`
- `enable_sc_model_fallback`
- `enable_parent_learning`
- `enable_parent_model_training`
- `enable_parent_model_prediction`
- `enable_parent_model_decision`
- `enable_policy_learning`
- `enable_policy_model_training`
- `enable_policy_model_prediction`
- `enable_policy_model_decision`
- `enable_simulator_learning`
- `enable_simulator_model_training`
- `enable_simulator_model_prediction`
- `enable_simulator_model_skip`
- `enable_auto_promotion`
- `enable_auto_rollback`

## Experiment tracking and budgeting

- `enable_experiment_tracking`
- `enable_experiment_design`
- `enable_experiment_budgeting`
- `experiment_status_path`
- `experiment_assignment_mode`
- `experiment_budget_mode`
- `experiment_budget_total_hint`
- `experiment_budget_refresh_interval_iterations`
- `experiment_budget_refresh_interval_hours`
- `experiment_budget_legacy_min_ratio`
- `experiment_budget_random_min_ratio`
- `experiment_budget_treatment_max_ratio`
- `experiment_budget_min_samples_for_adjustment`
- `experiment_budget_high_failure_rate_threshold`
- `experiment_budget_high_sc_abs_max_threshold`
- `experiment_budget_high_quality_pass_threshold`
- `experiment_budget_allow_governance_veto`
- `experiment_budget_fail_open_tracking_only`

## Offline replay and counterfactual evaluation

- `enable_offline_replay`
- `offline_replay_status_path`
- `offline_replay_mode`
- `offline_replay_auto_run`
- `offline_replay_default_limit`
- `offline_replay_min_observable_samples`
- `offline_replay_baseline_policy`
- `offline_replay_include_policies`
- `offline_replay_fail_open`
- `enable_counterfactual_evaluation`
- `counterfactual_status_path`
- `counterfactual_mode`
- `counterfactual_auto_run`
- `counterfactual_default_limit`
- `counterfactual_min_evidence`
- `counterfactual_min_effective_evidence`
- `counterfactual_similarity_threshold`
- `counterfactual_high_sc_abs_max_threshold`
- `counterfactual_low_success_rate_threshold`
- `counterfactual_medium_confidence_evidence`
- `counterfactual_high_confidence_evidence`
- `counterfactual_fail_open`
- `offline_replay_min_decisions`
- `offline_replay_max_decisions`

## Strategy registry, portfolio, and budget

- `enable_strategy_registry`
- `strategy_scoreboard_status_path`
- `strategy_registry_mode`
- `strategy_scoreboard_auto_refresh`
- `strategy_scoreboard_default_limit`
- `strategy_score_min_samples`
- `strategy_score_medium_samples`
- `strategy_score_high_samples`
- `strategy_high_sc_abs_max_threshold`
- `strategy_fail_open`
- `enable_strategy_champion_challenger`
- `enable_strategy_budget_allocator`
- `strategy_budget_status_path`
- `strategy_budget_mode`
- `strategy_budget_auto_refresh`
- `strategy_budget_total_hint`
- `strategy_budget_fail_open`
- `strategy_budget_legacy_min_ratio`
- `strategy_budget_exploration_min_ratio`
- `strategy_budget_shadow_max_ratio`
- `strategy_budget_challenger_max_ratio`
- `strategy_budget_limited_active_max_ratio`
- `strategy_budget_high_risk_max_ratio`
- `strategy_budget_high_sc_max_ratio`
- `strategy_budget_insufficient_evidence_max_ratio`
- `strategy_budget_non_champion_max_ratio`
- `strategy_budget_normalization_tolerance`
- `strategy_budget_auto_apply`
- `strategy_budget_allocator_auto_apply`
- `enable_strategy_portfolio`
- ...and 14 more keys in this category.

## Observability, alerts, diagnosis, and reports

- `enable_observability_metrics`
- `observability_metrics_status_path`
- `observability_mode`
- `observability_auto_collect`
- `observability_fail_open`
- `observability_status_max_age_seconds`
- `observability_recent_window`
- `observability_metrics_default_limit`
- `observability_collect_workflow`
- `observability_collect_ml`
- `observability_collect_governance`
- `observability_collect_experiment`
- `observability_collect_offline`
- `observability_collect_strategy`
- `observability_collect_system`
- `enable_observability_alerts`
- `enable_observability_drift_detection`
- `enable_observability_diagnosis`
- `observability_alerts_status_path`
- `observability_diagnosis_status_path`
- `observability_alert_mode`
- `observability_alert_auto_emit`
- `observability_diagnostics_auto_run`
- `observability_auto_remediation`
- `observability_drift_window_size`
- `observability_drift_baseline_window_size`
- `observability_failure_spike_threshold`
- `observability_success_drop_threshold`
- `observability_sc_risk_threshold`
- `observability_warning_count_threshold`
- ...and 13 more keys in this category.

## Storage, runtime, and compatibility

- `legacy_runtime_state_path`
- `legacy_recent_events_path`
- `legacy_learning_evidence_path`
- `legacy_observer_fail_open`
- `legacy_observer_max_event_payload_chars`
- `legacy_observer_max_message_chars`
- `legacy_recent_events_max_bytes`
- `legacy_learning_evidence_max_bytes`
- `legacy_observer_write_runtime_state`
- `legacy_observer_write_recent_events`
- `legacy_observer_write_learning_evidence`
- `legacy_observer_include_alpha_expression`
- `legacy_observer_include_template_body`
- `legacy_observer_include_traceback`

## Other Public Template Keys

- `enable_result_consistency_validation`
- `default_experiment_id`
- `run_explain_report_status_path`
- `daily_observability_report_status_path`
- `stage7_summary_report_status_path`
- `enable_legacy_iteration_observer`
- `enable_champion_challenger`
- `enable_drift_monitor`
- `enable_insight_feedback_learning`
- `ml_min_samples`
- `ml_retrain_every_samples`
- `ml_validation_ratio`
- `ml_model_min_confidence`
- `ml_model_max_age_days`
- `sc_model_max_age_days`
- `parent_model_max_age_days`
- `policy_model_max_age_days`
- `simulator_model_max_age_days`
- `sc_online_eval_min_samples`
- `parent_online_eval_min_samples`
- `policy_online_eval_min_samples`
- `simulator_online_eval_min_samples`
- `simulator_max_false_skip_rate`
- `ml_min_retrain_interval_minutes`
- `ml_auto_retrain_on_drift`
- `ml_auto_disable_on_retrain_failure`
- `ml_max_invalid_sample_ratio`
- `sc_max_invalid_sample_ratio`
- `min_legacy_baseline_budget`
- `min_random_exploration_budget`
- `simulator_validation_backtest_budget`
- `governance_status_path`
- `ml_status_path`
- `ml_require_validation_pass`
- `ml_allow_sklearn`
- `ml_allow_no_sklearn_fallback`
- `ml_model_root`
- `sc_learning_min_samples`
- `sc_model_min_confidence`
- `sc_model_max_mae`
- ...and 55 more keys.

## Operational Notes

- Keep production defaults conservative.
- The legacy official workflow remains the production default path.
- Refactored pipeline, learning, replay, counterfactual, strategy, and observability components should remain shadow/advisory/read-only unless explicitly enabled and validated.
- Runtime paths such as `runtime/status` or `runtime/db` are local state and should not be committed.
