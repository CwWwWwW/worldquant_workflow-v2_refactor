from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SampleQualityReport:
    ok: bool = True
    task_name: str = ""
    sample_count: int = 0
    invalid_count: int = 0
    invalid_ratio: float = 0.0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    recommended_action: str = "allow_train"
    confidence_multiplier: float = 1.0
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except Exception:
        return False


def _walk_bad_number(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, dict):
        return any(_walk_bad_number(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_walk_bad_number(v) for v in value)
    return False


class SampleQualityChecker:
    def __init__(self, config: Any | None = None, event_logger: Any | None = None, logger: Any | None = None) -> None:
        self.config = config
        self.event_logger = event_logger
        self.logger = logger

    def check(self, task_name: str, samples: list[dict[str, Any]] | None) -> SampleQualityReport:
        task = str(task_name or "")
        samples = [s for s in (samples or []) if isinstance(s, dict)]
        warnings: list[str] = []
        errors: list[str] = []
        seen: set[str] = set()
        invalid = 0
        families: dict[str, int] = {}
        for idx, sample in enumerate(samples):
            sample_errors: list[str] = []
            sid = sample.get("sample_id") or sample.get("id")
            if not sid:
                sample_errors.append("sample_id_missing")
            elif str(sid) in seen:
                sample_errors.append("duplicate_sample_id")
            else:
                seen.add(str(sid))
            if "features" not in sample and "features_json" not in sample and task not in {"parent", "policy", "insight"}:
                sample_errors.append("features_missing")
            if "label" not in sample and "label_json" not in sample and task not in {"parent", "policy", "insight"}:
                sample_errors.append("label_missing")
            if _walk_bad_number(sample):
                sample_errors.append("nan_or_inf")
            if not sample.get("source"):
                warnings.append(f"source_missing:{sid or idx}")
            family = sample.get("family") or sample.get("family_id")
            if family:
                families[str(family)] = families.get(str(family), 0) + 1
            if task == "sc":
                status = sample.get("platform_sc_status") or sample.get("sc_status")
                abs_max = sample.get("platform_sc_abs_max")
                if status != "complete":
                    sample_errors.append("platform_sc_status_not_complete")
                if not _finite(abs_max):
                    sample_errors.append("platform_sc_abs_max_invalid")
                elif not (0.0 <= abs(float(abs_max)) <= 1.5):
                    sample_errors.append("platform_sc_abs_max_out_of_range")
            elif task == "parent":
                if not sample.get("parent_alpha_id") or not sample.get("child_alpha_id"):
                    warnings.append(f"parent_child_id_missing:{sid or idx}")
                if sample.get("child_reward") is None and sample.get("reward_delta") is None:
                    warnings.append(f"child_reward_missing:{sid or idx}")
                risk = sample.get("child_sc_risk") or sample.get("child_platform_sc_abs_max")
                if _finite(risk) and float(risk) > 1.0:
                    warnings.append(f"child_sc_risk_extreme:{sid or idx}")
            elif task == "policy":
                if not sample.get("available_actions") and not sample.get("available_actions_json"):
                    sample_errors.append("available_actions_missing")
                if not sample.get("chosen_action") and not sample.get("chosen_action_json"):
                    sample_errors.append("chosen_action_missing")
                if sample.get("reward_delta") is None:
                    warnings.append(f"reward_delta_missing:{sid or idx}")
            elif task in {"simulator", "outcome"}:
                raw = sample.get("raw_payload") if isinstance(sample.get("raw_payload"), dict) else sample
                if not ("skip_would_have_been_wrong" in raw):
                    sample_errors.append("false_skip_label_missing")
                if sample.get("backtest_success") is None and sample.get("quality_passed") is None:
                    sample_errors.append("real_backtest_label_missing")
            elif task == "insight":
                if int(sample.get("support_count") or 0) <= 0:
                    warnings.append(f"support_count_low:{sid or idx}")
                if int(sample.get("contradiction_count") or 0) > 0:
                    warnings.append(f"contradiction_high:{sid or idx}")
                if sample.get("effect_score") is None and sample.get("reward") is None:
                    warnings.append(f"effect_score_missing:{sid or idx}")
            if sample_errors:
                invalid += 1
                errors.extend(f"{e}:{sid or idx}" for e in sample_errors)
        count = len(samples)
        ratio = invalid / count if count else 1.0
        max_ratio = float(getattr(self.config, "sc_max_invalid_sample_ratio", 0.05) if task == "sc" else getattr(self.config, "ml_max_invalid_sample_ratio", 0.2) or 0.2)
        if families and max(families.values()) / max(1, count) > 0.7:
            warnings.append("family_over_concentrated")
        ok = count > 0 and ratio <= max_ratio
        action = "allow_train" if ok else "block_train"
        if ok and (warnings or ratio > 0):
            action = "keep_shadow"
        report = SampleQualityReport(ok=ok, task_name=task, sample_count=count, invalid_count=invalid, invalid_ratio=ratio, warnings=warnings, errors=errors, recommended_action=action, confidence_multiplier=max(0.0, 1.0 - ratio), raw_payload={"max_invalid_ratio": max_ratio})
        if not ok or errors:
            try:
                if self.event_logger is not None:
                    self.event_logger.record(task_name=task, event_type="sample_pollution_detected", severity="warning", message="sample quality issues detected", action_taken=action, raw_payload=report.to_dict())
            except Exception:
                pass
        return report
