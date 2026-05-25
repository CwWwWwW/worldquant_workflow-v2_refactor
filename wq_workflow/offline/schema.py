from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from wq_workflow.data.json_utils import safe_float, safe_int, to_jsonable


ACTION_SOURCES = {"legacy", "ml", "model", "experiment", "governance", "budget", "random", "manual", "actual", "unknown"}
DECISION_TYPES = {
    "parent_selection",
    "mutation_policy",
    "sc_fallback",
    "simulator_skip",
    "experiment_arm_selection",
    "budget_plan_selection",
    "candidate_acceptance",
    "quality_gate",
    "governance_gate",
    "unknown",
}


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _clean_dict(value: Any) -> dict[str, Any]:
    cleaned = to_jsonable(value if isinstance(value, dict) else {})
    return cleaned if isinstance(cleaned, dict) else {}


def _clean_list(value: Any) -> list[Any]:
    cleaned = to_jsonable(value if isinstance(value, list) else [])
    return cleaned if isinstance(cleaned, list) else []


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _nullable_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _nullable_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "pass", "passed", "success"}:
        return True
    if text in {"0", "false", "no", "n", "off", "fail", "failed", "failure"}:
        return False
    return None


def _nullable_float(value: Any) -> float | None:
    return safe_float(value, None)


def _nullable_int(value: Any) -> int | None:
    return safe_int(value, None)


@dataclass
class DecisionAction:
    action_id: str = ""
    action_type: str = "unknown"
    name: str = ""
    source: str = "unknown"
    score: float | None = None
    rank: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source"] = self.source if self.source in ACTION_SOURCES else "unknown"
        data["name"] = self.name or self.action_id
        data["score"] = _nullable_float(self.score)
        data["rank"] = _nullable_int(self.rank)
        data["metadata"] = _clean_dict(self.metadata)
        return _clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "DecisionAction":
        if isinstance(data, DecisionAction):
            return data
        if isinstance(data, str):
            source = {"action_id": data, "name": data, "action_type": "unknown", "source": "unknown"}
        else:
            source = data if isinstance(data, dict) else {}
        action_id = _text(source.get("action_id") or source.get("id") or source.get("arm_id") or source.get("budget_plan_id") or source.get("name"))
        action_type = _text(source.get("action_type") or source.get("type") or "unknown", "unknown")
        action_source = _text(source.get("source") or "unknown", "unknown")
        if action_source not in ACTION_SOURCES:
            action_source = "unknown"
        metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {
            key: value
            for key, value in source.items()
            if key not in {"action_id", "id", "arm_id", "budget_plan_id", "action_type", "type", "name", "source", "score", "rank"}
        }
        return cls(
            action_id=action_id,
            action_type=action_type,
            name=_text(source.get("name") or action_id),
            source=action_source,
            score=_nullable_float(source.get("score")),
            rank=_nullable_int(source.get("rank")),
            metadata=_clean_dict(metadata),
        )


