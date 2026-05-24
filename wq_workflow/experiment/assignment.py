from __future__ import annotations

import hashlib
from typing import Any

from .planner import context_to_dict, expression_hash
from .schema import ExperimentAssignment


def build_assignment_id(experiment_id: str, arm_id: str, candidate_context: Any) -> str:
    data = context_to_dict(candidate_context)
    identity = str(data.get("alpha_id") or data.get("expression_hash") or expression_hash(data.get("expression") or data.get("code")) or "unknown")
    digest = hashlib.sha256(f"{experiment_id}|{arm_id}|{identity}".encode("utf-8", errors="replace")).hexdigest()[:24]
    return f"assignment:{digest}"


def make_assignment(experiment_id: str, arm_id: str, candidate_context: Any, *, assigned_by: str = "default_planner") -> ExperimentAssignment:
    data = context_to_dict(candidate_context)
    expression = data.get("expression") or data.get("code")
    return ExperimentAssignment(
        assignment_id=str(data.get("assignment_id") or build_assignment_id(experiment_id, arm_id, data)),
        experiment_id=experiment_id,
        arm_id=arm_id,
        alpha_id=_text_or_none(data.get("alpha_id")),
        expression_hash=_text_or_none(data.get("expression_hash") or expression_hash(expression)),
        template_name=_text_or_none(data.get("template_name") or data.get("template_file") or data.get("template_path")),
        template_family=_text_or_none(data.get("template_family") or data.get("template_name") or data.get("template_file")),
        operator_family=_text_or_none(data.get("operator_family")),
        mutation_type=_text_or_none(data.get("mutation_type") or data.get("candidate_source")),
        field_family=_text_or_none(data.get("field_family")),
        behavior_family=_text_or_none(data.get("behavior_family")),
        assigned_by=assigned_by,
        raw_payload=data,
    )


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None
