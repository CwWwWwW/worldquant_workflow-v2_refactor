from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def build_replay_report(**kwargs: Any) -> dict[str, Any]:
    report = dict(kwargs)
    report.setdefault("report_id", f"replay_report:{uuid.uuid4().hex}")
    report.setdefault("created_at", _now())
    report.setdefault("reasons", [])
    report.setdefault("report_json", {k: v for k, v in report.items() if k != "raw_payload"})
    report.setdefault("raw_payload", report.get("report_json", {}))
    return report


def save_replay_report(repositories: Any, report: dict[str, Any]) -> str | None:
    repo = getattr(repositories, "replay", None) if repositories is not None else None
    if repo is None:
        return None
    return repo.insert_offline_replay_report(report)


def save_policy_replay_evaluation(repositories: Any, evaluation: dict[str, Any]) -> str | None:
    repo = getattr(repositories, "replay", None) if repositories is not None else None
    if repo is None:
        return None
    return repo.insert_policy_replay_evaluation(evaluation)


def save_model_safety_report(repositories: Any, report: dict[str, Any]) -> str | None:
    repo = getattr(repositories, "replay", None) if repositories is not None else None
    if repo is None:
        return None
    return repo.insert_model_safety_report(report)


def load_latest_replay_report(repositories: Any, task_name: str | None = None, strategy_id: str | None = None, decision_type: str | None = None) -> dict[str, Any] | None:
    repo = getattr(repositories, "replay", None) if repositories is not None else None
    if repo is None:
        return None
    return repo.latest_offline_replay_report(task_name=task_name, strategy_id=strategy_id, decision_type=decision_type)


def summarize_replay_report(report: dict[str, Any] | None) -> dict[str, Any]:
    data = report if isinstance(report, dict) else {}
    return {
        "report_id": data.get("report_id", ""),
        "task_name": data.get("task_name", ""),
        "decision_type": data.get("decision_type", ""),
        "sample_count": int(data.get("sample_count") or 0),
        "support_coverage": float(data.get("support_coverage") or 0.0),
        "model_match_rate": float(data.get("model_match_rate") or 0.0),
        "estimated_reward_delta": float(data.get("estimated_reward_delta") or 0.0),
        "estimated_sc_risk_delta": float(data.get("estimated_sc_risk_delta", data.get("estimated_risk_delta")) or 0.0),
        "estimated_failure_delta": float(data.get("estimated_failure_delta") or 0.0),
        "replay_pass": bool(data.get("replay_pass")),
        "reasons": list(data.get("reasons") or []),
    }