@dataclass
class DecisionSnapshot:
    decision_id: str = ""
    decision_type: str = "unknown"
    workflow_run_id: str | None = None
    iteration: int | None = None
    alpha_id: str | None = None
    experiment_id: str | None = None
    arm_id: str | None = None
    budget_plan_id: str | None = None
    available_actions: list[DecisionAction] = field(default_factory=list)
    chosen_action: DecisionAction | None = None
    legacy_choice: DecisionAction | None = None
    model_choice: DecisionAction | None = None
    experiment_choice: DecisionAction | None = None
    governance_decision: str | None = None
    features: dict[str, Any] = field(default_factory=dict)
    scores: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    actual_result: dict[str, Any] | None = None
    reward: float | None = None
    platform_sc_status: str | None = None
    platform_sc_abs_max: float | None = None
    success: bool | None = None
    quality_passed: bool | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["decision_type"] = self.decision_type if self.decision_type in DECISION_TYPES else str(self.decision_type or "unknown")
        data["available_actions"] = [action.to_dict() if isinstance(action, DecisionAction) else DecisionAction.from_dict(action).to_dict() for action in self.available_actions]
        for key in ("chosen_action", "legacy_choice", "model_choice", "experiment_choice"):
            value = getattr(self, key)
            data[key] = None if value is None else (value.to_dict() if isinstance(value, DecisionAction) else DecisionAction.from_dict(value).to_dict())
        data["features"] = _clean_dict(self.features)
        data["scores"] = _clean_dict(self.scores)
        data["context"] = _clean_dict(self.context)
        data["actual_result"] = None if self.actual_result is None else _clean_dict(self.actual_result)
        data["reward"] = _nullable_float(self.reward)
        data["platform_sc_abs_max"] = _nullable_float(self.platform_sc_abs_max)
        data["success"] = _nullable_bool(self.success)
        data["quality_passed"] = _nullable_bool(self.quality_passed)
        data["raw_payload"] = _clean_dict(self.raw_payload)
        return _clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "DecisionSnapshot":
        source = data.to_dict() if isinstance(data, DecisionSnapshot) else (data if isinstance(data, dict) else {})
        return cls(
            decision_id=_text(source.get("decision_id")),
            decision_type=_text(source.get("decision_type") or "unknown", "unknown"),
            workflow_run_id=_nullable_text(source.get("workflow_run_id")),
            iteration=_nullable_int(source.get("iteration")),
            alpha_id=_nullable_text(source.get("alpha_id")),
            experiment_id=_nullable_text(source.get("experiment_id")),
            arm_id=_nullable_text(source.get("arm_id")),
            budget_plan_id=_nullable_text(source.get("budget_plan_id")),
            available_actions=[DecisionAction.from_dict(item) for item in (source.get("available_actions") or [])],
            chosen_action=DecisionAction.from_dict(source.get("chosen_action")) if source.get("chosen_action") else None,
            legacy_choice=DecisionAction.from_dict(source.get("legacy_choice")) if source.get("legacy_choice") else None,
            model_choice=DecisionAction.from_dict(source.get("model_choice")) if source.get("model_choice") else None,
            experiment_choice=DecisionAction.from_dict(source.get("experiment_choice")) if source.get("experiment_choice") else None,
            governance_decision=_nullable_text(source.get("governance_decision")),
            features=_clean_dict(source.get("features") or {}),
            scores=_clean_dict(source.get("scores") or source.get("action_scores") or {}),
            context=_clean_dict(source.get("context") or {}),
            actual_result=_clean_dict(source.get("actual_result") or {}) if source.get("actual_result") is not None else None,
            reward=_nullable_float(source.get("reward")),
            platform_sc_status=_nullable_text(source.get("platform_sc_status")),
            platform_sc_abs_max=_nullable_float(source.get("platform_sc_abs_max")),
            success=_nullable_bool(source.get("success")),
            quality_passed=_nullable_bool(source.get("quality_passed")),
            created_at=_text(source.get("created_at") or utc_now_iso()),
            updated_at=_text(source.get("updated_at") or source.get("created_at") or utc_now_iso()),
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class DecisionOutcome:
    outcome_id: str = ""
    decision_id: str = ""
    alpha_id: str | None = None
    success: bool | None = None
    reward: float | None = None
    sharpe: float | None = None
    fitness: float | None = None
    returns: float | None = None
    turnover: float | None = None
    drawdown: float | None = None
    margin: float | None = None
    platform_sc_status: str | None = None
    platform_sc_abs_max: float | None = None
    quality_passed: bool | None = None
    failure_type: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("reward", "sharpe", "fitness", "returns", "turnover", "drawdown", "margin", "platform_sc_abs_max"):
            data[key] = _nullable_float(getattr(self, key))
        data["success"] = _nullable_bool(self.success)
        data["quality_passed"] = _nullable_bool(self.quality_passed)
        data["raw_payload"] = _clean_dict(self.raw_payload)
        return _clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "DecisionOutcome":
        source = data.to_dict() if isinstance(data, DecisionOutcome) else (data if isinstance(data, dict) else {})
        return cls(
            outcome_id=_text(source.get("outcome_id")),
            decision_id=_text(source.get("decision_id")),
            alpha_id=_nullable_text(source.get("alpha_id")),
            success=_nullable_bool(source.get("success")),
            reward=_nullable_float(source.get("reward")),
            sharpe=_nullable_float(source.get("sharpe")),
            fitness=_nullable_float(source.get("fitness")),
            returns=_nullable_float(source.get("returns")),
            turnover=_nullable_float(source.get("turnover")),
            drawdown=_nullable_float(source.get("drawdown")),
            margin=_nullable_float(source.get("margin")),
            platform_sc_status=_nullable_text(source.get("platform_sc_status")),
            platform_sc_abs_max=_nullable_float(source.get("platform_sc_abs_max")),
            quality_passed=_nullable_bool(source.get("quality_passed")),
            failure_type=_nullable_text(source.get("failure_type")),
            created_at=_text(source.get("created_at") or utc_now_iso()),
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class DecisionSnapshotSummary:
    decision_type: str = "unknown"
    sample_count: int = 0
    outcome_count: int = 0
    success_count: int = 0
    avg_reward: float | None = None
    avg_platform_sc_abs_max: float | None = None
    updated_at: str = field(default_factory=utc_now_iso)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["sample_count"] = int(self.sample_count or 0)
        data["outcome_count"] = int(self.outcome_count or 0)
        data["success_count"] = int(self.success_count or 0)
        data["avg_reward"] = _nullable_float(self.avg_reward)
        data["avg_platform_sc_abs_max"] = _nullable_float(self.avg_platform_sc_abs_max)
        data["raw_payload"] = _clean_dict(self.raw_payload)
        return _clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "DecisionSnapshotSummary":
        source = data.to_dict() if isinstance(data, DecisionSnapshotSummary) else (data if isinstance(data, dict) else {})
        return cls(
            decision_type=_text(source.get("decision_type") or "unknown", "unknown"),
            sample_count=int(_nullable_int(source.get("sample_count")) or 0),
            outcome_count=int(_nullable_int(source.get("outcome_count")) or 0),
            success_count=int(_nullable_int(source.get("success_count")) or 0),
            avg_reward=_nullable_float(source.get("avg_reward")),
            avg_platform_sc_abs_max=_nullable_float(source.get("avg_platform_sc_abs_max")),
            updated_at=_text(source.get("updated_at") or utc_now_iso()),
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class ReplayDatasetFilter:
    decision_types: list[str] = field(default_factory=list)
    start_time: str | None = None
    end_time: str | None = None
    min_samples: int = 0
    require_outcome: bool = False
    experiment_id: str | None = None
    arm_id: str | None = None
    budget_plan_id: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean_dict(
            {
                "decision_types": [str(item) for item in _clean_list(self.decision_types)],
                "start_time": _nullable_text(self.start_time),
                "end_time": _nullable_text(self.end_time),
                "min_samples": int(_nullable_int(self.min_samples) or 0),
                "require_outcome": bool(self.require_outcome),
                "experiment_id": _nullable_text(self.experiment_id),
                "arm_id": _nullable_text(self.arm_id),
                "budget_plan_id": _nullable_text(self.budget_plan_id),
                "raw_payload": _clean_dict(self.raw_payload),
            }
        )

    @classmethod
    def from_dict(cls, data: Any) -> "ReplayDatasetFilter":
        source = data.to_dict() if isinstance(data, ReplayDatasetFilter) else (data if isinstance(data, dict) else {})
        return cls(
            decision_types=[str(item) for item in _clean_list(source.get("decision_types") or source.get("decision_type") or [])],
            start_time=_nullable_text(source.get("start_time")),
            end_time=_nullable_text(source.get("end_time")),
            min_samples=int(_nullable_int(source.get("min_samples")) or 0),
            require_outcome=bool(_nullable_bool(source.get("require_outcome")) or False),
            experiment_id=_nullable_text(source.get("experiment_id")),
            arm_id=_nullable_text(source.get("arm_id")),
            budget_plan_id=_nullable_text(source.get("budget_plan_id")),
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class ReplayRecord:
    record_id: str = ""
    decision_id: str = ""
    decision_type: str = "unknown"
    alpha_id: str | None = None
    experiment_id: str | None = None
    arm_id: str | None = None
    budget_plan_id: str | None = None
    available_actions: list[DecisionAction] = field(default_factory=list)
    chosen_action: DecisionAction | None = None
    legacy_choice: DecisionAction | None = None
    model_choice: DecisionAction | None = None
    experiment_choice: DecisionAction | None = None
    budget_choice: DecisionAction | None = None
    features: dict[str, Any] = field(default_factory=dict)
    scores: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    outcome: DecisionOutcome | None = None
    reward: float | None = None
    success: bool | None = None
    platform_sc_abs_max: float | None = None
    quality_passed: bool | None = None
    created_at: str = field(default_factory=utc_now_iso)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["record_id"] = self.record_id or self.decision_id
        data["available_actions"] = [DecisionAction.from_dict(action).to_dict() for action in self.available_actions]
        for key in ("chosen_action", "legacy_choice", "model_choice", "experiment_choice", "budget_choice"):
            value = getattr(self, key)
            data[key] = None if value is None else DecisionAction.from_dict(value).to_dict()
        data["features"] = _clean_dict(self.features)
        data["scores"] = _clean_dict(self.scores)
        data["context"] = _clean_dict(self.context)
        data["outcome"] = None if self.outcome is None else DecisionOutcome.from_dict(self.outcome).to_dict()
        data["reward"] = _nullable_float(self.reward)
        data["success"] = _nullable_bool(self.success)
        data["platform_sc_abs_max"] = _nullable_float(self.platform_sc_abs_max)
        data["quality_passed"] = _nullable_bool(self.quality_passed)
        data["raw_payload"] = _clean_dict(self.raw_payload)
        return _clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "ReplayRecord":
        source = data.to_dict() if isinstance(data, ReplayRecord) else (data if isinstance(data, dict) else {})
        return cls(
            record_id=_text(source.get("record_id") or source.get("decision_id")),
            decision_id=_text(source.get("decision_id")),
            decision_type=_text(source.get("decision_type") or "unknown", "unknown"),
            alpha_id=_nullable_text(source.get("alpha_id")),
            experiment_id=_nullable_text(source.get("experiment_id")),
            arm_id=_nullable_text(source.get("arm_id")),
            budget_plan_id=_nullable_text(source.get("budget_plan_id")),
            available_actions=[DecisionAction.from_dict(item) for item in _clean_list(source.get("available_actions"))],
            chosen_action=DecisionAction.from_dict(source.get("chosen_action")) if source.get("chosen_action") else None,
            legacy_choice=DecisionAction.from_dict(source.get("legacy_choice")) if source.get("legacy_choice") else None,
            model_choice=DecisionAction.from_dict(source.get("model_choice")) if source.get("model_choice") else None,
            experiment_choice=DecisionAction.from_dict(source.get("experiment_choice")) if source.get("experiment_choice") else None,
            budget_choice=DecisionAction.from_dict(source.get("budget_choice")) if source.get("budget_choice") else None,
            features=_clean_dict(source.get("features") or {}),
            scores=_clean_dict(source.get("scores") or {}),
            context=_clean_dict(source.get("context") or {}),
            outcome=DecisionOutcome.from_dict(source.get("outcome")) if source.get("outcome") else None,
            reward=_nullable_float(source.get("reward")),
            success=_nullable_bool(source.get("success")),
            platform_sc_abs_max=_nullable_float(source.get("platform_sc_abs_max")),
            quality_passed=_nullable_bool(source.get("quality_passed")),
            created_at=_text(source.get("created_at") or utc_now_iso()),
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class ReplayPolicyDecision:
    policy_decision_id: str = ""
    replay_run_id: str = ""
    decision_id: str = ""
    policy_name: str = ""
    selected_action: DecisionAction | None = None
    selected_matches_actual: bool | None = None
    selected_matches_legacy: bool | None = None
    observable_outcome: bool = False
    reward: float | None = None
    success: bool | None = None
    platform_sc_abs_max: float | None = None
    quality_passed: bool | None = None
    reason_codes: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean_dict(
            {
                "policy_decision_id": self.policy_decision_id,
                "replay_run_id": self.replay_run_id,
                "decision_id": self.decision_id,
                "policy_name": self.policy_name,
                "selected_action": None if self.selected_action is None else DecisionAction.from_dict(self.selected_action).to_dict(),
                "selected_matches_actual": _nullable_bool(self.selected_matches_actual),
                "selected_matches_legacy": _nullable_bool(self.selected_matches_legacy),
                "observable_outcome": bool(self.observable_outcome),
                "reward": _nullable_float(self.reward),
                "success": _nullable_bool(self.success),
                "platform_sc_abs_max": _nullable_float(self.platform_sc_abs_max),
                "quality_passed": _nullable_bool(self.quality_passed),
                "reason_codes": [str(item) for item in _clean_list(self.reason_codes)],
                "created_at": self.created_at or utc_now_iso(),
                "raw_payload": _clean_dict(self.raw_payload),
            }
        )

    @classmethod
    def from_dict(cls, data: Any) -> "ReplayPolicyDecision":
        source = data.to_dict() if isinstance(data, ReplayPolicyDecision) else (data if isinstance(data, dict) else {})
        return cls(
            policy_decision_id=_text(source.get("policy_decision_id")),
            replay_run_id=_text(source.get("replay_run_id")),
            decision_id=_text(source.get("decision_id")),
            policy_name=_text(source.get("policy_name")),
            selected_action=DecisionAction.from_dict(source.get("selected_action")) if source.get("selected_action") else None,
            selected_matches_actual=_nullable_bool(source.get("selected_matches_actual")),
            selected_matches_legacy=_nullable_bool(source.get("selected_matches_legacy")),
            observable_outcome=bool(_nullable_bool(source.get("observable_outcome")) or False),
            reward=_nullable_float(source.get("reward")),
            success=_nullable_bool(source.get("success")),
            platform_sc_abs_max=_nullable_float(source.get("platform_sc_abs_max")),
            quality_passed=_nullable_bool(source.get("quality_passed")),
            reason_codes=[str(item) for item in _clean_list(source.get("reason_codes"))],
            created_at=_text(source.get("created_at") or utc_now_iso()),
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class ReplayRun:
    replay_run_id: str = ""
    name: str = ""
    status: str = "planned"
    policies: list[str] = field(default_factory=list)
    dataset_filter: ReplayDatasetFilter = field(default_factory=ReplayDatasetFilter)
    sample_count: int = 0
    observable_count: int = 0
    started_at: str = field(default_factory=utc_now_iso)
    completed_at: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        status = self.status if self.status in {"planned", "running", "completed", "failed", "insufficient_data"} else "failed"
        return _clean_dict(
            {
                "replay_run_id": self.replay_run_id,
                "name": self.name,
                "status": status,
                "policies": [str(item) for item in _clean_list(self.policies)],
                "dataset_filter": ReplayDatasetFilter.from_dict(self.dataset_filter).to_dict(),
                "sample_count": int(_nullable_int(self.sample_count) or 0),
                "observable_count": int(_nullable_int(self.observable_count) or 0),
                "started_at": self.started_at or utc_now_iso(),
                "completed_at": _nullable_text(self.completed_at),
                "raw_payload": _clean_dict(self.raw_payload),
            }
        )

    @classmethod
    def from_dict(cls, data: Any) -> "ReplayRun":
        source = data.to_dict() if isinstance(data, ReplayRun) else (data if isinstance(data, dict) else {})
        return cls(
            replay_run_id=_text(source.get("replay_run_id")),
            name=_text(source.get("name")),
            status=_text(source.get("status") or "planned", "planned"),
            policies=[str(item) for item in _clean_list(source.get("policies"))],
            dataset_filter=ReplayDatasetFilter.from_dict(source.get("dataset_filter") or {}),
            sample_count=int(_nullable_int(source.get("sample_count")) or 0),
            observable_count=int(_nullable_int(source.get("observable_count")) or 0),
            started_at=_text(source.get("started_at") or utc_now_iso()),
            completed_at=_nullable_text(source.get("completed_at")),
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class ReplayPolicyMetrics:
    replay_run_id: str = ""
    policy_name: str = ""
    decision_type: str | None = None
    sample_count: int = 0
    observable_count: int = 0
    coverage_rate: float = 0.0
    agreement_with_actual_rate: float | None = None
    agreement_with_legacy_rate: float | None = None
    avg_reward: float | None = None
    success_rate: float | None = None
    avg_platform_sc_abs_max: float | None = None
    quality_pass_rate: float | None = None
    insufficient_evidence_count: int = 0
    reason_codes: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean_dict(
            {
                "replay_run_id": self.replay_run_id,
                "policy_name": self.policy_name,
                "decision_type": _nullable_text(self.decision_type),
                "sample_count": int(_nullable_int(self.sample_count) or 0),
                "observable_count": int(_nullable_int(self.observable_count) or 0),
                "coverage_rate": float(_nullable_float(self.coverage_rate) or 0.0),
                "agreement_with_actual_rate": _nullable_float(self.agreement_with_actual_rate),
                "agreement_with_legacy_rate": _nullable_float(self.agreement_with_legacy_rate),
                "avg_reward": _nullable_float(self.avg_reward),
                "success_rate": _nullable_float(self.success_rate),
                "avg_platform_sc_abs_max": _nullable_float(self.avg_platform_sc_abs_max),
                "quality_pass_rate": _nullable_float(self.quality_pass_rate),
                "insufficient_evidence_count": int(_nullable_int(self.insufficient_evidence_count) or 0),
                "reason_codes": [str(item) for item in _clean_list(self.reason_codes)],
                "raw_payload": _clean_dict(self.raw_payload),
            }
        )

    @classmethod
    def from_dict(cls, data: Any) -> "ReplayPolicyMetrics":
        source = data.to_dict() if isinstance(data, ReplayPolicyMetrics) else (data if isinstance(data, dict) else {})
        return cls(
            replay_run_id=_text(source.get("replay_run_id")),
            policy_name=_text(source.get("policy_name")),
            decision_type=_nullable_text(source.get("decision_type")),
            sample_count=int(_nullable_int(source.get("sample_count")) or 0),
            observable_count=int(_nullable_int(source.get("observable_count")) or 0),
            coverage_rate=float(_nullable_float(source.get("coverage_rate")) or 0.0),
            agreement_with_actual_rate=_nullable_float(source.get("agreement_with_actual_rate")),
            agreement_with_legacy_rate=_nullable_float(source.get("agreement_with_legacy_rate")),
            avg_reward=_nullable_float(source.get("avg_reward")),
            success_rate=_nullable_float(source.get("success_rate")),
            avg_platform_sc_abs_max=_nullable_float(source.get("avg_platform_sc_abs_max")),
            quality_pass_rate=_nullable_float(source.get("quality_pass_rate")),
            insufficient_evidence_count=int(_nullable_int(source.get("insufficient_evidence_count")) or 0),
            reason_codes=[str(item) for item in _clean_list(source.get("reason_codes"))],
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class ReplayComparison:
    comparison_id: str = ""
    replay_run_id: str = ""
    baseline_policy: str = ""
    challenger_policy: str = ""
    decision_type: str | None = None
    baseline_metrics: dict[str, Any] = field(default_factory=dict)
    challenger_metrics: dict[str, Any] = field(default_factory=dict)
    reward_delta: float | None = None
    success_rate_delta: float | None = None
    sc_risk_delta: float | None = None
    quality_pass_delta: float | None = None
    confidence: str = "insufficient"
    verdict: str = "insufficient_evidence"
    created_at: str = field(default_factory=utc_now_iso)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        confidence = self.confidence if self.confidence in {"insufficient", "low", "medium", "high"} else "insufficient"
        verdict = self.verdict if self.verdict in {"challenger_better", "challenger_worse", "no_clear_difference", "insufficient_evidence"} else "insufficient_evidence"
        return _clean_dict(
            {
                "comparison_id": self.comparison_id,
                "replay_run_id": self.replay_run_id,
                "baseline_policy": self.baseline_policy,
                "challenger_policy": self.challenger_policy,
                "decision_type": _nullable_text(self.decision_type),
                "baseline_metrics": _clean_dict(self.baseline_metrics),
                "challenger_metrics": _clean_dict(self.challenger_metrics),
                "reward_delta": _nullable_float(self.reward_delta),
                "success_rate_delta": _nullable_float(self.success_rate_delta),
                "sc_risk_delta": _nullable_float(self.sc_risk_delta),
                "quality_pass_delta": _nullable_float(self.quality_pass_delta),
                "confidence": confidence,
                "verdict": verdict,
                "created_at": self.created_at or utc_now_iso(),
                "raw_payload": _clean_dict(self.raw_payload),
            }
        )

    @classmethod
    def from_dict(cls, data: Any) -> "ReplayComparison":
        source = data.to_dict() if isinstance(data, ReplayComparison) else (data if isinstance(data, dict) else {})
        return cls(
            comparison_id=_text(source.get("comparison_id")),
            replay_run_id=_text(source.get("replay_run_id")),
            baseline_policy=_text(source.get("baseline_policy")),
            challenger_policy=_text(source.get("challenger_policy")),
            decision_type=_nullable_text(source.get("decision_type")),
            baseline_metrics=_clean_dict(source.get("baseline_metrics") or {}),
            challenger_metrics=_clean_dict(source.get("challenger_metrics") or {}),
            reward_delta=_nullable_float(source.get("reward_delta")),
            success_rate_delta=_nullable_float(source.get("success_rate_delta")),
            sc_risk_delta=_nullable_float(source.get("sc_risk_delta")),
            quality_pass_delta=_nullable_float(source.get("quality_pass_delta")),
            confidence=_text(source.get("confidence") or "insufficient", "insufficient"),
            verdict=_text(source.get("verdict") or "insufficient_evidence", "insufficient_evidence"),
            created_at=_text(source.get("created_at") or utc_now_iso()),
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )
