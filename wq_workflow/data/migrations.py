from __future__ import annotations

import sqlite3


REFRACTOR_TABLE_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS ml_model_registry (
        model_id TEXT PRIMARY KEY,
        task_name TEXT,
        model_version TEXT,
        model_path TEXT,
        feature_schema_json TEXT,
        train_sample_count INTEGER,
        validation_metric_json TEXT,
        is_active INTEGER DEFAULT 0,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS ml_prediction_audit (
        prediction_id TEXT PRIMARY KEY,
        task_name TEXT,
        alpha_id TEXT,
        model_version TEXT,
        features_json TEXT,
        prediction_json TEXT,
        confidence REAL,
        final_decision TEXT,
        final_source TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS ml_training_samples (
        sample_id TEXT PRIMARY KEY,
        task_name TEXT,
        alpha_id TEXT,
        features_json TEXT,
        label_json TEXT,
        context_json TEXT,
        raw_payload TEXT,
        created_at TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS ml_model_events (
        event_id TEXT PRIMARY KEY,
        task_name TEXT,
        model_version TEXT,
        event_type TEXT,
        severity TEXT,
        message TEXT,
        action_taken TEXT,
        raw_payload TEXT,
        created_at TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS ml_online_evaluation (
        eval_id TEXT PRIMARY KEY,
        task_name TEXT,
        model_version TEXT,
        window_start TEXT,
        window_end TEXT,
        sample_count INTEGER,
        prediction_count INTEGER,
        success_count INTEGER,
        failure_count INTEGER,
        mae REAL,
        rmse REAL,
        precision_score REAL,
        recall_score REAL,
        hit_rate REAL,
        avg_reward_delta REAL,
        avg_sc_error REAL,
        drift_score REAL,
        degradation_score REAL,
        recommended_action TEXT,
        raw_payload TEXT,
        created_at TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS decision_snapshots (
        decision_id TEXT PRIMARY KEY,
        decision_type TEXT,
        workflow_run_id TEXT,
        iteration INTEGER,
        alpha_id TEXT,
        experiment_id TEXT,
        arm_id TEXT,
        budget_plan_id TEXT,
        available_actions_json TEXT,
        chosen_action_json TEXT,
        legacy_choice_json TEXT,
        model_choice_json TEXT,
        experiment_choice_json TEXT,
        governance_decision TEXT,
        features_json TEXT,
        scores_json TEXT,
        context_json TEXT,
        actual_result_json TEXT,
        reward REAL,
        platform_sc_status TEXT,
        platform_sc_abs_max REAL,
        success INTEGER,
        quality_passed INTEGER,
        created_at TEXT,
        updated_at TEXT,
        raw_payload TEXT,
        action_scores_json TEXT,
        selection_reason TEXT,
        legacy_score REAL,
        model_score REAL,
        propensity REAL,
        model_version TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS decision_outcomes (
        outcome_id TEXT PRIMARY KEY,
        decision_id TEXT,
        decision_type TEXT,
        alpha_id TEXT,
        success INTEGER,
        reward REAL,
        reward_delta REAL,
        sharpe REAL,
        fitness REAL,
        returns REAL,
        turnover REAL,
        drawdown REAL,
        margin REAL,
        platform_sc_status TEXT,
        platform_sc_abs_max REAL,
        quality_passed INTEGER,
        failure_type TEXT,
        metrics_json TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS decision_snapshot_summaries (
        summary_id TEXT PRIMARY KEY,
        decision_type TEXT,
        sample_count INTEGER,
        outcome_count INTEGER,
        success_count INTEGER,
        avg_reward REAL,
        avg_platform_sc_abs_max REAL,
        updated_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS sc_training_samples (
        sample_id TEXT PRIMARY KEY,
        alpha_id TEXT,
        expression TEXT,
        platform_sc_abs_max REAL,
        platform_sc_status TEXT,
        features_json TEXT,
        label_json TEXT,
        context_json TEXT,
        raw_payload TEXT,
        created_at TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS parent_selection_samples (
        sample_id TEXT PRIMARY KEY,
        parent_alpha_id TEXT,
        child_alpha_id TEXT,
        parent_features_json TEXT,
        child_metrics_json TEXT,
        child_reward REAL,
        reward_delta REAL,
        child_success INTEGER,
        child_platform_sc_abs_max REAL,
        mutation_type TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS policy_training_samples (
        sample_id TEXT PRIMARY KEY,
        decision_id TEXT,
        alpha_id TEXT,
        context_json TEXT,
        available_actions_json TEXT,
        chosen_action_json TEXT,
        reward_delta REAL,
        success INTEGER,
        failure_type TEXT,
        platform_sc_abs_max REAL,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS simulator_training_samples (
        sample_id TEXT PRIMARY KEY,
        alpha_id TEXT,
        features_json TEXT,
        prediction_json TEXT,
        backtest_success INTEGER,
        quality_passed INTEGER,
        reward REAL,
        fitness REAL,
        sharpe REAL,
        turnover REAL,
        failure_type TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS experiment_records (
        experiment_id TEXT PRIMARY KEY,
        experiment_type TEXT,
        base_alpha_id TEXT,
        controlled_variable TEXT,
        hypothesis TEXT,
        status TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS experiment_plans (
        experiment_id TEXT PRIMARY KEY,
        name TEXT,
        status TEXT,
        hypothesis_json TEXT,
        arms_json TEXT,
        created_at TEXT,
        updated_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS experiment_assignments (
        assignment_id TEXT PRIMARY KEY,
        experiment_id TEXT,
        arm_id TEXT,
        alpha_id TEXT,
        expression_hash TEXT,
        template_name TEXT,
        template_family TEXT,
        operator_family TEXT,
        mutation_type TEXT,
        field_family TEXT,
        behavior_family TEXT,
        assigned_by TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS experiment_results (
        result_id TEXT PRIMARY KEY,
        assignment_id TEXT,
        experiment_id TEXT,
        arm_id TEXT,
        alpha_id TEXT,
        success INTEGER,
        reward REAL,
        sharpe REAL,
        fitness REAL,
        returns REAL,
        turnover REAL,
        drawdown REAL,
        margin REAL,
        platform_sc_status TEXT,
        platform_sc_abs_max REAL,
        quality_passed INTEGER,
        failure_type TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS experiment_summaries (
        summary_id TEXT PRIMARY KEY,
        experiment_id TEXT,
        arm_id TEXT,
        sample_count INTEGER,
        success_count INTEGER,
        failure_count INTEGER,
        avg_reward REAL,
        avg_sharpe REAL,
        avg_fitness REAL,
        avg_platform_sc_abs_max REAL,
        quality_pass_rate REAL,
        updated_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS experiment_budget_plans (
        budget_plan_id TEXT PRIMARY KEY,
        experiment_id TEXT,
        status TEXT,
        total_budget_hint INTEGER,
        allocations_json TEXT,
        generated_by TEXT,
        created_at TEXT,
        updated_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS experiment_budget_allocations (
        allocation_id TEXT PRIMARY KEY,
        budget_plan_id TEXT,
        experiment_id TEXT,
        arm_id TEXT,
        suggested_ratio REAL,
        min_ratio REAL,
        max_ratio REAL,
        sample_count INTEGER,
        success_count INTEGER,
        failure_count INTEGER,
        avg_reward REAL,
        avg_platform_sc_abs_max REAL,
        quality_pass_rate REAL,
        reason_codes_json TEXT,
        governance_allowed INTEGER,
        status TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS experiment_budget_snapshots (
        snapshot_id TEXT PRIMARY KEY,
        budget_plan_id TEXT,
        experiment_id TEXT,
        total_budget_hint INTEGER,
        allocations_json TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS insight_usage (
        usage_id TEXT PRIMARY KEY,
        insight_id TEXT,
        alpha_id TEXT,
        prompt_context_json TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS insight_effect_samples (
        effect_id TEXT PRIMARY KEY,
        insight_id TEXT,
        alpha_id TEXT,
        reward REAL,
        fitness REAL,
        sharpe REAL,
        turnover REAL,
        platform_sc_abs_max REAL,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS drift_events (
        event_id TEXT PRIMARY KEY,
        drift_type TEXT,
        severity TEXT,
        metric_name TEXT,
        event_json TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_registry (
        strategy_id TEXT PRIMARY KEY,
        strategy_type TEXT,
        role TEXT,
        task_name TEXT,
        model_version TEXT,
        status TEXT,
        created_at TEXT,
        updated_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_performance (
        record_id TEXT PRIMARY KEY,
        strategy_id TEXT,
        window_name TEXT,
        sample_count INTEGER,
        avg_reward REAL,
        median_reward REAL,
        success_rate REAL,
        failure_rate REAL,
        avg_platform_sc_abs_max REAL,
        avg_turnover REAL,
        avg_fitness REAL,
        performance_json TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_allocations (
        allocation_id TEXT PRIMARY KEY,
        strategy_id TEXT,
        role TEXT,
        budget REAL,
        effective_from TEXT,
        effective_to TEXT,
        reason TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_decisions (
        decision_id TEXT PRIMARY KEY,
        strategy_id TEXT,
        alpha_id TEXT,
        decision_type TEXT,
        selected INTEGER,
        shadow INTEGER,
        score REAL,
        model_version TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_profiles (
        strategy_id TEXT PRIMARY KEY,
        strategy_type TEXT,
        name TEXT,
        description TEXT,
        source TEXT,
        enabled INTEGER,
        advisory_only INTEGER,
        created_at TEXT,
        updated_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_evidence (
        evidence_id TEXT PRIMARY KEY,
        strategy_id TEXT,
        evidence_type TEXT,
        sample_count INTEGER,
        success_count INTEGER,
        avg_reward REAL,
        success_rate REAL,
        avg_platform_sc_abs_max REAL,
        quality_pass_rate REAL,
        replay_confidence TEXT,
        counterfactual_confidence TEXT,
        governance_status TEXT,
        risk_flags_json TEXT,
        reason_codes_json TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_signals (
        signal_id TEXT PRIMARY KEY,
        strategy_id TEXT,
        signal_type TEXT,
        value_json TEXT,
        weight REAL,
        direction TEXT,
        reason TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_scores (
        strategy_id TEXT PRIMARY KEY,
        strategy_type TEXT,
        total_score REAL,
        reward_score REAL,
        success_score REAL,
        sc_risk_score REAL,
        quality_score REAL,
        replay_score REAL,
        counterfactual_score REAL,
        governance_score REAL,
        sample_size_score REAL,
        confidence TEXT,
        risk_level TEXT,
        recommendation TEXT,
        evidence_count INTEGER,
        sample_count INTEGER,
        updated_at TEXT,
        reason_codes_json TEXT,
        risk_flags_json TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_scoreboards (
        scoreboard_id TEXT PRIMARY KEY,
        generated_at TEXT,
        profiles_json TEXT,
        scores_json TEXT,
        signals_json TEXT,
        evidence_summary_json TEXT,
        warnings_json TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_portfolio_states (
        strategy_id TEXT PRIMARY KEY,
        strategy_type TEXT,
        current_state TEXT,
        recommended_state TEXT,
        current_role TEXT,
        confidence TEXT,
        risk_level TEXT,
        score REAL,
        sample_count INTEGER,
        evidence_count INTEGER,
        governance_status TEXT,
        reason_codes_json TEXT,
        risk_flags_json TEXT,
        updated_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_portfolio_transitions (
        transition_id TEXT PRIMARY KEY,
        strategy_id TEXT,
        from_state TEXT,
        to_state TEXT,
        recommendation TEXT,
        allowed INTEGER,
        auto_apply_allowed INTEGER,
        confidence TEXT,
        reason_codes_json TEXT,
        risk_flags_json TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_portfolios (
        portfolio_id TEXT PRIMARY KEY,
        generated_at TEXT,
        champion_strategy_id TEXT,
        states_json TEXT,
        transitions_json TEXT,
        warnings_json TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_portfolio_reports (
        report_id TEXT PRIMARY KEY,
        generated_at TEXT,
        mode TEXT,
        champion_strategy_id TEXT,
        strategy_states_json TEXT,
        recommended_transitions_json TEXT,
        warnings_json TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_budget_rules (
        rule_id TEXT PRIMARY KEY,
        rule_type TEXT,
        description TEXT,
        enabled INTEGER,
        priority INTEGER,
        min_ratio REAL,
        max_ratio REAL,
        applies_to_state TEXT,
        applies_to_strategy_type TEXT,
        reason_code TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_budget_allocations (
        allocation_id TEXT PRIMARY KEY,
        plan_id TEXT,
        strategy_id TEXT,
        strategy_type TEXT,
        state TEXT,
        role TEXT,
        score REAL,
        confidence TEXT,
        risk_level TEXT,
        requested_ratio REAL,
        suggested_ratio REAL,
        min_floor_ratio REAL,
        hard_cap_ratio REAL,
        suggested_slots INTEGER,
        budget_status TEXT,
        reason_codes_json TEXT,
        risk_flags_json TEXT,
        auto_apply_allowed INTEGER,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_budget_plans (
        plan_id TEXT PRIMARY KEY,
        generated_at TEXT,
        mode TEXT,
        total_budget_hint INTEGER,
        allocations_json TEXT,
        total_suggested_ratio REAL,
        warnings_json TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_budget_reports (
        report_id TEXT PRIMARY KEY,
        generated_at TEXT,
        mode TEXT,
        total_budget_hint INTEGER,
        allocations_json TEXT,
        warnings_json TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS observability_metrics (
        metric_id TEXT PRIMARY KEY,
        source TEXT,
        metric_name TEXT,
        metric_type TEXT,
        value_json TEXT,
        unit TEXT,
        timestamp TEXT,
        tags_json TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS observability_source_status (
        source TEXT PRIMARY KEY,
        available INTEGER,
        status_path TEXT,
        table_names_json TEXT,
        last_updated_at TEXT,
        is_stale INTEGER,
        metric_count INTEGER,
        warnings_json TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS observability_snapshots (
        snapshot_id TEXT PRIMARY KEY,
        generated_at TEXT,
        metrics_json TEXT,
        source_statuses_json TEXT,
        summary_json TEXT,
        warnings_json TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS observability_summaries (
        summary_id TEXT PRIMARY KEY,
        generated_at TEXT,
        total_metrics INTEGER,
        available_sources INTEGER,
        stale_sources INTEGER,
        warning_count INTEGER,
        workflow_summary_json TEXT,
        ml_summary_json TEXT,
        governance_summary_json TEXT,
        experiment_summary_json TEXT,
        offline_summary_json TEXT,
        strategy_summary_json TEXT,
        system_summary_json TEXT,
        warnings_json TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS observability_drift_rules (
        rule_id TEXT PRIMARY KEY,
        metric_name TEXT,
        source TEXT,
        rule_type TEXT,
        window_size INTEGER,
        baseline_window_size INTEGER,
        threshold REAL,
        direction TEXT,
        severity TEXT,
        enabled INTEGER,
        description TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS observability_drift_signals (
        signal_id TEXT PRIMARY KEY,
        rule_id TEXT,
        source TEXT,
        metric_name TEXT,
        current_value_json TEXT,
        baseline_value_json TEXT,
        delta REAL,
        delta_ratio REAL,
        threshold REAL,
        triggered INTEGER,
        severity TEXT,
        reason_codes_json TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS observability_alert_rules (
        rule_id TEXT PRIMARY KEY,
        alert_name TEXT,
        source TEXT,
        condition_type TEXT,
        metric_name TEXT,
        severity TEXT,
        enabled INTEGER,
        threshold REAL,
        description TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS observability_alert_events (
        alert_id TEXT PRIMARY KEY,
        rule_id TEXT,
        alert_name TEXT,
        source TEXT,
        severity TEXT,
        status TEXT,
        message TEXT,
        triggered INTEGER,
        created_at TEXT,
        metric_name TEXT,
        metric_value_json TEXT,
        reason_codes_json TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS observability_health_diagnoses (
        diagnosis_id TEXT PRIMARY KEY,
        area TEXT,
        status TEXT,
        severity TEXT,
        summary TEXT,
        evidence_metrics_json TEXT,
        alert_ids_json TEXT,
        drift_signal_ids_json TEXT,
        recommended_action TEXT,
        auto_action_allowed INTEGER,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS observability_health_reports (
        report_id TEXT PRIMARY KEY,
        generated_at TEXT,
        mode TEXT,
        overall_status TEXT,
        diagnoses_json TEXT,
        alert_events_json TEXT,
        drift_signals_json TEXT,
        summary_json TEXT,
        warnings_json TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS observability_explanation_evidence (
        evidence_id TEXT PRIMARY KEY,
        source TEXT,
        evidence_type TEXT,
        title TEXT,
        summary TEXT,
        confidence TEXT,
        observed INTEGER,
        estimated INTEGER,
        advisory INTEGER,
        timestamp TEXT,
        related_ids_json TEXT,
        reason_codes_json TEXT,
        risk_flags_json TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS observability_decision_traces (
        trace_id TEXT PRIMARY KEY,
        generated_at TEXT,
        decision_id TEXT,
        alpha_id TEXT,
        run_id TEXT,
        strategy_id TEXT,
        decision_type TEXT,
        decision_summary TEXT,
        selected_action TEXT,
        alternative_actions_json TEXT,
        evidence_json TEXT,
        explanation TEXT,
        confidence TEXT,
        warnings_json TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS observability_run_explanations (
        explanation_id TEXT PRIMARY KEY,
        generated_at TEXT,
        window_start TEXT,
        window_end TEXT,
        run_summary TEXT,
        key_findings_json TEXT,
        decision_traces_json TEXT,
        alerts_summary_json TEXT,
        diagnosis_summary_json TEXT,
        strategy_summary_json TEXT,
        budget_summary_json TEXT,
        evidence_summary_json TEXT,
        limitations_json TEXT,
        recommended_human_checks_json TEXT,
        auto_action_allowed INTEGER,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS observability_daily_reports (
        report_id TEXT PRIMARY KEY,
        generated_at TEXT,
        date TEXT,
        overall_summary TEXT,
        health_status TEXT,
        key_metrics_json TEXT,
        key_alerts_json TEXT,
        key_diagnoses_json TEXT,
        strategy_explanations_json TEXT,
        budget_explanations_json TEXT,
        offline_evidence_summary_json TEXT,
        counterfactual_limitations_json TEXT,
        recommended_human_checks_json TEXT,
        auto_action_allowed INTEGER,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS observability_stage_reports (
        report_id TEXT PRIMARY KEY,
        generated_at TEXT,
        stage_name TEXT,
        summary TEXT,
        completed_substages_json TEXT,
        generated_reports_json TEXT,
        key_capabilities_json TEXT,
        known_limitations_json TEXT,
        next_stage_recommendations_json TEXT,
        auto_action_allowed INTEGER,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS offline_replay_reports (
        report_id TEXT PRIMARY KEY,
        task_name TEXT,
        strategy_id TEXT,
        model_version TEXT,
        decision_type TEXT,
        sample_count INTEGER,
        support_coverage REAL,
        model_match_rate REAL,
        estimated_reward_delta REAL,
        estimated_risk_delta REAL,
        replay_pass INTEGER,
        report_json TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS offline_replay_runs (
        replay_run_id TEXT PRIMARY KEY,
        name TEXT,
        status TEXT,
        policies_json TEXT,
        dataset_filter_json TEXT,
        sample_count INTEGER,
        observable_count INTEGER,
        started_at TEXT,
        completed_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS offline_replay_policy_decisions (
        policy_decision_id TEXT PRIMARY KEY,
        replay_run_id TEXT,
        decision_id TEXT,
        policy_name TEXT,
        selected_action_json TEXT,
        selected_matches_actual INTEGER,
        selected_matches_legacy INTEGER,
        observable_outcome INTEGER,
        reward REAL,
        success INTEGER,
        platform_sc_abs_max REAL,
        quality_passed INTEGER,
        reason_codes_json TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS offline_replay_policy_metrics (
        metric_id TEXT PRIMARY KEY,
        replay_run_id TEXT,
        policy_name TEXT,
        decision_type TEXT,
        sample_count INTEGER,
        observable_count INTEGER,
        coverage_rate REAL,
        agreement_with_actual_rate REAL,
        agreement_with_legacy_rate REAL,
        avg_reward REAL,
        success_rate REAL,
        avg_platform_sc_abs_max REAL,
        quality_pass_rate REAL,
        insufficient_evidence_count INTEGER,
        reason_codes_json TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS offline_replay_comparisons (
        comparison_id TEXT PRIMARY KEY,
        replay_run_id TEXT,
        baseline_policy TEXT,
        challenger_policy TEXT,
        decision_type TEXT,
        baseline_metrics_json TEXT,
        challenger_metrics_json TEXT,
        reward_delta REAL,
        success_rate_delta REAL,
        sc_risk_delta REAL,
        quality_pass_delta REAL,
        confidence TEXT,
        verdict TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS counterfactual_requests (
        request_id TEXT PRIMARY KEY,
        replay_run_id TEXT,
        policy_decision_id TEXT,
        decision_id TEXT,
        decision_type TEXT,
        target_action_json TEXT,
        actual_action_json TEXT,
        alpha_id TEXT,
        experiment_id TEXT,
        arm_id TEXT,
        budget_plan_id TEXT,
        features_json TEXT,
        context_json TEXT,
        min_evidence INTEGER,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS counterfactual_evidence (
        evidence_id TEXT PRIMARY KEY,
        request_id TEXT,
        source_decision_id TEXT,
        source_alpha_id TEXT,
        action_id TEXT,
        action_type TEXT,
        similarity_score REAL,
        reward REAL,
        success INTEGER,
        platform_sc_abs_max REAL,
        quality_passed INTEGER,
        reason_codes_json TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS counterfactual_estimates (
        estimate_id TEXT PRIMARY KEY,
        request_id TEXT,
        decision_id TEXT,
        target_action_json TEXT,
        evidence_count INTEGER,
        effective_evidence_count INTEGER,
        estimated_reward REAL,
        estimated_success_rate REAL,
        estimated_platform_sc_abs_max REAL,
        estimated_quality_pass_rate REAL,
        confidence TEXT,
        verdict TEXT,
        risk_flags_json TEXT,
        reason_codes_json TEXT,
        estimated_not_observed INTEGER,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS counterfactual_summaries (
        summary_id TEXT PRIMARY KEY,
        decision_type TEXT,
        request_count INTEGER,
        estimate_count INTEGER,
        insufficient_count INTEGER,
        high_risk_count INTEGER,
        medium_or_high_confidence_count INTEGER,
        avg_evidence_count REAL,
        updated_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS policy_replay_evaluations (
        evaluation_id TEXT PRIMARY KEY,
        task_name TEXT,
        model_version TEXT,
        decision_type TEXT,
        sample_count INTEGER,
        support_coverage REAL,
        action_coverage REAL,
        avg_legacy_score REAL,
        avg_model_score REAL,
        estimated_reward_delta REAL,
        estimated_sc_risk_delta REAL,
        estimated_failure_delta REAL,
        evaluation_json TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS model_safety_reports (
        report_id TEXT PRIMARY KEY,
        task_name TEXT,
        model_version TEXT,
        strategy_id TEXT,
        validation_pass INTEGER,
        replay_pass INTEGER,
        support_pass INTEGER,
        promotion_pass INTEGER,
        safety_status TEXT,
        reason TEXT,
        report_json TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
)

REFRACTOR_INDEX_DDL: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_ml_training_samples_task ON ml_training_samples(task_name, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_sc_training_samples_alpha ON sc_training_samples(alpha_id, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_decision_snapshots_type ON decision_snapshots(decision_type, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_decision_snapshots_alpha_id ON decision_snapshots(alpha_id);",
    "CREATE INDEX IF NOT EXISTS idx_decision_snapshots_experiment_id ON decision_snapshots(experiment_id);",
    "CREATE INDEX IF NOT EXISTS idx_decision_snapshots_budget_plan_id ON decision_snapshots(budget_plan_id);",
    "CREATE INDEX IF NOT EXISTS idx_decision_outcomes_decision ON decision_outcomes(decision_id, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_decision_outcomes_decision_id ON decision_outcomes(decision_id);",
    "CREATE INDEX IF NOT EXISTS idx_decision_outcomes_alpha_id ON decision_outcomes(alpha_id);",
    "CREATE INDEX IF NOT EXISTS idx_decision_snapshot_summaries_type ON decision_snapshot_summaries(decision_type);",
    "CREATE INDEX IF NOT EXISTS idx_prediction_audit_task ON ml_prediction_audit(task_name, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_parent_selection_child ON parent_selection_samples(child_alpha_id, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_policy_samples_decision ON policy_training_samples(decision_id, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_simulator_samples_alpha ON simulator_training_samples(alpha_id, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_drift_events_created ON drift_events(created_at);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_registry_role ON strategy_registry(role, status, task_name);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_allocations_strategy ON strategy_allocations(strategy_id, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_decisions_strategy ON strategy_decisions(strategy_id, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_profiles_type ON strategy_profiles(strategy_type);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_profiles_source ON strategy_profiles(source);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_evidence_strategy_id ON strategy_evidence(strategy_id);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_evidence_type ON strategy_evidence(evidence_type);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_signals_strategy_id ON strategy_signals(strategy_id);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_signals_type ON strategy_signals(signal_type);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_scores_type ON strategy_scores(strategy_type);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_scores_recommendation ON strategy_scores(recommendation);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_scoreboards_generated_at ON strategy_scoreboards(generated_at);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_portfolio_states_state ON strategy_portfolio_states(current_state, recommended_state);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_portfolio_states_type ON strategy_portfolio_states(strategy_type);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_portfolio_transitions_strategy_id ON strategy_portfolio_transitions(strategy_id);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_portfolio_transitions_recommendation ON strategy_portfolio_transitions(recommendation);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_portfolios_generated_at ON strategy_portfolios(generated_at);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_portfolio_reports_generated_at ON strategy_portfolio_reports(generated_at);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_budget_rules_type ON strategy_budget_rules(rule_type);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_budget_rules_state ON strategy_budget_rules(applies_to_state);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_budget_allocations_plan_id ON strategy_budget_allocations(plan_id);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_budget_allocations_strategy_id ON strategy_budget_allocations(strategy_id);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_budget_allocations_status ON strategy_budget_allocations(budget_status);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_budget_plans_generated_at ON strategy_budget_plans(generated_at);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_budget_reports_generated_at ON strategy_budget_reports(generated_at);",
    "CREATE INDEX IF NOT EXISTS idx_observability_metrics_source ON observability_metrics(source);",
    "CREATE INDEX IF NOT EXISTS idx_observability_metrics_name ON observability_metrics(metric_name);",
    "CREATE INDEX IF NOT EXISTS idx_observability_metrics_timestamp ON observability_metrics(timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_observability_snapshots_generated_at ON observability_snapshots(generated_at);",
    "CREATE INDEX IF NOT EXISTS idx_observability_summaries_generated_at ON observability_summaries(generated_at);",
    "CREATE INDEX IF NOT EXISTS idx_observability_drift_rules_metric ON observability_drift_rules(metric_name);",
    "CREATE INDEX IF NOT EXISTS idx_observability_drift_signals_metric ON observability_drift_signals(metric_name);",
    "CREATE INDEX IF NOT EXISTS idx_observability_drift_signals_created_at ON observability_drift_signals(created_at);",
    "CREATE INDEX IF NOT EXISTS idx_observability_alert_events_source ON observability_alert_events(source);",
    "CREATE INDEX IF NOT EXISTS idx_observability_alert_events_severity ON observability_alert_events(severity);",
    "CREATE INDEX IF NOT EXISTS idx_observability_alert_events_created_at ON observability_alert_events(created_at);",
    "CREATE INDEX IF NOT EXISTS idx_observability_health_diagnoses_area ON observability_health_diagnoses(area);",
    "CREATE INDEX IF NOT EXISTS idx_observability_health_reports_generated_at ON observability_health_reports(generated_at);",
    "CREATE INDEX IF NOT EXISTS idx_observability_explanation_source ON observability_explanation_evidence(source);",
    "CREATE INDEX IF NOT EXISTS idx_observability_explanation_type ON observability_explanation_evidence(evidence_type);",
    "CREATE INDEX IF NOT EXISTS idx_observability_explanation_timestamp ON observability_explanation_evidence(timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_observability_decision_traces_generated_at ON observability_decision_traces(generated_at);",
    "CREATE INDEX IF NOT EXISTS idx_observability_decision_traces_decision_type ON observability_decision_traces(decision_type);",
    "CREATE INDEX IF NOT EXISTS idx_observability_run_explanations_generated_at ON observability_run_explanations(generated_at);",
    "CREATE INDEX IF NOT EXISTS idx_observability_daily_reports_date ON observability_daily_reports(date);",
    "CREATE INDEX IF NOT EXISTS idx_observability_stage_reports_generated_at ON observability_stage_reports(generated_at);",
    "CREATE INDEX IF NOT EXISTS idx_offline_replay_reports_task ON offline_replay_reports(task_name, decision_type, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_offline_replay_runs_status ON offline_replay_runs(status);",
    "CREATE INDEX IF NOT EXISTS idx_offline_replay_policy_decisions_run_id ON offline_replay_policy_decisions(replay_run_id);",
    "CREATE INDEX IF NOT EXISTS idx_offline_replay_policy_decisions_decision_id ON offline_replay_policy_decisions(decision_id);",
    "CREATE INDEX IF NOT EXISTS idx_offline_replay_policy_metrics_run_id ON offline_replay_policy_metrics(replay_run_id);",
    "CREATE INDEX IF NOT EXISTS idx_offline_replay_policy_metrics_policy ON offline_replay_policy_metrics(policy_name, decision_type);",
    "CREATE INDEX IF NOT EXISTS idx_offline_replay_comparisons_run_id ON offline_replay_comparisons(replay_run_id);",
    "CREATE INDEX IF NOT EXISTS idx_offline_replay_comparisons_policies ON offline_replay_comparisons(baseline_policy, challenger_policy);",
    "CREATE INDEX IF NOT EXISTS idx_counterfactual_requests_decision_id ON counterfactual_requests(decision_id);",
    "CREATE INDEX IF NOT EXISTS idx_counterfactual_requests_replay_run_id ON counterfactual_requests(replay_run_id);",
    "CREATE INDEX IF NOT EXISTS idx_counterfactual_requests_policy_decision_id ON counterfactual_requests(policy_decision_id);",
    "CREATE INDEX IF NOT EXISTS idx_counterfactual_evidence_request_id ON counterfactual_evidence(request_id);",
    "CREATE INDEX IF NOT EXISTS idx_counterfactual_evidence_source_decision_id ON counterfactual_evidence(source_decision_id);",
    "CREATE INDEX IF NOT EXISTS idx_counterfactual_estimates_request_id ON counterfactual_estimates(request_id);",
    "CREATE INDEX IF NOT EXISTS idx_counterfactual_estimates_decision_id ON counterfactual_estimates(decision_id);",
    "CREATE INDEX IF NOT EXISTS idx_counterfactual_estimates_verdict ON counterfactual_estimates(verdict);",
    "CREATE INDEX IF NOT EXISTS idx_counterfactual_summaries_type ON counterfactual_summaries(decision_type);",
    "CREATE INDEX IF NOT EXISTS idx_model_safety_reports_strategy ON model_safety_reports(strategy_id, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_experiment_assignments_alpha_id ON experiment_assignments(alpha_id);",
    "CREATE INDEX IF NOT EXISTS idx_experiment_assignments_experiment_id ON experiment_assignments(experiment_id);",
    "CREATE INDEX IF NOT EXISTS idx_experiment_results_experiment_id ON experiment_results(experiment_id);",
    "CREATE INDEX IF NOT EXISTS idx_experiment_results_arm_id ON experiment_results(arm_id);",
    "CREATE INDEX IF NOT EXISTS idx_experiment_budget_plans_experiment_id ON experiment_budget_plans(experiment_id);",
    "CREATE INDEX IF NOT EXISTS idx_experiment_budget_allocations_plan_id ON experiment_budget_allocations(budget_plan_id);",
    "CREATE INDEX IF NOT EXISTS idx_experiment_budget_allocations_experiment_id ON experiment_budget_allocations(experiment_id);",
    "CREATE INDEX IF NOT EXISTS idx_experiment_budget_allocations_arm_id ON experiment_budget_allocations(arm_id);",
    "CREATE INDEX IF NOT EXISTS idx_experiment_budget_snapshots_experiment_id ON experiment_budget_snapshots(experiment_id);",
)

COMPAT_COLUMNS: dict[str, dict[str, str]] = {
    "decision_snapshots": {
        "decision_id": "TEXT",
        "decision_type": "TEXT",
        "workflow_run_id": "TEXT",
        "iteration": "INTEGER",
        "alpha_id": "TEXT",
        "experiment_id": "TEXT",
        "arm_id": "TEXT",
        "budget_plan_id": "TEXT",
        "available_actions_json": "TEXT",
        "chosen_action_json": "TEXT",
        "legacy_choice_json": "TEXT",
        "model_choice_json": "TEXT",
        "experiment_choice_json": "TEXT",
        "governance_decision": "TEXT",
        "features_json": "TEXT",
        "scores_json": "TEXT",
        "context_json": "TEXT",
        "actual_result_json": "TEXT",
        "reward": "REAL",
        "platform_sc_status": "TEXT",
        "platform_sc_abs_max": "REAL",
        "success": "INTEGER",
        "quality_passed": "INTEGER",
        "created_at": "TEXT",
        "updated_at": "TEXT",
        "raw_payload": "TEXT",
        "action_scores_json": "TEXT",
        "selection_reason": "TEXT",
        "legacy_score": "REAL",
        "model_score": "REAL",
        "propensity": "REAL",
        "model_version": "TEXT",
    },
    "decision_outcomes": {
        "outcome_id": "TEXT",
        "decision_id": "TEXT",
        "decision_type": "TEXT",
        "alpha_id": "TEXT",
        "success": "INTEGER",
        "reward": "REAL",
        "reward_delta": "REAL",
        "sharpe": "REAL",
        "fitness": "REAL",
        "returns": "REAL",
        "turnover": "REAL",
        "drawdown": "REAL",
        "margin": "REAL",
        "platform_sc_status": "TEXT",
        "platform_sc_abs_max": "REAL",
        "quality_passed": "INTEGER",
        "failure_type": "TEXT",
        "metrics_json": "TEXT",
        "created_at": "TEXT",
        "raw_payload": "TEXT",
    },
    "decision_snapshot_summaries": {
        "summary_id": "TEXT",
        "decision_type": "TEXT",
        "sample_count": "INTEGER",
        "outcome_count": "INTEGER",
        "success_count": "INTEGER",
        "avg_reward": "REAL",
        "avg_platform_sc_abs_max": "REAL",
        "updated_at": "TEXT",
        "raw_payload": "TEXT",
    },
    "insight_usage": {
        "usage_id": "TEXT",
        "insight_id": "TEXT",
        "alpha_id": "TEXT",
        "prompt_context_json": "TEXT",
        "created_at": "TEXT",
        "raw_payload": "TEXT",
    },
    "insight_effect_samples": {
        "effect_id": "TEXT",
        "insight_id": "TEXT",
        "alpha_id": "TEXT",
        "reward": "REAL",
        "fitness": "REAL",
        "sharpe": "REAL",
        "turnover": "REAL",
        "platform_sc_abs_max": "REAL",
        "created_at": "TEXT",
        "raw_payload": "TEXT",
    },
    "drift_events": {
        "event_id": "TEXT",
        "drift_type": "TEXT",
        "severity": "TEXT",
        "metric_name": "TEXT",
        "event_json": "TEXT",
        "created_at": "TEXT",
        "raw_payload": "TEXT",
    },
    "strategy_registry": {
        "strategy_id": "TEXT",
        "strategy_type": "TEXT",
        "role": "TEXT",
        "task_name": "TEXT",
        "model_version": "TEXT",
        "status": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT",
        "raw_payload": "TEXT",
    },
    "strategy_budget_rules": {
        "rule_id": "TEXT",
        "rule_type": "TEXT",
        "description": "TEXT",
        "enabled": "INTEGER",
        "priority": "INTEGER",
        "min_ratio": "REAL",
        "max_ratio": "REAL",
        "applies_to_state": "TEXT",
        "applies_to_strategy_type": "TEXT",
        "reason_code": "TEXT",
        "created_at": "TEXT",
        "raw_payload": "TEXT",
    },
    "strategy_budget_allocations": {
        "allocation_id": "TEXT",
        "plan_id": "TEXT",
        "strategy_id": "TEXT",
        "strategy_type": "TEXT",
        "state": "TEXT",
        "role": "TEXT",
        "score": "REAL",
        "confidence": "TEXT",
        "risk_level": "TEXT",
        "requested_ratio": "REAL",
        "suggested_ratio": "REAL",
        "min_floor_ratio": "REAL",
        "hard_cap_ratio": "REAL",
        "suggested_slots": "INTEGER",
        "budget_status": "TEXT",
        "reason_codes_json": "TEXT",
        "risk_flags_json": "TEXT",
        "auto_apply_allowed": "INTEGER",
        "created_at": "TEXT",
        "raw_payload": "TEXT",
    },
    "strategy_budget_plans": {
        "plan_id": "TEXT",
        "generated_at": "TEXT",
        "mode": "TEXT",
        "total_budget_hint": "INTEGER",
        "allocations_json": "TEXT",
        "total_suggested_ratio": "REAL",
        "warnings_json": "TEXT",
        "raw_payload": "TEXT",
    },
    "strategy_budget_reports": {
        "report_id": "TEXT",
        "generated_at": "TEXT",
        "mode": "TEXT",
        "total_budget_hint": "INTEGER",
        "allocations_json": "TEXT",
        "warnings_json": "TEXT",
        "raw_payload": "TEXT",
    },
    "observability_metrics": {
        "metric_id": "TEXT",
        "source": "TEXT",
        "metric_name": "TEXT",
        "metric_type": "TEXT",
        "value_json": "TEXT",
        "unit": "TEXT",
        "timestamp": "TEXT",
        "tags_json": "TEXT",
        "raw_payload": "TEXT",
    },
    "observability_source_status": {
        "source": "TEXT",
        "available": "INTEGER",
        "status_path": "TEXT",
        "table_names_json": "TEXT",
        "last_updated_at": "TEXT",
        "is_stale": "INTEGER",
        "metric_count": "INTEGER",
        "warnings_json": "TEXT",
        "raw_payload": "TEXT",
    },
    "observability_snapshots": {
        "snapshot_id": "TEXT",
        "generated_at": "TEXT",
        "metrics_json": "TEXT",
        "source_statuses_json": "TEXT",
        "summary_json": "TEXT",
        "warnings_json": "TEXT",
        "raw_payload": "TEXT",
    },
    "observability_summaries": {
        "summary_id": "TEXT",
        "generated_at": "TEXT",
        "total_metrics": "INTEGER",
        "available_sources": "INTEGER",
        "stale_sources": "INTEGER",
        "warning_count": "INTEGER",
        "workflow_summary_json": "TEXT",
        "ml_summary_json": "TEXT",
        "governance_summary_json": "TEXT",
        "experiment_summary_json": "TEXT",
        "offline_summary_json": "TEXT",
        "strategy_summary_json": "TEXT",
        "system_summary_json": "TEXT",
        "warnings_json": "TEXT",
        "raw_payload": "TEXT",
    },
    "observability_drift_rules": {
        "rule_id": "TEXT",
        "metric_name": "TEXT",
        "source": "TEXT",
        "rule_type": "TEXT",
        "window_size": "INTEGER",
        "baseline_window_size": "INTEGER",
        "threshold": "REAL",
        "direction": "TEXT",
        "severity": "TEXT",
        "enabled": "INTEGER",
        "description": "TEXT",
        "created_at": "TEXT",
        "raw_payload": "TEXT",
    },
    "observability_drift_signals": {
        "signal_id": "TEXT",
        "rule_id": "TEXT",
        "source": "TEXT",
        "metric_name": "TEXT",
        "current_value_json": "TEXT",
        "baseline_value_json": "TEXT",
        "delta": "REAL",
        "delta_ratio": "REAL",
        "threshold": "REAL",
        "triggered": "INTEGER",
        "severity": "TEXT",
        "reason_codes_json": "TEXT",
        "created_at": "TEXT",
        "raw_payload": "TEXT",
    },
    "observability_alert_rules": {
        "rule_id": "TEXT",
        "alert_name": "TEXT",
        "source": "TEXT",
        "condition_type": "TEXT",
        "metric_name": "TEXT",
        "severity": "TEXT",
        "enabled": "INTEGER",
        "threshold": "REAL",
        "description": "TEXT",
        "created_at": "TEXT",
        "raw_payload": "TEXT",
    },
    "observability_alert_events": {
        "alert_id": "TEXT",
        "rule_id": "TEXT",
        "alert_name": "TEXT",
        "source": "TEXT",
        "severity": "TEXT",
        "status": "TEXT",
        "message": "TEXT",
        "triggered": "INTEGER",
        "created_at": "TEXT",
        "metric_name": "TEXT",
        "metric_value_json": "TEXT",
        "reason_codes_json": "TEXT",
        "raw_payload": "TEXT",
    },
    "observability_health_diagnoses": {
        "diagnosis_id": "TEXT",
        "area": "TEXT",
        "status": "TEXT",
        "severity": "TEXT",
        "summary": "TEXT",
        "evidence_metrics_json": "TEXT",
        "alert_ids_json": "TEXT",
        "drift_signal_ids_json": "TEXT",
        "recommended_action": "TEXT",
        "auto_action_allowed": "INTEGER",
        "created_at": "TEXT",
        "raw_payload": "TEXT",
    },
    "observability_health_reports": {
        "report_id": "TEXT",
        "generated_at": "TEXT",
        "mode": "TEXT",
        "overall_status": "TEXT",
        "diagnoses_json": "TEXT",
        "alert_events_json": "TEXT",
        "drift_signals_json": "TEXT",
        "summary_json": "TEXT",
        "warnings_json": "TEXT",
        "raw_payload": "TEXT",
    },
    "observability_explanation_evidence": {
        "evidence_id": "TEXT",
        "source": "TEXT",
        "evidence_type": "TEXT",
        "title": "TEXT",
        "summary": "TEXT",
        "confidence": "TEXT",
        "observed": "INTEGER",
        "estimated": "INTEGER",
        "advisory": "INTEGER",
        "timestamp": "TEXT",
        "related_ids_json": "TEXT",
        "reason_codes_json": "TEXT",
        "risk_flags_json": "TEXT",
        "raw_payload": "TEXT",
    },
    "observability_decision_traces": {
        "trace_id": "TEXT",
        "generated_at": "TEXT",
        "decision_id": "TEXT",
        "alpha_id": "TEXT",
        "run_id": "TEXT",
        "strategy_id": "TEXT",
        "decision_type": "TEXT",
        "decision_summary": "TEXT",
        "selected_action": "TEXT",
        "alternative_actions_json": "TEXT",
        "evidence_json": "TEXT",
        "explanation": "TEXT",
        "confidence": "TEXT",
        "warnings_json": "TEXT",
        "raw_payload": "TEXT",
    },
    "observability_run_explanations": {
        "explanation_id": "TEXT",
        "generated_at": "TEXT",
        "window_start": "TEXT",
        "window_end": "TEXT",
        "run_summary": "TEXT",
        "key_findings_json": "TEXT",
        "decision_traces_json": "TEXT",
        "alerts_summary_json": "TEXT",
        "diagnosis_summary_json": "TEXT",
        "strategy_summary_json": "TEXT",
        "budget_summary_json": "TEXT",
        "evidence_summary_json": "TEXT",
        "limitations_json": "TEXT",
        "recommended_human_checks_json": "TEXT",
        "auto_action_allowed": "INTEGER",
        "raw_payload": "TEXT",
    },
    "observability_daily_reports": {
        "report_id": "TEXT",
        "generated_at": "TEXT",
        "date": "TEXT",
        "overall_summary": "TEXT",
        "health_status": "TEXT",
        "key_metrics_json": "TEXT",
        "key_alerts_json": "TEXT",
        "key_diagnoses_json": "TEXT",
        "strategy_explanations_json": "TEXT",
        "budget_explanations_json": "TEXT",
        "offline_evidence_summary_json": "TEXT",
        "counterfactual_limitations_json": "TEXT",
        "recommended_human_checks_json": "TEXT",
        "auto_action_allowed": "INTEGER",
        "raw_payload": "TEXT",
    },
    "observability_stage_reports": {
        "report_id": "TEXT",
        "generated_at": "TEXT",
        "stage_name": "TEXT",
        "summary": "TEXT",
        "completed_substages_json": "TEXT",
        "generated_reports_json": "TEXT",
        "key_capabilities_json": "TEXT",
        "known_limitations_json": "TEXT",
        "next_stage_recommendations_json": "TEXT",
        "auto_action_allowed": "INTEGER",
        "raw_payload": "TEXT",
    },
    "offline_replay_reports": {
        "report_id": "TEXT",
        "task_name": "TEXT",
        "strategy_id": "TEXT",
        "model_version": "TEXT",
        "decision_type": "TEXT",
        "sample_count": "INTEGER",
        "support_coverage": "REAL",
        "model_match_rate": "REAL",
        "estimated_reward_delta": "REAL",
        "estimated_risk_delta": "REAL",
        "replay_pass": "INTEGER",
        "report_json": "TEXT",
        "created_at": "TEXT",
        "raw_payload": "TEXT",
    },
    "counterfactual_requests": {
        "request_id": "TEXT",
        "replay_run_id": "TEXT",
        "policy_decision_id": "TEXT",
        "decision_id": "TEXT",
        "decision_type": "TEXT",
        "target_action_json": "TEXT",
        "actual_action_json": "TEXT",
        "alpha_id": "TEXT",
        "experiment_id": "TEXT",
        "arm_id": "TEXT",
        "budget_plan_id": "TEXT",
        "features_json": "TEXT",
        "context_json": "TEXT",
        "min_evidence": "INTEGER",
        "created_at": "TEXT",
        "raw_payload": "TEXT",
    },
    "counterfactual_evidence": {
        "evidence_id": "TEXT",
        "request_id": "TEXT",
        "source_decision_id": "TEXT",
        "source_alpha_id": "TEXT",
        "action_id": "TEXT",
        "action_type": "TEXT",
        "similarity_score": "REAL",
        "reward": "REAL",
        "success": "INTEGER",
        "platform_sc_abs_max": "REAL",
        "quality_passed": "INTEGER",
        "reason_codes_json": "TEXT",
        "raw_payload": "TEXT",
    },
    "counterfactual_estimates": {
        "estimate_id": "TEXT",
        "request_id": "TEXT",
        "decision_id": "TEXT",
        "target_action_json": "TEXT",
        "evidence_count": "INTEGER",
        "effective_evidence_count": "INTEGER",
        "estimated_reward": "REAL",
        "estimated_success_rate": "REAL",
        "estimated_platform_sc_abs_max": "REAL",
        "estimated_quality_pass_rate": "REAL",
        "confidence": "TEXT",
        "verdict": "TEXT",
        "risk_flags_json": "TEXT",
        "reason_codes_json": "TEXT",
        "estimated_not_observed": "INTEGER",
        "created_at": "TEXT",
        "raw_payload": "TEXT",
    },
    "counterfactual_summaries": {
        "summary_id": "TEXT",
        "decision_type": "TEXT",
        "request_count": "INTEGER",
        "estimate_count": "INTEGER",
        "insufficient_count": "INTEGER",
        "high_risk_count": "INTEGER",
        "medium_or_high_confidence_count": "INTEGER",
        "avg_evidence_count": "REAL",
        "updated_at": "TEXT",
        "raw_payload": "TEXT",
    },
}


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def get_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not table_exists(conn, table):
        return set()
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if not table_exists(conn, table):
        return
    if column not in get_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def initialize_refactor_tables(conn: sqlite3.Connection) -> None:
    try:
        for statement in REFRACTOR_TABLE_DDL:
            conn.execute(statement)
        for table, columns in COMPAT_COLUMNS.items():
            for column, definition in columns.items():
                ensure_column(conn, table, column, definition)
        for statement in REFRACTOR_INDEX_DDL:
            conn.execute(statement)
    except Exception as exc:
        raise RuntimeError(f"initialize_refactor_tables failed: {exc}") from exc
