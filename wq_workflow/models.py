from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


BASE_URL = "https://platform.worldquantbrain.com"
LOGIN_URL = f"{BASE_URL}/login"
SIMULATE_URL = f"{BASE_URL}/simulate"
ALPHAS_URL = f"{BASE_URL}/alphas"


@dataclass
class WorkflowConfig:
    email: str = ""
    password: str = ""
    login_url: str = LOGIN_URL
    headless: bool = False
    slow_mo: int = 0
    browser_executable_path: str = ""
    max_templates: int = 0
    max_iterations_per_template: int = 12
    simulation_wait_seconds: int = 900
    wait_result_max_seconds: int = 300
    wait_result_start_timeout_seconds: int = 90
    result_stable_reads: int = 3
    result_poll_interval_seconds: float = 2.0
    result_dom_stable_window_seconds: float = 4.0
    freshness_accept_score: int = 70
    enable_result_consistency_validation: bool = True
    enable_platform_sc_check: bool = True
    platform_sc_timeout_seconds: int = 90
    enable_refactored_pipeline: bool = False
    enable_refactored_pipeline_shadow: bool = True
    allow_observe_only_pipeline: bool = False
    enable_app_context: bool = True
    enable_platform_services: bool = True
    enable_data_services: bool = True
    enable_startup_healthcheck: bool = True
    healthcheck_auto_repair: bool = True
    healthcheck_force_legacy_on_critical_warning: bool = True
    healthcheck_disable_broken_models: bool = True
    healthcheck_audit_path: str = "runtime/audit/healthcheck.jsonl"
    enable_learning_governance: bool = True
    enable_long_term_learning_guard: bool = True
    enable_auto_model_disable: bool = True
    enable_auto_model_rollback: bool = True
    enable_auto_retrain: bool = True
    enable_model_lifecycle: bool = True
    enable_online_model_evaluation: bool = True
    enable_sample_quality_check: bool = True
    force_enable_unsafe_ml_decisions: bool = False
    enable_ml_system: bool = True
    enable_ml_dependencies_required: bool = False
    enable_sc_learning: bool = True
    enable_sc_model_training: bool = True
    enable_sc_model_prediction: bool = True
    enable_sc_model_fallback: bool = False
    enable_parent_learning: bool = True
    enable_parent_model_training: bool = True
    enable_parent_model_prediction: bool = True
    enable_parent_model_decision: bool = False
    enable_policy_learning: bool = True
    enable_policy_model_training: bool = True
    enable_policy_model_prediction: bool = True
    enable_policy_model_decision: bool = False
    enable_simulator_learning: bool = True
    enable_simulator_model_training: bool = True
    enable_simulator_model_prediction: bool = True
    enable_simulator_model_skip: bool = False
    enable_experiment_tracking: bool = True
    enable_experiment_design: bool = False
    enable_experiment_budgeting: bool = False
    experiment_status_path: str = "runtime/status/experiment_report.json"
    default_experiment_id: str = "default_experiment_v1"
    experiment_assignment_mode: str = "tracking_only"
    enable_offline_replay: bool = True
    enable_counterfactual_evaluation: bool = True
    enable_support_checker: bool = True
    enable_strategy_portfolio: bool = True
    enable_champion_challenger: bool = True
    enable_challenger_live_budget: bool = False
    strategy_default_champion: str = "legacy_champion"
    strategy_challenger_live_budget: float = 0.0
    strategy_random_baseline_budget: float = 0.0
    promotion_min_samples: int = 200
    promotion_min_support_coverage: float = 0.65
    promotion_min_reward_improvement: float = 0.05
    promotion_max_sc_risk_delta: float = 0.03
    promotion_max_failure_rate_delta: float = 0.03
    promotion_require_model_validation_pass: bool = True
    promotion_require_offline_replay_pass: bool = True
    rollback_reward_drop_threshold: float = 0.10
    rollback_sc_risk_increase_threshold: float = 0.05
    rollback_failure_rate_increase_threshold: float = 0.05
    rollback_window_size: int = 100
    offline_replay_min_decisions: int = 100
    offline_replay_max_decisions: int = 5000
    support_min_action_count: int = 10
    support_min_context_count: int = 20
    enable_auto_promotion: bool = False
    enable_auto_rollback: bool = False
    enable_drift_monitor: bool = False
    enable_insight_feedback_learning: bool = True
    ml_min_samples: int = 200
    ml_retrain_every_samples: int = 50
    ml_validation_ratio: float = 0.2
    ml_model_min_confidence: float = 0.65
    ml_model_max_age_days: int = 14
    sc_model_max_age_days: int = 7
    parent_model_max_age_days: int = 14
    policy_model_max_age_days: int = 14
    simulator_model_max_age_days: int = 7
    sc_online_eval_min_samples: int = 30
    parent_online_eval_min_samples: int = 30
    policy_online_eval_min_samples: int = 30
    simulator_online_eval_min_samples: int = 50
    simulator_max_false_skip_rate: float = 0.02
    ml_min_retrain_interval_minutes: int = 30
    ml_auto_retrain_on_drift: bool = True
    ml_auto_disable_on_retrain_failure: bool = True
    ml_max_invalid_sample_ratio: float = 0.2
    sc_max_invalid_sample_ratio: float = 0.05
    min_legacy_baseline_budget: float = 0.10
    min_random_exploration_budget: float = 0.03
    simulator_validation_backtest_budget: float = 0.10
    governance_status_path: str = "runtime/status/governance_status.json"
    ml_status_path: str = "runtime/status/ml_status.json"
    ml_require_validation_pass: bool = True
    ml_allow_sklearn: bool = True
    ml_allow_no_sklearn_fallback: bool = True
    ml_model_root: str = "runtime/models"
    sc_learning_min_samples: int = 200
    sc_model_min_confidence: float = 0.65
    sc_model_max_mae: float = 0.15
    parent_learning_min_samples: int = 200
    parent_model_max_mae: float = 0.20
    parent_model_min_success_recall: float = 0.60
    policy_learning_min_samples: int = 200
    policy_model_max_mae: float = 0.25
    policy_min_action_coverage: float = 0.30
    simulator_learning_min_samples: int = 200
    simulator_model_min_success_recall: float = 0.70
    simulator_model_max_mae: float = 0.25
    ml_random_seed: int = 42
    simulator_protected_parent_reward: float = 0.5
    enable_alpha_representation: bool = True
    enable_alpha_ast_parser: bool = True
    enable_alpha_distance_features: bool = True
    alpha_parser_fail_soft: bool = True
    alpha_representation_cache_size: int = 10000
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-pro"
    deepseek_temperature: float = 0.15
    deepseek_max_tokens: int = 3000
    enable_v2_engine: bool = True
    enable_behavior_sc_pipeline: bool = True
    v2_rollout_phase: int = 6
    enable_survival_memory: bool = True
    enable_pending_reward: bool = True
    enable_template_governance: bool = True
    enable_exploration_pressure: bool = True
    enable_adaptive_legacy: bool = True
    enable_research_insights: bool = True
    enable_sidecar_evolution: bool = True
    enable_population_engine: bool = True
    enable_evolution_policy: bool = True
    enable_alpha_simulator: bool = True
    enable_lineage_value: bool = True
    enable_alpha_graph: bool = True
    enable_ast_evolution: bool = True
    enable_crossover: bool = True
    enable_experimental_evolution_decisions: bool = False
    simulator_low_confidence_threshold: float = 0.2
    population_size: int = 80
    population_elite_size: int = 12
    population_max_same_family_ratio: float = 0.35
    population_tournament_k: int = 5
    crossover_rate: float = 0.25
    max_crossover_attempts: int = 5
    crossover_random_subtree_selection: bool = True
    crossover_use_graph_bias: bool = False
    crossover_random_seed: int | None = None
    mutation_rate: float = 0.70
    random_seed_rate: float = 0.05
    policy_learning_rate: float = 0.08
    policy_min_weight: float = 0.15
    policy_max_weight: float = 5.0
    policy_epsilon_explore: float = 0.12
    policy_decay_rate: float = 0.995
    policy_recent_window: int = 300
    simulator_skip_enabled: bool = True
    simulator_skip_threshold: float = 0.18
    simulator_never_skip_if_parent_reward_above: float = 1.0
    simulator_skip_only_pending_candidates: bool = True
    simulator_max_consecutive_skips_per_template: int = 3
    legacy_full_import_enabled: bool = True
    legacy_full_import_once: bool = True
    legacy_full_import_force: bool = False
    legacy_full_import_batch_size: int = 1000
    legacy_full_import_max_records: int = 0
    lineage_value_lookahead: int = 3
    lineage_value_decay: float = 0.75
    max_ast_depth: int = 12
    max_operator_count: int = 40
    max_expr_length: int = 512
    max_nested_ts: int = 5
    insight_top_k: int = 5
    insight_distill_interval: int = 50
    insight_min_samples: int = 20
    insight_max_prompt_clusters: int = 16
    storage_mode: str = "hybrid"
    storage_db_path: str = "runtime/db/workflow.db"
    storage_legacy_export: bool = True
    storage_queue_batch_size: int = 100
    storage_queue_flush_interval_seconds: float = 0.25
    storage_health_check_interval_seconds: float = 60.0
    storage_retention_days: int = 14
    thresholds: dict[str, float] = field(
        default_factory=lambda: {
            "sharpe_min": 1.25,
            "fitness_min": 1.0,
            "sub_universe_sharpe_min": -0.49,
            "turnover_min": 1.0,
            "turnover_max": 70.0,
        }
    )
    selectors: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class TemplateItem:
    index: int
    name: str
    code: str
    source: str
    path: str = ""


