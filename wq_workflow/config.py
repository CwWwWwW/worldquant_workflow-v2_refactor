from __future__ import annotations

import json
import os
from typing import Any

from .models import LOGIN_URL, WorkflowConfig
from .paths import CONFIG_FILE


ENABLE_V2_ENGINE = True
ENABLE_BEHAVIOR_SC_PIPELINE = True
V2_ROLLOUT_PHASE = 6
ENABLE_SURVIVAL_MEMORY = True
ENABLE_PENDING_REWARD = True
ENABLE_TEMPLATE_GOVERNANCE = True
ENABLE_EXPLORATION_PRESSURE = True
ENABLE_ADAPTIVE_LEGACY = True
ENABLE_RESEARCH_INSIGHTS = True
ENABLE_SIDECAR_EVOLUTION = True
ENABLE_POPULATION_ENGINE = True
ENABLE_EVOLUTION_POLICY = True
ENABLE_ALPHA_SIMULATOR = True
ENABLE_LINEAGE_VALUE = True
ENABLE_ALPHA_GRAPH = True
ENABLE_AST_EVOLUTION = True
ENABLE_CROSSOVER = True
ENABLE_EXPERIMENTAL_EVOLUTION_DECISIONS = False
SIMULATOR_LOW_CONFIDENCE_THRESHOLD = 0.2
POPULATION_SIZE = 80
POPULATION_ELITE_SIZE = 12
POPULATION_MAX_SAME_FAMILY_RATIO = 0.35
POPULATION_TOURNAMENT_K = 5
CROSSOVER_RATE = 0.25
MAX_CROSSOVER_ATTEMPTS = 5
CROSSOVER_RANDOM_SUBTREE_SELECTION = True
CROSSOVER_USE_GRAPH_BIAS = False
CROSSOVER_RANDOM_SEED = None
MUTATION_RATE = 0.70
RANDOM_SEED_RATE = 0.05
POLICY_LEARNING_RATE = 0.08
POLICY_MIN_WEIGHT = 0.15
POLICY_MAX_WEIGHT = 5.0
POLICY_EPSILON_EXPLORE = 0.12
POLICY_DECAY_RATE = 0.995
POLICY_RECENT_WINDOW = 300
SIMULATOR_SKIP_ENABLED = True
SIMULATOR_SKIP_THRESHOLD = 0.18
SIMULATOR_NEVER_SKIP_IF_PARENT_REWARD_ABOVE = 1.0
SIMULATOR_SKIP_ONLY_PENDING_CANDIDATES = True
SIMULATOR_MAX_CONSECUTIVE_SKIPS_PER_TEMPLATE = 3
LEGACY_FULL_IMPORT_ENABLED = True
LEGACY_FULL_IMPORT_ONCE = True
LEGACY_FULL_IMPORT_FORCE = False
LEGACY_FULL_IMPORT_BATCH_SIZE = 1000
LEGACY_FULL_IMPORT_MAX_RECORDS = 0
LINEAGE_VALUE_LOOKAHEAD = 3
LINEAGE_VALUE_DECAY = 0.75
MAX_AST_DEPTH = 12
MAX_OPERATOR_COUNT = 40
MAX_EXPR_LENGTH = 512
MAX_NESTED_TS = 5
INSIGHT_TOP_K = 5
INSIGHT_DISTILL_INTERVAL = 50
INSIGHT_MIN_SAMPLES = 20
INSIGHT_MAX_PROMPT_CLUSTERS = 16
STORAGE_MODE = "hybrid"
STORAGE_DB_PATH = "runtime/db/workflow.db"
STORAGE_LEGACY_EXPORT = True
STORAGE_QUEUE_BATCH_SIZE = 100
STORAGE_QUEUE_FLUSH_INTERVAL_SECONDS = 0.25
STORAGE_HEALTH_CHECK_INTERVAL_SECONDS = 60.0
STORAGE_RETENTION_DAYS = 14
ENABLE_PLATFORM_SC_CHECK = True
PLATFORM_SC_TIMEOUT_SECONDS = 90
ENABLE_REFACTORED_PIPELINE = False
ENABLE_REFACTORED_PIPELINE_SHADOW = True
ALLOW_OBSERVE_ONLY_PIPELINE = False
ENABLE_APP_CONTEXT = True
ENABLE_PLATFORM_SERVICES = True
ENABLE_DATA_SERVICES = True
ENABLE_STARTUP_HEALTHCHECK = True
HEALTHCHECK_AUTO_REPAIR = True
HEALTHCHECK_FORCE_LEGACY_ON_CRITICAL_WARNING = True
HEALTHCHECK_DISABLE_BROKEN_MODELS = True
HEALTHCHECK_AUDIT_PATH = "runtime/audit/healthcheck.jsonl"
ENABLE_LEARNING_GOVERNANCE = True
ENABLE_LONG_TERM_LEARNING_GUARD = True
ENABLE_AUTO_MODEL_DISABLE = True
ENABLE_AUTO_MODEL_ROLLBACK = True
ENABLE_AUTO_RETRAIN = True
ENABLE_MODEL_LIFECYCLE = True
ENABLE_ONLINE_MODEL_EVALUATION = True
ENABLE_SAMPLE_QUALITY_CHECK = True
FORCE_ENABLE_UNSAFE_ML_DECISIONS = False
ENABLE_ML_SYSTEM = True
ENABLE_ML_DEPENDENCIES_REQUIRED = False
ENABLE_SC_LEARNING = True
ENABLE_SC_MODEL_TRAINING = True
ENABLE_SC_MODEL_PREDICTION = True
ENABLE_SC_MODEL_FALLBACK = False
ENABLE_PARENT_LEARNING = True
ENABLE_PARENT_MODEL_TRAINING = True
ENABLE_PARENT_MODEL_PREDICTION = True
ENABLE_PARENT_MODEL_DECISION = False
ENABLE_POLICY_LEARNING = True
ENABLE_POLICY_MODEL_TRAINING = True
ENABLE_POLICY_MODEL_PREDICTION = True
ENABLE_POLICY_MODEL_DECISION = False
ENABLE_SIMULATOR_LEARNING = True
ENABLE_SIMULATOR_MODEL_TRAINING = True
ENABLE_SIMULATOR_MODEL_PREDICTION = True
ENABLE_SIMULATOR_MODEL_SKIP = False
ENABLE_EXPERIMENT_TRACKING = True
ENABLE_EXPERIMENT_DESIGN = True
ENABLE_EXPERIMENT_BUDGETING = True
EXPERIMENT_STATUS_PATH = "runtime/status/experiment_report.json"
DEFAULT_EXPERIMENT_ID = "default_experiment_v1"
EXPERIMENT_ASSIGNMENT_MODE = "tracking_only"
EXPERIMENT_BUDGET_MODE = "advisory"
EXPERIMENT_BUDGET_TOTAL_HINT = 200
EXPERIMENT_BUDGET_REFRESH_INTERVAL_ITERATIONS = 50
EXPERIMENT_BUDGET_REFRESH_INTERVAL_HOURS = 24
EXPERIMENT_BUDGET_LEGACY_MIN_RATIO = 0.15
EXPERIMENT_BUDGET_RANDOM_MIN_RATIO = 0.05
EXPERIMENT_BUDGET_TREATMENT_MAX_RATIO = 0.40
EXPERIMENT_BUDGET_MIN_SAMPLES_FOR_ADJUSTMENT = 30
EXPERIMENT_BUDGET_HIGH_FAILURE_RATE_THRESHOLD = 0.70
EXPERIMENT_BUDGET_HIGH_SC_ABS_MAX_THRESHOLD = 0.70
EXPERIMENT_BUDGET_HIGH_QUALITY_PASS_THRESHOLD = 0.30
EXPERIMENT_BUDGET_ALLOW_GOVERNANCE_VETO = True
EXPERIMENT_BUDGET_FAIL_OPEN_TRACKING_ONLY = True
ENABLE_DECISION_SNAPSHOTS = True
DECISION_SNAPSHOT_STATUS_PATH = "runtime/status/decision_snapshot_status.json"
DECISION_SNAPSHOT_RECORD_PARENT_SELECTION = True
DECISION_SNAPSHOT_RECORD_MUTATION_POLICY = True
DECISION_SNAPSHOT_RECORD_SC_FALLBACK = True
DECISION_SNAPSHOT_RECORD_SIMULATOR_SKIP = True
DECISION_SNAPSHOT_RECORD_EXPERIMENT_ARM_SELECTION = True
DECISION_SNAPSHOT_RECORD_BUDGET_PLAN_SELECTION = True
DECISION_SNAPSHOT_RECORD_CANDIDATE_ACCEPTANCE = True
DECISION_SNAPSHOT_FAIL_OPEN = True
ENABLE_OFFLINE_REPLAY = False
ENABLE_COUNTERFACTUAL_EVALUATION = False
ENABLE_SUPPORT_CHECKER = True
ENABLE_STRATEGY_REGISTRY = True
STRATEGY_SCOREBOARD_STATUS_PATH = "runtime/status/strategy_scoreboard.json"
STRATEGY_REGISTRY_MODE = "advisory"
STRATEGY_SCOREBOARD_AUTO_REFRESH = False
STRATEGY_SCOREBOARD_DEFAULT_LIMIT = 1000
STRATEGY_SCORE_MIN_SAMPLES = 30
STRATEGY_SCORE_MEDIUM_SAMPLES = 100
STRATEGY_SCORE_HIGH_SAMPLES = 500
STRATEGY_HIGH_SC_ABS_MAX_THRESHOLD = 0.70
STRATEGY_FAIL_OPEN = True
ENABLE_STRATEGY_CHAMPION_CHALLENGER = False
ENABLE_STRATEGY_BUDGET_ALLOCATOR = False
STRATEGY_BUDGET_ALLOCATOR_AUTO_APPLY = False
ENABLE_STRATEGY_PORTFOLIO = True
ENABLE_CHAMPION_CHALLENGER = True
ENABLE_CHALLENGER_LIVE_BUDGET = False
STRATEGY_DEFAULT_CHAMPION = "legacy_champion"
STRATEGY_CHALLENGER_LIVE_BUDGET = 0.0
STRATEGY_RANDOM_BASELINE_BUDGET = 0.0
PROMOTION_MIN_SAMPLES = 200
PROMOTION_MIN_SUPPORT_COVERAGE = 0.65
PROMOTION_MIN_REWARD_IMPROVEMENT = 0.05
PROMOTION_MAX_SC_RISK_DELTA = 0.03
PROMOTION_MAX_FAILURE_RATE_DELTA = 0.03
PROMOTION_REQUIRE_MODEL_VALIDATION_PASS = True
PROMOTION_REQUIRE_OFFLINE_REPLAY_PASS = True
ROLLBACK_REWARD_DROP_THRESHOLD = 0.10
ROLLBACK_SC_RISK_INCREASE_THRESHOLD = 0.05
ROLLBACK_FAILURE_RATE_INCREASE_THRESHOLD = 0.05
ROLLBACK_WINDOW_SIZE = 100
OFFLINE_REPLAY_MIN_DECISIONS = 100
OFFLINE_REPLAY_MAX_DECISIONS = 5000
OFFLINE_REPLAY_STATUS_PATH = "runtime/status/offline_replay_report.json"
OFFLINE_REPLAY_MODE = "advisory"
OFFLINE_REPLAY_AUTO_RUN = False
OFFLINE_REPLAY_DEFAULT_LIMIT = 1000
OFFLINE_REPLAY_MIN_OBSERVABLE_SAMPLES = 30
OFFLINE_REPLAY_BASELINE_POLICY = "legacy"
OFFLINE_REPLAY_INCLUDE_POLICIES = ["actual_chosen", "legacy", "model_choice", "experiment_choice", "budget_choice"]
OFFLINE_REPLAY_FAIL_OPEN = True
COUNTERFACTUAL_STATUS_PATH = "runtime/status/counterfactual_report.json"
COUNTERFACTUAL_MODE = "advisory"
COUNTERFACTUAL_AUTO_RUN = False
COUNTERFACTUAL_DEFAULT_LIMIT = 1000
COUNTERFACTUAL_MIN_EVIDENCE = 30
COUNTERFACTUAL_MIN_EFFECTIVE_EVIDENCE = 15
COUNTERFACTUAL_SIMILARITY_THRESHOLD = 0.55
COUNTERFACTUAL_HIGH_SC_ABS_MAX_THRESHOLD = 0.70
COUNTERFACTUAL_LOW_SUCCESS_RATE_THRESHOLD = 0.02
COUNTERFACTUAL_MEDIUM_CONFIDENCE_EVIDENCE = 100
COUNTERFACTUAL_HIGH_CONFIDENCE_EVIDENCE = 500
COUNTERFACTUAL_FAIL_OPEN = True
SUPPORT_MIN_ACTION_COUNT = 10
SUPPORT_MIN_CONTEXT_COUNT = 20
ENABLE_AUTO_PROMOTION = False
ENABLE_AUTO_ROLLBACK = False
ENABLE_DRIFT_MONITOR = False
ENABLE_INSIGHT_FEEDBACK_LEARNING = True
ML_MIN_SAMPLES = 200
ML_RETRAIN_EVERY_SAMPLES = 50
ML_VALIDATION_RATIO = 0.2
ML_MODEL_MIN_CONFIDENCE = 0.65
ML_MODEL_MAX_AGE_DAYS = 14
SC_MODEL_MAX_AGE_DAYS = 7
PARENT_MODEL_MAX_AGE_DAYS = 14
POLICY_MODEL_MAX_AGE_DAYS = 14
SIMULATOR_MODEL_MAX_AGE_DAYS = 7
SC_ONLINE_EVAL_MIN_SAMPLES = 30
PARENT_ONLINE_EVAL_MIN_SAMPLES = 30
POLICY_ONLINE_EVAL_MIN_SAMPLES = 30
SIMULATOR_ONLINE_EVAL_MIN_SAMPLES = 50
SIMULATOR_MAX_FALSE_SKIP_RATE = 0.02
ML_MIN_RETRAIN_INTERVAL_MINUTES = 30
ML_AUTO_RETRAIN_ON_DRIFT = True
ML_AUTO_DISABLE_ON_RETRAIN_FAILURE = True
ML_MAX_INVALID_SAMPLE_RATIO = 0.2
SC_MAX_INVALID_SAMPLE_RATIO = 0.05
MIN_LEGACY_BASELINE_BUDGET = 0.10
MIN_RANDOM_EXPLORATION_BUDGET = 0.03
SIMULATOR_VALIDATION_BACKTEST_BUDGET = 0.10
GOVERNANCE_STATUS_PATH = "runtime/status/governance_status.json"
ML_STATUS_PATH = "runtime/status/ml_status.json"
ML_REQUIRE_VALIDATION_PASS = True
ML_ALLOW_SKLEARN = True
ML_ALLOW_NO_SKLEARN_FALLBACK = True
ML_MODEL_ROOT = "runtime/models"
SC_LEARNING_MIN_SAMPLES = 200
SC_MODEL_MIN_CONFIDENCE = 0.65
SC_MODEL_MAX_MAE = 0.15
PARENT_LEARNING_MIN_SAMPLES = 200
PARENT_MODEL_MAX_MAE = 0.20
PARENT_MODEL_MIN_SUCCESS_RECALL = 0.60
POLICY_LEARNING_MIN_SAMPLES = 200
POLICY_MODEL_MAX_MAE = 0.25
POLICY_MIN_ACTION_COVERAGE = 0.30
SIMULATOR_LEARNING_MIN_SAMPLES = 200
SIMULATOR_MODEL_MIN_SUCCESS_RECALL = 0.70
SIMULATOR_MODEL_MAX_MAE = 0.25
ML_RANDOM_SEED = 42
SIMULATOR_PROTECTED_PARENT_REWARD = 0.5
ENABLE_ALPHA_REPRESENTATION = True
ENABLE_ALPHA_AST_PARSER = True
ENABLE_ALPHA_DISTANCE_FEATURES = True
ALPHA_PARSER_FAIL_SOFT = True
ALPHA_REPRESENTATION_CACHE_SIZE = 10000


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_str_list(value: Any, default: list[str]) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    return list(default)


def load_config() -> WorkflowConfig:
    raw: dict[str, Any] = {}
    if CONFIG_FILE.exists():
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))

    deepseek = raw.get("deepseek", {}) if isinstance(raw.get("deepseek"), dict) else {}
    thresholds = raw.get("thresholds", {}) if isinstance(raw.get("thresholds"), dict) else {}
    v2 = raw.get("v2", {}) if isinstance(raw.get("v2"), dict) else {}
    evolution = raw.get("evolution", {}) if isinstance(raw.get("evolution"), dict) else {}
    insight = raw.get("insight", {}) if isinstance(raw.get("insight"), dict) else {}
    sidecar = raw.get("sidecar_evolution", {}) if isinstance(raw.get("sidecar_evolution"), dict) else {}
    storage = raw.get("storage", {}) if isinstance(raw.get("storage"), dict) else {}
    platform_sc = raw.get("platform_sc", {}) if isinstance(raw.get("platform_sc"), dict) else {}

    config = WorkflowConfig(
        email=os.getenv("WORLDQUANT_EMAIL") or os.getenv("WQ_EMAIL") or raw.get("email", ""),
        password=os.getenv("WORLDQUANT_PASSWORD") or os.getenv("WQ_PASSWORD") or raw.get("password", ""),
        login_url=raw.get("login_url", LOGIN_URL),
        headless=_as_bool(os.getenv("WQ_HEADLESS"), _as_bool(raw.get("headless"), False)),
        slow_mo=_as_int(raw.get("slow_mo"), 0),
        browser_executable_path=os.getenv("WQ_BROWSER_EXECUTABLE") or raw.get("browser_executable_path", ""),
        max_templates=_as_int(os.getenv("WQ_MAX_TEMPLATES") or raw.get("max_templates"), 0),
        max_iterations_per_template=_as_int(
            os.getenv("WQ_MAX_ITERATIONS") or raw.get("max_iterations_per_template"),
            12,
        ),
        simulation_wait_seconds=_as_int(raw.get("simulation_wait_seconds"), 900),
        wait_result_max_seconds=_bounded_int(raw.get("wait_result_max_seconds"), 300, minimum=240, maximum=300),
        wait_result_start_timeout_seconds=_as_int(raw.get("wait_result_start_timeout_seconds"), 90),
        result_stable_reads=max(1, _as_int(raw.get("result_stable_reads"), 3)),
        result_poll_interval_seconds=max(0.5, _as_float(raw.get("result_poll_interval_seconds"), 2.0)),
        result_dom_stable_window_seconds=max(0.0, _as_float(raw.get("result_dom_stable_window_seconds"), 4.0)),
        freshness_accept_score=_as_int(raw.get("freshness_accept_score"), 70),
        enable_result_consistency_validation=_as_bool(raw.get("enable_result_consistency_validation"), True),
        enable_platform_sc_check=_as_bool(
            os.getenv("ENABLE_PLATFORM_SC_CHECK") or os.getenv("WQ_ENABLE_PLATFORM_SC_CHECK"),
            _as_bool(platform_sc.get("enabled", raw.get("enable_platform_sc_check")), ENABLE_PLATFORM_SC_CHECK),
        ),
        platform_sc_timeout_seconds=max(
            1,
            _as_int(
                os.getenv("PLATFORM_SC_TIMEOUT_SECONDS")
                or os.getenv("WQ_PLATFORM_SC_TIMEOUT_SECONDS")
                or platform_sc.get("timeout_seconds")
                or raw.get("platform_sc_timeout_seconds"),
                PLATFORM_SC_TIMEOUT_SECONDS,
            ),
        ),
        enable_refactored_pipeline=_as_bool(raw.get("enable_refactored_pipeline"), ENABLE_REFACTORED_PIPELINE),
        enable_refactored_pipeline_shadow=_as_bool(raw.get("enable_refactored_pipeline_shadow"), ENABLE_REFACTORED_PIPELINE_SHADOW),
        allow_observe_only_pipeline=_as_bool(raw.get("allow_observe_only_pipeline"), ALLOW_OBSERVE_ONLY_PIPELINE),
        enable_app_context=_as_bool(raw.get("enable_app_context"), ENABLE_APP_CONTEXT),
        enable_platform_services=_as_bool(raw.get("enable_platform_services"), ENABLE_PLATFORM_SERVICES),
        enable_data_services=_as_bool(raw.get("enable_data_services"), ENABLE_DATA_SERVICES),
        enable_startup_healthcheck=_as_bool(raw.get("enable_startup_healthcheck"), ENABLE_STARTUP_HEALTHCHECK),
        healthcheck_auto_repair=_as_bool(raw.get("healthcheck_auto_repair"), HEALTHCHECK_AUTO_REPAIR),
        healthcheck_force_legacy_on_critical_warning=_as_bool(raw.get("healthcheck_force_legacy_on_critical_warning"), HEALTHCHECK_FORCE_LEGACY_ON_CRITICAL_WARNING),
        healthcheck_disable_broken_models=_as_bool(raw.get("healthcheck_disable_broken_models"), HEALTHCHECK_DISABLE_BROKEN_MODELS),
        healthcheck_audit_path=str(raw.get("healthcheck_audit_path") or HEALTHCHECK_AUDIT_PATH),
        enable_learning_governance=_as_bool(raw.get("enable_learning_governance"), ENABLE_LEARNING_GOVERNANCE),
        enable_long_term_learning_guard=_as_bool(raw.get("enable_long_term_learning_guard"), ENABLE_LONG_TERM_LEARNING_GUARD),
        enable_auto_model_disable=_as_bool(raw.get("enable_auto_model_disable"), ENABLE_AUTO_MODEL_DISABLE),
        enable_auto_model_rollback=_as_bool(raw.get("enable_auto_model_rollback"), ENABLE_AUTO_MODEL_ROLLBACK),
        enable_auto_retrain=_as_bool(raw.get("enable_auto_retrain"), ENABLE_AUTO_RETRAIN),
        enable_model_lifecycle=_as_bool(raw.get("enable_model_lifecycle"), ENABLE_MODEL_LIFECYCLE),
        enable_online_model_evaluation=_as_bool(raw.get("enable_online_model_evaluation"), ENABLE_ONLINE_MODEL_EVALUATION),
        enable_sample_quality_check=_as_bool(raw.get("enable_sample_quality_check"), ENABLE_SAMPLE_QUALITY_CHECK),
        force_enable_unsafe_ml_decisions=_as_bool(raw.get("force_enable_unsafe_ml_decisions"), FORCE_ENABLE_UNSAFE_ML_DECISIONS),
        enable_ml_system=_as_bool(raw.get("enable_ml_system"), ENABLE_ML_SYSTEM),
        enable_ml_dependencies_required=_as_bool(raw.get("enable_ml_dependencies_required"), ENABLE_ML_DEPENDENCIES_REQUIRED),
        enable_sc_learning=_as_bool(raw.get("enable_sc_learning"), ENABLE_SC_LEARNING),
        enable_sc_model_training=_as_bool(raw.get("enable_sc_model_training"), ENABLE_SC_MODEL_TRAINING),
        enable_sc_model_prediction=_as_bool(raw.get("enable_sc_model_prediction"), ENABLE_SC_MODEL_PREDICTION),
        enable_sc_model_fallback=_as_bool(raw.get("enable_sc_model_fallback"), ENABLE_SC_MODEL_FALLBACK),
        enable_parent_learning=_as_bool(raw.get("enable_parent_learning"), ENABLE_PARENT_LEARNING),
        enable_parent_model_training=_as_bool(raw.get("enable_parent_model_training"), ENABLE_PARENT_MODEL_TRAINING),
        enable_parent_model_prediction=_as_bool(raw.get("enable_parent_model_prediction"), ENABLE_PARENT_MODEL_PREDICTION),
        enable_parent_model_decision=_as_bool(raw.get("enable_parent_model_decision"), ENABLE_PARENT_MODEL_DECISION),
        enable_policy_learning=_as_bool(raw.get("enable_policy_learning"), ENABLE_POLICY_LEARNING),
        enable_policy_model_training=_as_bool(raw.get("enable_policy_model_training"), ENABLE_POLICY_MODEL_TRAINING),
        enable_policy_model_prediction=_as_bool(raw.get("enable_policy_model_prediction"), ENABLE_POLICY_MODEL_PREDICTION),
        enable_policy_model_decision=_as_bool(raw.get("enable_policy_model_decision"), ENABLE_POLICY_MODEL_DECISION),
        enable_simulator_learning=_as_bool(raw.get("enable_simulator_learning"), ENABLE_SIMULATOR_LEARNING),
        enable_simulator_model_training=_as_bool(raw.get("enable_simulator_model_training"), ENABLE_SIMULATOR_MODEL_TRAINING),
        enable_simulator_model_prediction=_as_bool(raw.get("enable_simulator_model_prediction"), ENABLE_SIMULATOR_MODEL_PREDICTION),
        enable_simulator_model_skip=_as_bool(raw.get("enable_simulator_model_skip"), ENABLE_SIMULATOR_MODEL_SKIP),
        enable_experiment_tracking=_as_bool(raw.get("enable_experiment_tracking"), ENABLE_EXPERIMENT_TRACKING),
        enable_experiment_design=_as_bool(raw.get("enable_experiment_design"), ENABLE_EXPERIMENT_DESIGN),
        enable_experiment_budgeting=_as_bool(raw.get("enable_experiment_budgeting"), ENABLE_EXPERIMENT_BUDGETING),
        experiment_status_path=str(raw.get("experiment_status_path") or EXPERIMENT_STATUS_PATH),
        default_experiment_id=str(raw.get("default_experiment_id") or DEFAULT_EXPERIMENT_ID),
        experiment_assignment_mode=str(raw.get("experiment_assignment_mode") or EXPERIMENT_ASSIGNMENT_MODE),
        experiment_budget_mode=str(raw.get("experiment_budget_mode") or EXPERIMENT_BUDGET_MODE),
        experiment_budget_total_hint=max(0, _as_int(raw.get("experiment_budget_total_hint"), EXPERIMENT_BUDGET_TOTAL_HINT)),
        experiment_budget_refresh_interval_iterations=max(
            1,
            _as_int(raw.get("experiment_budget_refresh_interval_iterations"), EXPERIMENT_BUDGET_REFRESH_INTERVAL_ITERATIONS),
        ),
        experiment_budget_refresh_interval_hours=max(
            1,
            _as_int(raw.get("experiment_budget_refresh_interval_hours"), EXPERIMENT_BUDGET_REFRESH_INTERVAL_HOURS),
        ),
        experiment_budget_legacy_min_ratio=max(
            0.0,
            min(1.0, _as_float(raw.get("experiment_budget_legacy_min_ratio"), EXPERIMENT_BUDGET_LEGACY_MIN_RATIO)),
        ),
        experiment_budget_random_min_ratio=max(
            0.0,
            min(1.0, _as_float(raw.get("experiment_budget_random_min_ratio"), EXPERIMENT_BUDGET_RANDOM_MIN_RATIO)),
        ),
        experiment_budget_treatment_max_ratio=max(
            0.0,
            min(1.0, _as_float(raw.get("experiment_budget_treatment_max_ratio"), EXPERIMENT_BUDGET_TREATMENT_MAX_RATIO)),
        ),
        experiment_budget_min_samples_for_adjustment=max(
            1,
            _as_int(raw.get("experiment_budget_min_samples_for_adjustment"), EXPERIMENT_BUDGET_MIN_SAMPLES_FOR_ADJUSTMENT),
        ),
        experiment_budget_high_failure_rate_threshold=max(
            0.0,
            min(1.0, _as_float(raw.get("experiment_budget_high_failure_rate_threshold"), EXPERIMENT_BUDGET_HIGH_FAILURE_RATE_THRESHOLD)),
        ),
        experiment_budget_high_sc_abs_max_threshold=max(
            0.0,
            min(1.0, _as_float(raw.get("experiment_budget_high_sc_abs_max_threshold"), EXPERIMENT_BUDGET_HIGH_SC_ABS_MAX_THRESHOLD)),
        ),
        experiment_budget_high_quality_pass_threshold=max(
            0.0,
            min(1.0, _as_float(raw.get("experiment_budget_high_quality_pass_threshold"), EXPERIMENT_BUDGET_HIGH_QUALITY_PASS_THRESHOLD)),
        ),
        experiment_budget_allow_governance_veto=_as_bool(
            raw.get("experiment_budget_allow_governance_veto"),
            EXPERIMENT_BUDGET_ALLOW_GOVERNANCE_VETO,
        ),
        experiment_budget_fail_open_tracking_only=_as_bool(
            raw.get("experiment_budget_fail_open_tracking_only"),
            EXPERIMENT_BUDGET_FAIL_OPEN_TRACKING_ONLY,
        ),
        enable_decision_snapshots=_as_bool(raw.get("enable_decision_snapshots"), ENABLE_DECISION_SNAPSHOTS),
        decision_snapshot_status_path=str(raw.get("decision_snapshot_status_path") or DECISION_SNAPSHOT_STATUS_PATH),
        decision_snapshot_record_parent_selection=_as_bool(
            raw.get("decision_snapshot_record_parent_selection"), DECISION_SNAPSHOT_RECORD_PARENT_SELECTION
        ),
        decision_snapshot_record_mutation_policy=_as_bool(
            raw.get("decision_snapshot_record_mutation_policy"), DECISION_SNAPSHOT_RECORD_MUTATION_POLICY
        ),
        decision_snapshot_record_sc_fallback=_as_bool(raw.get("decision_snapshot_record_sc_fallback"), DECISION_SNAPSHOT_RECORD_SC_FALLBACK),
        decision_snapshot_record_simulator_skip=_as_bool(raw.get("decision_snapshot_record_simulator_skip"), DECISION_SNAPSHOT_RECORD_SIMULATOR_SKIP),
        decision_snapshot_record_experiment_arm_selection=_as_bool(
            raw.get("decision_snapshot_record_experiment_arm_selection"), DECISION_SNAPSHOT_RECORD_EXPERIMENT_ARM_SELECTION
        ),
        decision_snapshot_record_budget_plan_selection=_as_bool(
            raw.get("decision_snapshot_record_budget_plan_selection"), DECISION_SNAPSHOT_RECORD_BUDGET_PLAN_SELECTION
        ),
        decision_snapshot_record_candidate_acceptance=_as_bool(
            raw.get("decision_snapshot_record_candidate_acceptance"), DECISION_SNAPSHOT_RECORD_CANDIDATE_ACCEPTANCE
        ),
        decision_snapshot_fail_open=_as_bool(raw.get("decision_snapshot_fail_open"), DECISION_SNAPSHOT_FAIL_OPEN),
        enable_offline_replay=_as_bool(raw.get("enable_offline_replay"), ENABLE_OFFLINE_REPLAY),
        enable_counterfactual_evaluation=_as_bool(raw.get("enable_counterfactual_evaluation"), ENABLE_COUNTERFACTUAL_EVALUATION),
        enable_support_checker=_as_bool(raw.get("enable_support_checker"), ENABLE_SUPPORT_CHECKER),
        enable_strategy_registry=_as_bool(raw.get("enable_strategy_registry"), ENABLE_STRATEGY_REGISTRY),
        strategy_scoreboard_status_path=str(raw.get("strategy_scoreboard_status_path") or STRATEGY_SCOREBOARD_STATUS_PATH),
        strategy_registry_mode=str(raw.get("strategy_registry_mode") or STRATEGY_REGISTRY_MODE),
        strategy_scoreboard_auto_refresh=_as_bool(raw.get("strategy_scoreboard_auto_refresh"), STRATEGY_SCOREBOARD_AUTO_REFRESH),
        strategy_scoreboard_default_limit=max(1, _as_int(raw.get("strategy_scoreboard_default_limit"), STRATEGY_SCOREBOARD_DEFAULT_LIMIT)),
        strategy_score_min_samples=max(1, _as_int(raw.get("strategy_score_min_samples"), STRATEGY_SCORE_MIN_SAMPLES)),
        strategy_score_medium_samples=max(1, _as_int(raw.get("strategy_score_medium_samples"), STRATEGY_SCORE_MEDIUM_SAMPLES)),
        strategy_score_high_samples=max(1, _as_int(raw.get("strategy_score_high_samples"), STRATEGY_SCORE_HIGH_SAMPLES)),
        strategy_high_sc_abs_max_threshold=max(0.0, _as_float(raw.get("strategy_high_sc_abs_max_threshold"), STRATEGY_HIGH_SC_ABS_MAX_THRESHOLD)),
        strategy_fail_open=_as_bool(raw.get("strategy_fail_open"), STRATEGY_FAIL_OPEN),
        enable_strategy_champion_challenger=_as_bool(raw.get("enable_strategy_champion_challenger"), ENABLE_STRATEGY_CHAMPION_CHALLENGER),
        enable_strategy_budget_allocator=_as_bool(raw.get("enable_strategy_budget_allocator"), ENABLE_STRATEGY_BUDGET_ALLOCATOR),
        strategy_budget_allocator_auto_apply=_as_bool(raw.get("strategy_budget_allocator_auto_apply"), STRATEGY_BUDGET_ALLOCATOR_AUTO_APPLY),
        enable_strategy_portfolio=_as_bool(raw.get("enable_strategy_portfolio"), ENABLE_STRATEGY_PORTFOLIO),
        enable_champion_challenger=_as_bool(raw.get("enable_champion_challenger"), ENABLE_CHAMPION_CHALLENGER),
        enable_challenger_live_budget=_as_bool(raw.get("enable_challenger_live_budget"), ENABLE_CHALLENGER_LIVE_BUDGET),
        strategy_default_champion=str(raw.get("strategy_default_champion") or STRATEGY_DEFAULT_CHAMPION),
        strategy_challenger_live_budget=max(0.0, min(1.0, _as_float(raw.get("strategy_challenger_live_budget"), STRATEGY_CHALLENGER_LIVE_BUDGET))),
        strategy_random_baseline_budget=max(0.0, min(1.0, _as_float(raw.get("strategy_random_baseline_budget"), STRATEGY_RANDOM_BASELINE_BUDGET))),
        promotion_min_samples=max(1, _as_int(raw.get("promotion_min_samples"), PROMOTION_MIN_SAMPLES)),
        promotion_min_support_coverage=max(0.0, min(1.0, _as_float(raw.get("promotion_min_support_coverage"), PROMOTION_MIN_SUPPORT_COVERAGE))),
        promotion_min_reward_improvement=_as_float(raw.get("promotion_min_reward_improvement"), PROMOTION_MIN_REWARD_IMPROVEMENT),
        promotion_max_sc_risk_delta=_as_float(raw.get("promotion_max_sc_risk_delta"), PROMOTION_MAX_SC_RISK_DELTA),
        promotion_max_failure_rate_delta=_as_float(raw.get("promotion_max_failure_rate_delta"), PROMOTION_MAX_FAILURE_RATE_DELTA),
        promotion_require_model_validation_pass=_as_bool(raw.get("promotion_require_model_validation_pass"), PROMOTION_REQUIRE_MODEL_VALIDATION_PASS),
        promotion_require_offline_replay_pass=_as_bool(raw.get("promotion_require_offline_replay_pass"), PROMOTION_REQUIRE_OFFLINE_REPLAY_PASS),
        rollback_reward_drop_threshold=max(0.0, _as_float(raw.get("rollback_reward_drop_threshold"), ROLLBACK_REWARD_DROP_THRESHOLD)),
        rollback_sc_risk_increase_threshold=max(0.0, _as_float(raw.get("rollback_sc_risk_increase_threshold"), ROLLBACK_SC_RISK_INCREASE_THRESHOLD)),
        rollback_failure_rate_increase_threshold=max(0.0, _as_float(raw.get("rollback_failure_rate_increase_threshold"), ROLLBACK_FAILURE_RATE_INCREASE_THRESHOLD)),
        rollback_window_size=max(1, _as_int(raw.get("rollback_window_size"), ROLLBACK_WINDOW_SIZE)),
        offline_replay_min_decisions=max(1, _as_int(raw.get("offline_replay_min_decisions"), OFFLINE_REPLAY_MIN_DECISIONS)),
        offline_replay_max_decisions=max(1, _as_int(raw.get("offline_replay_max_decisions"), OFFLINE_REPLAY_MAX_DECISIONS)),
        offline_replay_status_path=str(raw.get("offline_replay_status_path") or OFFLINE_REPLAY_STATUS_PATH),
        offline_replay_mode=str(raw.get("offline_replay_mode") or OFFLINE_REPLAY_MODE),
        offline_replay_auto_run=_as_bool(raw.get("offline_replay_auto_run"), OFFLINE_REPLAY_AUTO_RUN),
        offline_replay_default_limit=max(1, _as_int(raw.get("offline_replay_default_limit"), OFFLINE_REPLAY_DEFAULT_LIMIT)),
        offline_replay_min_observable_samples=max(1, _as_int(raw.get("offline_replay_min_observable_samples"), OFFLINE_REPLAY_MIN_OBSERVABLE_SAMPLES)),
        offline_replay_baseline_policy=str(raw.get("offline_replay_baseline_policy") or OFFLINE_REPLAY_BASELINE_POLICY),
        offline_replay_include_policies=_as_str_list(raw.get("offline_replay_include_policies"), OFFLINE_REPLAY_INCLUDE_POLICIES),
        offline_replay_fail_open=_as_bool(raw.get("offline_replay_fail_open"), OFFLINE_REPLAY_FAIL_OPEN),
        counterfactual_status_path=str(raw.get("counterfactual_status_path") or COUNTERFACTUAL_STATUS_PATH),
        counterfactual_mode=str(raw.get("counterfactual_mode") or COUNTERFACTUAL_MODE),
        counterfactual_auto_run=_as_bool(raw.get("counterfactual_auto_run"), COUNTERFACTUAL_AUTO_RUN),
        counterfactual_default_limit=max(1, _as_int(raw.get("counterfactual_default_limit"), COUNTERFACTUAL_DEFAULT_LIMIT)),
        counterfactual_min_evidence=max(1, _as_int(raw.get("counterfactual_min_evidence"), COUNTERFACTUAL_MIN_EVIDENCE)),
        counterfactual_min_effective_evidence=max(1, _as_int(raw.get("counterfactual_min_effective_evidence"), COUNTERFACTUAL_MIN_EFFECTIVE_EVIDENCE)),
        counterfactual_similarity_threshold=max(0.0, min(1.0, _as_float(raw.get("counterfactual_similarity_threshold"), COUNTERFACTUAL_SIMILARITY_THRESHOLD))),
        counterfactual_high_sc_abs_max_threshold=max(0.0, _as_float(raw.get("counterfactual_high_sc_abs_max_threshold"), COUNTERFACTUAL_HIGH_SC_ABS_MAX_THRESHOLD)),
        counterfactual_low_success_rate_threshold=max(0.0, min(1.0, _as_float(raw.get("counterfactual_low_success_rate_threshold"), COUNTERFACTUAL_LOW_SUCCESS_RATE_THRESHOLD))),
        counterfactual_medium_confidence_evidence=max(1, _as_int(raw.get("counterfactual_medium_confidence_evidence"), COUNTERFACTUAL_MEDIUM_CONFIDENCE_EVIDENCE)),
        counterfactual_high_confidence_evidence=max(1, _as_int(raw.get("counterfactual_high_confidence_evidence"), COUNTERFACTUAL_HIGH_CONFIDENCE_EVIDENCE)),
        counterfactual_fail_open=_as_bool(raw.get("counterfactual_fail_open"), COUNTERFACTUAL_FAIL_OPEN),
        support_min_action_count=max(1, _as_int(raw.get("support_min_action_count"), SUPPORT_MIN_ACTION_COUNT)),
        support_min_context_count=max(1, _as_int(raw.get("support_min_context_count"), SUPPORT_MIN_CONTEXT_COUNT)),
        enable_auto_promotion=_as_bool(raw.get("enable_auto_promotion"), ENABLE_AUTO_PROMOTION),
        enable_auto_rollback=_as_bool(raw.get("enable_auto_rollback"), ENABLE_AUTO_ROLLBACK),
        enable_drift_monitor=_as_bool(raw.get("enable_drift_monitor"), ENABLE_DRIFT_MONITOR),
        enable_insight_feedback_learning=_as_bool(raw.get("enable_insight_feedback_learning"), ENABLE_INSIGHT_FEEDBACK_LEARNING),
        ml_min_samples=max(1, _as_int(raw.get("ml_min_samples"), ML_MIN_SAMPLES)),
        ml_retrain_every_samples=max(1, _as_int(raw.get("ml_retrain_every_samples"), ML_RETRAIN_EVERY_SAMPLES)),
        ml_validation_ratio=max(0.0, min(0.9, _as_float(raw.get("ml_validation_ratio"), ML_VALIDATION_RATIO))),
        ml_model_min_confidence=max(0.0, min(1.0, _as_float(raw.get("ml_model_min_confidence"), ML_MODEL_MIN_CONFIDENCE))),
        ml_model_max_age_days=max(1, _as_int(raw.get("ml_model_max_age_days"), ML_MODEL_MAX_AGE_DAYS)),
        sc_model_max_age_days=max(1, _as_int(raw.get("sc_model_max_age_days"), SC_MODEL_MAX_AGE_DAYS)),
        parent_model_max_age_days=max(1, _as_int(raw.get("parent_model_max_age_days"), PARENT_MODEL_MAX_AGE_DAYS)),
        policy_model_max_age_days=max(1, _as_int(raw.get("policy_model_max_age_days"), POLICY_MODEL_MAX_AGE_DAYS)),
        simulator_model_max_age_days=max(1, _as_int(raw.get("simulator_model_max_age_days"), SIMULATOR_MODEL_MAX_AGE_DAYS)),
        sc_online_eval_min_samples=max(1, _as_int(raw.get("sc_online_eval_min_samples"), SC_ONLINE_EVAL_MIN_SAMPLES)),
        parent_online_eval_min_samples=max(1, _as_int(raw.get("parent_online_eval_min_samples"), PARENT_ONLINE_EVAL_MIN_SAMPLES)),
        policy_online_eval_min_samples=max(1, _as_int(raw.get("policy_online_eval_min_samples"), POLICY_ONLINE_EVAL_MIN_SAMPLES)),
        simulator_online_eval_min_samples=max(1, _as_int(raw.get("simulator_online_eval_min_samples"), SIMULATOR_ONLINE_EVAL_MIN_SAMPLES)),
        simulator_max_false_skip_rate=max(0.0, _as_float(raw.get("simulator_max_false_skip_rate"), SIMULATOR_MAX_FALSE_SKIP_RATE)),
        ml_min_retrain_interval_minutes=max(0, _as_int(raw.get("ml_min_retrain_interval_minutes"), ML_MIN_RETRAIN_INTERVAL_MINUTES)),
        ml_auto_retrain_on_drift=_as_bool(raw.get("ml_auto_retrain_on_drift"), ML_AUTO_RETRAIN_ON_DRIFT),
        ml_auto_disable_on_retrain_failure=_as_bool(raw.get("ml_auto_disable_on_retrain_failure"), ML_AUTO_DISABLE_ON_RETRAIN_FAILURE),
        ml_max_invalid_sample_ratio=max(0.0, min(1.0, _as_float(raw.get("ml_max_invalid_sample_ratio"), ML_MAX_INVALID_SAMPLE_RATIO))),
        sc_max_invalid_sample_ratio=max(0.0, min(1.0, _as_float(raw.get("sc_max_invalid_sample_ratio"), SC_MAX_INVALID_SAMPLE_RATIO))),
        min_legacy_baseline_budget=max(0.0, min(1.0, _as_float(raw.get("min_legacy_baseline_budget"), MIN_LEGACY_BASELINE_BUDGET))),
        min_random_exploration_budget=max(0.0, min(1.0, _as_float(raw.get("min_random_exploration_budget"), MIN_RANDOM_EXPLORATION_BUDGET))),
        simulator_validation_backtest_budget=max(0.0, min(1.0, _as_float(raw.get("simulator_validation_backtest_budget"), SIMULATOR_VALIDATION_BACKTEST_BUDGET))),
        governance_status_path=str(raw.get("governance_status_path") or GOVERNANCE_STATUS_PATH),
        ml_status_path=str(raw.get("ml_status_path") or ML_STATUS_PATH),
        ml_require_validation_pass=_as_bool(raw.get("ml_require_validation_pass"), ML_REQUIRE_VALIDATION_PASS),
        ml_allow_sklearn=_as_bool(raw.get("ml_allow_sklearn"), ML_ALLOW_SKLEARN),
        ml_allow_no_sklearn_fallback=_as_bool(raw.get("ml_allow_no_sklearn_fallback"), ML_ALLOW_NO_SKLEARN_FALLBACK),
        ml_model_root=str(raw.get("ml_model_root") or ML_MODEL_ROOT),
        sc_learning_min_samples=max(1, _as_int(raw.get("sc_learning_min_samples"), SC_LEARNING_MIN_SAMPLES)),
        sc_model_min_confidence=max(0.0, min(1.0, _as_float(raw.get("sc_model_min_confidence"), SC_MODEL_MIN_CONFIDENCE))),
        sc_model_max_mae=max(0.0, _as_float(raw.get("sc_model_max_mae"), SC_MODEL_MAX_MAE)),
        parent_learning_min_samples=max(1, _as_int(raw.get("parent_learning_min_samples"), PARENT_LEARNING_MIN_SAMPLES)),
        parent_model_max_mae=max(0.0, _as_float(raw.get("parent_model_max_mae"), PARENT_MODEL_MAX_MAE)),
        parent_model_min_success_recall=max(0.0, min(1.0, _as_float(raw.get("parent_model_min_success_recall"), PARENT_MODEL_MIN_SUCCESS_RECALL))),
        policy_learning_min_samples=max(1, _as_int(raw.get("policy_learning_min_samples"), POLICY_LEARNING_MIN_SAMPLES)),
        policy_model_max_mae=max(0.0, _as_float(raw.get("policy_model_max_mae"), POLICY_MODEL_MAX_MAE)),
        policy_min_action_coverage=max(0.0, min(1.0, _as_float(raw.get("policy_min_action_coverage"), POLICY_MIN_ACTION_COVERAGE))),
        simulator_learning_min_samples=max(1, _as_int(raw.get("simulator_learning_min_samples"), SIMULATOR_LEARNING_MIN_SAMPLES)),
        simulator_model_min_success_recall=max(0.0, min(1.0, _as_float(raw.get("simulator_model_min_success_recall"), SIMULATOR_MODEL_MIN_SUCCESS_RECALL))),
        simulator_model_max_mae=max(0.0, _as_float(raw.get("simulator_model_max_mae"), SIMULATOR_MODEL_MAX_MAE)),
        ml_random_seed=_as_int(raw.get("ml_random_seed"), ML_RANDOM_SEED),
        simulator_protected_parent_reward=_as_float(raw.get("simulator_protected_parent_reward"), SIMULATOR_PROTECTED_PARENT_REWARD),
        enable_alpha_representation=_as_bool(raw.get("enable_alpha_representation"), ENABLE_ALPHA_REPRESENTATION),
        enable_alpha_ast_parser=_as_bool(raw.get("enable_alpha_ast_parser"), ENABLE_ALPHA_AST_PARSER),
        enable_alpha_distance_features=_as_bool(raw.get("enable_alpha_distance_features"), ENABLE_ALPHA_DISTANCE_FEATURES),
        alpha_parser_fail_soft=_as_bool(raw.get("alpha_parser_fail_soft"), ALPHA_PARSER_FAIL_SOFT),
        alpha_representation_cache_size=max(1, _as_int(raw.get("alpha_representation_cache_size"), ALPHA_REPRESENTATION_CACHE_SIZE)),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY") or deepseek.get("api_key", ""),
        deepseek_base_url=deepseek.get("base_url", "https://api.deepseek.com"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL") or deepseek.get("model", "deepseek-v4-pro"),
        deepseek_temperature=_as_float(deepseek.get("temperature"), 0.15),
        deepseek_max_tokens=_as_int(deepseek.get("max_tokens"), 3000),
        enable_v2_engine=_as_bool(
            os.getenv("ENABLE_V2_ENGINE") or os.getenv("WQ_ENABLE_V2_ENGINE"),
            _as_bool(v2.get("enable_v2_engine", raw.get("enable_v2_engine")), ENABLE_V2_ENGINE),
        ),
        enable_behavior_sc_pipeline=_as_bool(
            os.getenv("ENABLE_BEHAVIOR_SC_PIPELINE") or os.getenv("WQ_ENABLE_BEHAVIOR_SC_PIPELINE"),
            _as_bool(
                v2.get("enable_behavior_sc_pipeline", raw.get("enable_behavior_sc_pipeline")),
                ENABLE_BEHAVIOR_SC_PIPELINE,
            ),
        ),
        v2_rollout_phase=_as_int(
            os.getenv("V2_ROLLOUT_PHASE")
            or os.getenv("WQ_V2_ROLLOUT_PHASE")
            or v2.get("rollout_phase")
            or raw.get("v2_rollout_phase"),
            V2_ROLLOUT_PHASE,
        ),
        enable_survival_memory=_as_bool(
            os.getenv("ENABLE_SURVIVAL_MEMORY") or os.getenv("WQ_ENABLE_SURVIVAL_MEMORY"),
            _as_bool(
                evolution.get("enable_survival_memory", raw.get("enable_survival_memory")),
                ENABLE_SURVIVAL_MEMORY,
            ),
        ),
        enable_pending_reward=_as_bool(
            os.getenv("ENABLE_PENDING_REWARD") or os.getenv("WQ_ENABLE_PENDING_REWARD"),
            _as_bool(
                evolution.get("enable_pending_reward", raw.get("enable_pending_reward")),
                ENABLE_PENDING_REWARD,
            ),
        ),
        enable_template_governance=_as_bool(
            os.getenv("ENABLE_TEMPLATE_GOVERNANCE") or os.getenv("WQ_ENABLE_TEMPLATE_GOVERNANCE"),
            _as_bool(
                evolution.get("enable_template_governance", raw.get("enable_template_governance")),
                ENABLE_TEMPLATE_GOVERNANCE,
            ),
        ),
        enable_exploration_pressure=_as_bool(
            os.getenv("ENABLE_EXPLORATION_PRESSURE") or os.getenv("WQ_ENABLE_EXPLORATION_PRESSURE"),
            _as_bool(
                evolution.get("enable_exploration_pressure", raw.get("enable_exploration_pressure")),
                ENABLE_EXPLORATION_PRESSURE,
            ),
        ),
        enable_adaptive_legacy=_as_bool(
            os.getenv("ENABLE_ADAPTIVE_LEGACY") or os.getenv("WQ_ENABLE_ADAPTIVE_LEGACY"),
            _as_bool(
                evolution.get("enable_adaptive_legacy", raw.get("enable_adaptive_legacy")),
                ENABLE_ADAPTIVE_LEGACY,
            ),
        ),
        enable_research_insights=_as_bool(
            os.getenv("ENABLE_RESEARCH_INSIGHTS") or os.getenv("WQ_ENABLE_RESEARCH_INSIGHTS"),
            _as_bool(
                insight.get("enable_research_insights", raw.get("enable_research_insights")),
                ENABLE_RESEARCH_INSIGHTS,
            ),
        ),
        enable_sidecar_evolution=_as_bool(
            os.getenv("ENABLE_SIDECAR_EVOLUTION") or os.getenv("WQ_ENABLE_SIDECAR_EVOLUTION"),
            _as_bool(
                sidecar.get("enable_sidecar_evolution", raw.get("enable_sidecar_evolution")),
                ENABLE_SIDECAR_EVOLUTION,
            ),
        ),
        enable_population_engine=_as_bool(
            os.getenv("ENABLE_POPULATION_ENGINE") or os.getenv("WQ_ENABLE_POPULATION_ENGINE"),
            _as_bool(
                sidecar.get("enable_population_engine", raw.get("enable_population_engine")),
                ENABLE_POPULATION_ENGINE,
            ),
        ),
        enable_evolution_policy=_as_bool(
            os.getenv("ENABLE_EVOLUTION_POLICY") or os.getenv("WQ_ENABLE_EVOLUTION_POLICY"),
            _as_bool(
                sidecar.get("enable_evolution_policy", raw.get("enable_evolution_policy")),
                ENABLE_EVOLUTION_POLICY,
            ),
        ),
        enable_alpha_simulator=_as_bool(
            os.getenv("ENABLE_ALPHA_SIMULATOR") or os.getenv("WQ_ENABLE_ALPHA_SIMULATOR"),
            _as_bool(
                sidecar.get("enable_alpha_simulator", raw.get("enable_alpha_simulator")),
                ENABLE_ALPHA_SIMULATOR,
            ),
        ),
        enable_lineage_value=_as_bool(
            os.getenv("ENABLE_LINEAGE_VALUE") or os.getenv("WQ_ENABLE_LINEAGE_VALUE"),
            _as_bool(sidecar.get("enable_lineage_value", raw.get("enable_lineage_value")), ENABLE_LINEAGE_VALUE),
        ),
        enable_alpha_graph=_as_bool(
            os.getenv("ENABLE_ALPHA_GRAPH") or os.getenv("WQ_ENABLE_ALPHA_GRAPH"),
            _as_bool(sidecar.get("enable_alpha_graph", raw.get("enable_alpha_graph")), ENABLE_ALPHA_GRAPH),
        ),
        enable_ast_evolution=_as_bool(
            os.getenv("ENABLE_AST_EVOLUTION") or os.getenv("WQ_ENABLE_AST_EVOLUTION"),
            _as_bool(sidecar.get("enable_ast_evolution", raw.get("enable_ast_evolution")), ENABLE_AST_EVOLUTION),
        ),
        enable_crossover=_as_bool(
            os.getenv("ENABLE_CROSSOVER") or os.getenv("WQ_ENABLE_CROSSOVER"),
            _as_bool(sidecar.get("enable_crossover", raw.get("enable_crossover")), ENABLE_CROSSOVER),
        ),
        enable_experimental_evolution_decisions=_as_bool(
            os.getenv("ENABLE_EXPERIMENTAL_EVOLUTION_DECISIONS")
            or os.getenv("WQ_ENABLE_EXPERIMENTAL_EVOLUTION_DECISIONS"),
            _as_bool(
                sidecar.get("enable_experimental_evolution_decisions", raw.get("enable_experimental_evolution_decisions")),
                ENABLE_EXPERIMENTAL_EVOLUTION_DECISIONS,
            ),
        ),
        simulator_low_confidence_threshold=_as_float(
            os.getenv("SIMULATOR_LOW_CONFIDENCE_THRESHOLD")
            or os.getenv("WQ_SIMULATOR_LOW_CONFIDENCE_THRESHOLD")
            or sidecar.get("simulator_low_confidence_threshold")
            or raw.get("simulator_low_confidence_threshold"),
            SIMULATOR_LOW_CONFIDENCE_THRESHOLD,
        ),
        population_size=max(
            1,
            _as_int(
                os.getenv("WQ_POPULATION_SIZE") or sidecar.get("population_size") or evolution.get("population_size") or raw.get("population_size"),
                POPULATION_SIZE,
            ),
        ),
        population_elite_size=max(
            0,
            _as_int(
                os.getenv("WQ_POPULATION_ELITE_SIZE")
                or sidecar.get("population_elite_size")
                or evolution.get("population_elite_size")
                or raw.get("population_elite_size"),
                POPULATION_ELITE_SIZE,
            ),
        ),
        population_max_same_family_ratio=_as_float(
            sidecar.get("population_max_same_family_ratio")
            or evolution.get("population_max_same_family_ratio")
            or raw.get("population_max_same_family_ratio"),
            POPULATION_MAX_SAME_FAMILY_RATIO,
        ),
        population_tournament_k=max(
            1,
            _as_int(
                sidecar.get("population_tournament_k") or evolution.get("population_tournament_k") or raw.get("population_tournament_k"),
                POPULATION_TOURNAMENT_K,
            ),
        ),
        crossover_rate=_as_float(
            os.getenv("WQ_CROSSOVER_RATE") or sidecar.get("crossover_rate") or evolution.get("crossover_rate") or raw.get("crossover_rate"),
            CROSSOVER_RATE,
        ),
        max_crossover_attempts=max(
            1,
            _as_int(
                os.getenv("WQ_MAX_CROSSOVER_ATTEMPTS")
                or sidecar.get("max_crossover_attempts")
                or evolution.get("max_crossover_attempts")
                or raw.get("max_crossover_attempts"),
                MAX_CROSSOVER_ATTEMPTS,
            ),
        ),
        crossover_random_subtree_selection=_as_bool(
            os.getenv("WQ_CROSSOVER_RANDOM_SUBTREE_SELECTION")
            or sidecar.get("crossover_random_subtree_selection")
            or evolution.get("crossover_random_subtree_selection")
            or raw.get("crossover_random_subtree_selection"),
            CROSSOVER_RANDOM_SUBTREE_SELECTION,
        ),
        crossover_use_graph_bias=_as_bool(
            os.getenv("WQ_CROSSOVER_USE_GRAPH_BIAS")
            or sidecar.get("crossover_use_graph_bias")
            or evolution.get("crossover_use_graph_bias")
            or raw.get("crossover_use_graph_bias"),
            CROSSOVER_USE_GRAPH_BIAS,
        ),
        crossover_random_seed=(
            None
            if (
                os.getenv("WQ_CROSSOVER_RANDOM_SEED")
                or sidecar.get("crossover_random_seed")
                or evolution.get("crossover_random_seed")
                or raw.get("crossover_random_seed")
            )
            in {None, ""}
            else _as_int(
                os.getenv("WQ_CROSSOVER_RANDOM_SEED")
                or sidecar.get("crossover_random_seed")
                or evolution.get("crossover_random_seed")
                or raw.get("crossover_random_seed"),
                0,
            )
        ),
        mutation_rate=_as_float(
            os.getenv("WQ_MUTATION_RATE") or sidecar.get("mutation_rate") or evolution.get("mutation_rate") or raw.get("mutation_rate"),
            MUTATION_RATE,
        ),
        random_seed_rate=_as_float(
            os.getenv("WQ_RANDOM_SEED_RATE")
            or sidecar.get("random_seed_rate")
            or evolution.get("random_seed_rate")
            or raw.get("random_seed_rate"),
            RANDOM_SEED_RATE,
        ),
        policy_learning_rate=_as_float(
            os.getenv("WQ_POLICY_LEARNING_RATE")
            or sidecar.get("policy_learning_rate")
            or evolution.get("policy_learning_rate")
            or raw.get("policy_learning_rate"),
            POLICY_LEARNING_RATE,
        ),
        policy_min_weight=_as_float(sidecar.get("policy_min_weight") or evolution.get("policy_min_weight") or raw.get("policy_min_weight"), POLICY_MIN_WEIGHT),
        policy_max_weight=_as_float(sidecar.get("policy_max_weight") or evolution.get("policy_max_weight") or raw.get("policy_max_weight"), POLICY_MAX_WEIGHT),
        policy_epsilon_explore=_as_float(
            os.getenv("WQ_POLICY_EPSILON_EXPLORE")
            or sidecar.get("policy_epsilon_explore")
            or evolution.get("policy_epsilon_explore")
            or raw.get("policy_epsilon_explore"),
            POLICY_EPSILON_EXPLORE,
        ),
        policy_decay_rate=_as_float(
            os.getenv("WQ_POLICY_DECAY_RATE")
            or sidecar.get("policy_decay_rate")
            or evolution.get("policy_decay_rate")
            or raw.get("policy_decay_rate"),
            POLICY_DECAY_RATE,
        ),
        policy_recent_window=max(
            1,
            _as_int(
                os.getenv("WQ_POLICY_RECENT_WINDOW")
                or sidecar.get("policy_recent_window")
                or evolution.get("policy_recent_window")
                or raw.get("policy_recent_window"),
                POLICY_RECENT_WINDOW,
            ),
        ),
        simulator_skip_enabled=_as_bool(
            os.getenv("WQ_SIMULATOR_SKIP_ENABLED")
            or sidecar.get("simulator_skip_enabled", evolution.get("simulator_skip_enabled", raw.get("simulator_skip_enabled"))),
            SIMULATOR_SKIP_ENABLED,
        ),
        simulator_skip_threshold=_as_float(
            os.getenv("WQ_SIMULATOR_SKIP_THRESHOLD")
            or sidecar.get("simulator_skip_threshold")
            or evolution.get("simulator_skip_threshold")
            or raw.get("simulator_skip_threshold"),
            SIMULATOR_SKIP_THRESHOLD,
        ),
        simulator_never_skip_if_parent_reward_above=_as_float(
            sidecar.get("simulator_never_skip_if_parent_reward_above")
            or evolution.get("simulator_never_skip_if_parent_reward_above")
            or raw.get("simulator_never_skip_if_parent_reward_above"),
            SIMULATOR_NEVER_SKIP_IF_PARENT_REWARD_ABOVE,
        ),
        simulator_skip_only_pending_candidates=_as_bool(
            os.getenv("WQ_SIMULATOR_SKIP_ONLY_PENDING_CANDIDATES")
            or sidecar.get("simulator_skip_only_pending_candidates")
            or evolution.get("simulator_skip_only_pending_candidates")
            or raw.get("simulator_skip_only_pending_candidates"),
            SIMULATOR_SKIP_ONLY_PENDING_CANDIDATES,
        ),
        simulator_max_consecutive_skips_per_template=max(
            1,
            _as_int(
                os.getenv("WQ_SIMULATOR_MAX_CONSECUTIVE_SKIPS_PER_TEMPLATE")
                or sidecar.get("simulator_max_consecutive_skips_per_template")
                or evolution.get("simulator_max_consecutive_skips_per_template")
                or raw.get("simulator_max_consecutive_skips_per_template"),
                SIMULATOR_MAX_CONSECUTIVE_SKIPS_PER_TEMPLATE,
            ),
        ),
        legacy_full_import_enabled=_as_bool(
            os.getenv("WQ_LEGACY_FULL_IMPORT_ENABLED")
            or sidecar.get("legacy_full_import_enabled")
            or evolution.get("legacy_full_import_enabled")
            or raw.get("legacy_full_import_enabled"),
            LEGACY_FULL_IMPORT_ENABLED,
        ),
        legacy_full_import_once=_as_bool(
            os.getenv("WQ_LEGACY_FULL_IMPORT_ONCE")
            or sidecar.get("legacy_full_import_once")
            or evolution.get("legacy_full_import_once")
            or raw.get("legacy_full_import_once"),
            LEGACY_FULL_IMPORT_ONCE,
        ),
        legacy_full_import_force=_as_bool(
            os.getenv("WQ_LEGACY_FULL_IMPORT_FORCE")
            or sidecar.get("legacy_full_import_force")
            or evolution.get("legacy_full_import_force")
            or raw.get("legacy_full_import_force"),
            LEGACY_FULL_IMPORT_FORCE,
        ),
        legacy_full_import_batch_size=max(
            1,
            _as_int(
                os.getenv("WQ_LEGACY_FULL_IMPORT_BATCH_SIZE")
                or sidecar.get("legacy_full_import_batch_size")
                or evolution.get("legacy_full_import_batch_size")
                or raw.get("legacy_full_import_batch_size"),
                LEGACY_FULL_IMPORT_BATCH_SIZE,
            ),
        ),
        legacy_full_import_max_records=max(
            0,
            _as_int(
                os.getenv("WQ_LEGACY_FULL_IMPORT_MAX_RECORDS")
                or sidecar.get("legacy_full_import_max_records")
                or evolution.get("legacy_full_import_max_records")
                or raw.get("legacy_full_import_max_records"),
                LEGACY_FULL_IMPORT_MAX_RECORDS,
            ),
        ),
        lineage_value_lookahead=max(
            1,
            _as_int(
                os.getenv("WQ_LINEAGE_VALUE_LOOKAHEAD")
                or sidecar.get("lineage_value_lookahead")
                or evolution.get("lineage_value_lookahead")
                or raw.get("lineage_value_lookahead"),
                LINEAGE_VALUE_LOOKAHEAD,
            ),
        ),
        lineage_value_decay=_as_float(sidecar.get("lineage_value_decay") or evolution.get("lineage_value_decay") or raw.get("lineage_value_decay"), LINEAGE_VALUE_DECAY),
        max_ast_depth=_as_int(
            os.getenv("MAX_AST_DEPTH") or os.getenv("WQ_MAX_AST_DEPTH") or sidecar.get("max_ast_depth") or raw.get("max_ast_depth"),
            MAX_AST_DEPTH,
        ),
        max_operator_count=_as_int(
            os.getenv("MAX_OPERATOR_COUNT")
            or os.getenv("WQ_MAX_OPERATOR_COUNT")
            or sidecar.get("max_operator_count")
            or raw.get("max_operator_count"),
            MAX_OPERATOR_COUNT,
        ),
        max_expr_length=_as_int(
            os.getenv("MAX_EXPR_LENGTH")
            or os.getenv("WQ_MAX_EXPR_LENGTH")
            or sidecar.get("max_expr_length")
            or raw.get("max_expr_length"),
            MAX_EXPR_LENGTH,
        ),
        max_nested_ts=_as_int(
            os.getenv("MAX_NESTED_TS") or os.getenv("WQ_MAX_NESTED_TS") or sidecar.get("max_nested_ts") or raw.get("max_nested_ts"),
            MAX_NESTED_TS,
        ),
        insight_top_k=_as_int(
            os.getenv("INSIGHT_TOP_K") or os.getenv("WQ_INSIGHT_TOP_K") or insight.get("top_k") or raw.get("insight_top_k"),
            INSIGHT_TOP_K,
        ),
        insight_distill_interval=_as_int(
            os.getenv("INSIGHT_DISTILL_INTERVAL")
            or os.getenv("WQ_INSIGHT_DISTILL_INTERVAL")
            or insight.get("distill_interval")
            or raw.get("insight_distill_interval"),
            INSIGHT_DISTILL_INTERVAL,
        ),
        insight_min_samples=_as_int(
            os.getenv("INSIGHT_MIN_SAMPLES")
            or os.getenv("WQ_INSIGHT_MIN_SAMPLES")
            or insight.get("min_samples")
            or raw.get("insight_min_samples"),
            INSIGHT_MIN_SAMPLES,
        ),
        insight_max_prompt_clusters=_as_int(
            os.getenv("INSIGHT_MAX_PROMPT_CLUSTERS")
            or os.getenv("WQ_INSIGHT_MAX_PROMPT_CLUSTERS")
            or insight.get("max_prompt_clusters")
            or raw.get("insight_max_prompt_clusters"),
            INSIGHT_MAX_PROMPT_CLUSTERS,
        ),
        storage_mode=_storage_mode(os.getenv("WQ_STORAGE_MODE") or storage.get("mode") or raw.get("storage_mode")),
        storage_db_path=str(os.getenv("WQ_STORAGE_DB_PATH") or storage.get("db_path") or raw.get("storage_db_path") or STORAGE_DB_PATH),
        storage_legacy_export=_as_bool(storage.get("legacy_export", raw.get("storage_legacy_export")), STORAGE_LEGACY_EXPORT),
        storage_queue_batch_size=max(
            1,
            _as_int(storage.get("queue_batch_size", raw.get("storage_queue_batch_size")), STORAGE_QUEUE_BATCH_SIZE),
        ),
        storage_queue_flush_interval_seconds=max(
            0.05,
            _as_float(
                storage.get("queue_flush_interval_seconds", raw.get("storage_queue_flush_interval_seconds")),
                STORAGE_QUEUE_FLUSH_INTERVAL_SECONDS,
            ),
        ),
        storage_health_check_interval_seconds=max(
            5.0,
            _as_float(
                storage.get("health_check_interval_seconds", raw.get("storage_health_check_interval_seconds")),
                STORAGE_HEALTH_CHECK_INTERVAL_SECONDS,
            ),
        ),
        storage_retention_days=max(
            1,
            _as_int(storage.get("retention_days", raw.get("storage_retention_days")), STORAGE_RETENTION_DAYS),
        ),
        selectors=raw.get("selectors", {}) if isinstance(raw.get("selectors"), dict) else {},
    )
    config.thresholds.update({key: _as_float(value, config.thresholds.get(key, 0.0)) for key, value in thresholds.items()})
    return config


def _bounded_int(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    parsed = _as_int(value, default)
    return max(minimum, min(maximum, parsed))


def _storage_mode(value: Any) -> str:
    mode = str(value or STORAGE_MODE).strip().lower()
    if mode not in {"hybrid", "sqlite_only", "jsonl_only"}:
        return STORAGE_MODE
    return mode


def selector_config(config: WorkflowConfig, name: str, defaults: list[str]) -> list[str]:
    configured = config.selectors.get(name)
    if isinstance(configured, list) and configured:
        return [str(item) for item in configured]
    return defaults
