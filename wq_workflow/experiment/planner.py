from __future__ import annotations

import hashlib
import re
from typing import Any

from .schema import ExperimentArm, ExperimentHypothesis, ExperimentPlan, utc_now_iso


DEFAULT_EXPERIMENT_ID = "default_experiment_v1"
CONTROL_ARM_ID = "legacy_baseline"
DEFAULT_TREATMENT_ARM_ID = "default_treatment"


def context_to_dict(candidate_context: Any) -> dict[str, Any]:
    if isinstance(candidate_context, dict):
        return dict(candidate_context)
    if candidate_context is None:
        return {}
    if hasattr(candidate_context, "to_dict"):
        try:
            value = candidate_context.to_dict()
            if isinstance(value, dict):
                return dict(value)
        except Exception:
            pass
    data = getattr(candidate_context, "__dict__", {})
    return dict(data) if isinstance(data, dict) else {}


def stable_slug(value: Any, default: str = "unknown") -> str:
    text = str(value or default).strip().lower()
    text = re.sub(r"[^a-z0-9_\-:.]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_-")
    return text[:96] or default


def expression_hash(expression: Any) -> str | None:
    text = str(expression or "").strip()
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:32]


class ExperimentPlanner:
    """Compatibility wrapper from earlier phases.

    Earlier code imported ExperimentPlanner from this module and expected plan() to
    return None when active experiment design is disabled. Keep that behavior.
    """

    def __init__(self, *, config: Any | None = None) -> None:
        self.config = config

    def plan(self, parent: dict[str, Any] | None = None, alpha_repr: Any | None = None, strategy: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if not getattr(self.config, "enable_experiment_design", False):
            return None
        return {
            "experiment_type": "parameter_sweep",
            "base_alpha_id": (parent or {}).get("alpha_id", ""),
            "controlled_variable": "window",
            "variants": [],
            "hypothesis": "first-stage metadata only; candidate generation unchanged",
            "strategy_id": (strategy or {}).get("strategy_id", "legacy_champion"),
        }


class DefaultExperimentPlanner:
    def __init__(self, *, config: Any | None = None) -> None:
        self.config = config

    @property
    def default_experiment_id(self) -> str:
        return str(getattr(self.config, "default_experiment_id", DEFAULT_EXPERIMENT_ID) or DEFAULT_EXPERIMENT_ID)

    def build_default_plan(self) -> ExperimentPlan:
        experiment_id = self.default_experiment_id
        now = utc_now_iso()
        hypothesis = ExperimentHypothesis(
            hypothesis_id=f"{experiment_id}:hypothesis",
            name="Default experiment tracking baseline",
            description="Phase 4A tracking-only default experiment; no dynamic budget allocation.",
            variable_type="legacy_baseline",
            variable_value="tracking_only",
            expected_effect="Collect clean assignment/result data for later planning.",
            created_at=now,
            raw_payload={"phase": "4A", "tracking_only": True},
        )
        arms = [
            ExperimentArm(
                arm_id=CONTROL_ARM_ID,
                experiment_id=experiment_id,
                name="Legacy baseline control",
                role="control",
                variable_type="legacy_baseline",
                variable_value="legacy_baseline",
                allocation_hint=0.0,
                is_control=True,
                raw_payload={"tracking_only": True},
            ),
            ExperimentArm(
                arm_id=DEFAULT_TREATMENT_ARM_ID,
                experiment_id=experiment_id,
                name="Default treatment",
                role="treatment",
                variable_type="other",
                variable_value="default_treatment",
                allocation_hint=0.0,
                is_control=False,
                raw_payload={"tracking_only": True},
            ),
        ]
        return ExperimentPlan(
            experiment_id=experiment_id,
            name="Default Experiment Tracking v1",
            status="active",
            hypothesis=hypothesis,
            arms=arms,
            created_at=now,
            updated_at=now,
            raw_payload={"assignment_mode": "tracking_only"},
        )

    def infer_variable_tags(self, candidate_context: Any) -> dict[str, Any]:
        data = context_to_dict(candidate_context)
        expression = data.get("expression") or data.get("code")
        return {
            "alpha_id": data.get("alpha_id"),
            "expression_hash": data.get("expression_hash") or expression_hash(expression),
            "template_name": data.get("template_name") or data.get("template_file") or data.get("template_path"),
            "template_family": data.get("template_family") or data.get("template_name") or data.get("template_file"),
            "operator_family": data.get("operator_family"),
            "mutation_type": data.get("mutation_type") or data.get("candidate_source"),
            "field_family": data.get("field_family"),
            "behavior_family": data.get("behavior_family"),
        }

    def infer_arm(self, candidate_context: Any) -> ExperimentArm:
        data = context_to_dict(candidate_context)
        tags = self.infer_variable_tags(data)
        experiment_id = str(data.get("experiment_id") or self.default_experiment_id)
        source = str(data.get("candidate_source") or data.get("source") or "").lower()
        if data.get("is_legacy_baseline") or source in {"legacy", "legacy_baseline", "control"}:
            return ExperimentArm(
                arm_id=CONTROL_ARM_ID,
                experiment_id=experiment_id,
                name="Legacy baseline control",
                role="control",
                variable_type="legacy_baseline",
                variable_value="legacy_baseline",
                allocation_hint=0.0,
                is_control=True,
            )
        for variable_type in ("template_family", "operator_family", "mutation_type", "field_family", "behavior_family"):
            value = tags.get(variable_type)
            if value:
                slug = stable_slug(value)
                return ExperimentArm(
                    arm_id=f"{variable_type}:{slug}",
                    experiment_id=experiment_id,
                    name=f"{variable_type}={slug}",
                    role="treatment",
                    variable_type=variable_type,
                    variable_value=str(value),
                    allocation_hint=0.0,
                    is_control=False,
                    raw_payload={"tracking_only": True},
                )
        return ExperimentArm(
            arm_id=DEFAULT_TREATMENT_ARM_ID,
            experiment_id=experiment_id,
            name="Default treatment",
            role="treatment",
            variable_type="other",
            variable_value="default_treatment",
            allocation_hint=0.0,
            is_control=False,
            raw_payload={"tracking_only": True},
        )