@dataclass
class PlatformError:
    text: str
    page_text: str = ""


@dataclass
class QualityReport:
    passed: bool
    status: str
    pass_count: int = 0
    fail_count: int = 0
    pending_count: int = 0
    metrics: dict[str, float] = field(default_factory=dict)
    pass_messages: list[str] = field(default_factory=list)
    fail_messages: list[str] = field(default_factory=list)
    pending_messages: list[str] = field(default_factory=list)
    summary_text: str = ""
    testing_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "status": self.status,
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "pending_count": self.pending_count,
            "metrics": self.metrics,
            "pass_messages": self.pass_messages,
            "fail_messages": self.fail_messages,
            "pending_messages": self.pending_messages,
            "summary_text": self.summary_text,
            "testing_text": self.testing_text,
        }


@dataclass
class SimulationResult:
    ok: bool
    code: str
    alpha_name: str
    metrics: dict[str, float] = field(default_factory=dict)
    quality: QualityReport | None = None
    error: PlatformError | None = None
    page_text: str = ""
    screenshot: str = ""
    simulation_id: str = ""
    result_timestamp: float | None = None
    simulation_session_id: str = ""
    result_fingerprint: str = ""
    freshness_score: int | None = None
    result_stable_count: int = 0
    state_trace: list[dict[str, Any]] = field(default_factory=list)
    recovery_level: str = ""
    template_success: bool = False
    template_success_reason: str = ""
    success_candidate: bool = False
    result_uncertain: bool = False
    platform_sc: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunValidation:
    ok: bool
    old_simulation_id: str = ""
    new_simulation_id: str = ""
    click_timestamp: float = 0.0
    result_timestamp: float | None = None
    simulation_session_id: str = ""
    result_fingerprint: str = ""
    freshness_score: int | None = None
    result_stable_count: int = 0
    progress_complete: bool | None = None
    metrics_detected: bool | None = None
    fingerprint_stable: bool | None = None
    timestamp_fresh: bool | None = None
    freshness_accept_score: int = 70
    consistency_signals_present: bool = False
    reason: str = ""


@dataclass
class AlphaExecutionContext:
    alpha_id: str
    code: str
    alpha_name: str
    template_file: str = ""
    attempt: int = 1
    simulation_id: str = ""
    click_timestamp: float = 0.0
    result_timestamp: float | None = None
    simulation_session_id: str = ""
    result_fingerprint: str = ""
    freshness_score: int | None = None
    result_stable_count: int = 0
    state_trace: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RecoveryDecision:
    level: str
    reason: str = ""
    state: str = ""
    retry: int = 0
    fatal: bool = False


@dataclass
class CorrelationResult:
    passed: bool
    reason: str
    details: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TemplateSuccess:
    template_file: str
    alpha_name: str
    code: str
    metrics: dict[str, float]
    quality: QualityReport
    screenshot: str
    template_success: bool = False
    template_success_reason: str = ""


@dataclass
class TemplateFailure:
    template_file: str
    alpha_name: str
    code: str
    reason: str
    screenshot: str = ""
