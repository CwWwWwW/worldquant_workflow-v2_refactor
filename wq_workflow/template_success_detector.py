from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from .logger_state import log_state_event
from .quality import extract_metrics


SUCCESS_CANDIDATE = "SUCCESS_CANDIDATE"
RESULT_UNCERTAIN = "RESULT_UNCERTAIN"


@dataclass(slots=True)
class TemplateSuccessDetection:
    template_success: bool
    average_present: bool
    fail_count: int | None
    show_test_period_revealed: bool
    reason: str
    strong_present: bool = False
    candidate_success: bool = False
    result_uncertain: bool = False
    candidate_reason: str = ""
    signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def detect_template_success(
    text: str,
    *,
    show_test_period_revealed: bool,
    thresholds: dict[str, float] | None = None,
    expression: str = "",
) -> TemplateSuccessDetection:
    raw_text = text or ""
    has_result_scope = _has_result_marker(raw_text)
    scoped = _result_scope(raw_text) if has_result_scope else raw_text
    summary_text = _section_after(scoped, "IS Summary") or scoped
    status_text = _section_after(scoped, "IS Testing Status") or _section_after(scoped, "EXPANDED IS TESTING STATUS") or scoped
    average_present = bool(re.search(r"\bAverage\b", summary_text, re.I))
    strong_present = bool(re.search(r"\bStrong\b", summary_text, re.I))
    fail_count = _explicit_fail_count(status_text)
    if fail_count is None:
        fail_count = _explicit_fail_count(scoped)
    metrics = extract_metrics(scoped)
    signals = _candidate_signals(
        raw_text=raw_text,
        scoped_text=scoped,
        metrics=metrics,
        thresholds=thresholds or {},
        expression=expression,
        has_result_scope=has_result_scope,
        average_present=average_present,
        strong_present=strong_present,
        fail_count=fail_count,
    )
    candidate_success = bool(signals and (fail_count is None or fail_count == 0))
    result_uncertain = _result_uncertain(raw_text, has_result_scope, candidate_success)

    if not show_test_period_revealed:
        return TemplateSuccessDetection(
            False,
            average_present,
            fail_count,
            False,
            "show_test_period_not_revealed",
            strong_present,
            candidate_success,
            result_uncertain,
            _candidate_reason(signals),
            signals,
        )
    if fail_count is not None and fail_count != 0:
        return TemplateSuccessDetection(False, average_present, fail_count, True, "fail_count_nonzero", strong_present)
    if not (average_present or strong_present):
        return TemplateSuccessDetection(
            False,
            False,
            fail_count,
            True,
            "average_or_strong_missing",
            False,
            candidate_success,
            result_uncertain,
            _candidate_reason(signals),
            signals,
        )
    if fail_count is None:
        return TemplateSuccessDetection(
            False,
            average_present,
            None,
            True,
            "explicit_fail_count_missing",
            strong_present,
            candidate_success,
            result_uncertain,
            _candidate_reason(signals),
            signals,
        )
    if not has_result_scope:
        return TemplateSuccessDetection(False, average_present, fail_count, True, "result_scope_missing", strong_present)
    if strong_present:
        return TemplateSuccessDetection(
            True,
            average_present,
            0,
            True,
            "strong_with_zero_fail",
            True,
            True,
            False,
            "strong_with_zero_fail",
            signals or ["strong_with_zero_fail"],
        )
    return TemplateSuccessDetection(
        True,
        True,
        0,
        True,
        "average_with_zero_fail",
        False,
        True,
        False,
        "average_with_zero_fail",
        signals or ["average_with_zero_fail"],
    )


def confirm_success_candidate(detection: TemplateSuccessDetection, *, reason: str = "candidate_stabilized") -> TemplateSuccessDetection:
    if not detection.candidate_success or (detection.fail_count is not None and detection.fail_count != 0):
        return detection
    return replace(
        detection,
        template_success=True,
        result_uncertain=False,
        reason=reason,
        candidate_reason=detection.candidate_reason or reason,
    )


def emit_template_success_event(
    *,
    alpha_id: str,
    detection: TemplateSuccessDetection,
    template_file: str = "",
    simulation_id: str = "",
) -> None:
    payload = {
        "template_success": detection.template_success,
        "template_success_reason": detection.reason,
        "average_present": detection.average_present,
        "strong_present": detection.strong_present,
        "fail_count": detection.fail_count,
        "show_test_period_revealed": detection.show_test_period_revealed,
        "template_file": template_file,
    }
    try:
        log_state_event(
            "TEMPLATE_SUCCESS",
            alpha_id=alpha_id,
            state="TEMPLATE_SUCCESS",
            simulation_id=simulation_id or None,
            extra=payload,
        )
    except Exception:
        logging.info("Failed to write template success FSM event", exc_info=True)
    logging.info("TEMPLATE_SUCCESS_RESULT %s", json.dumps({"alpha_id": alpha_id, **payload}, ensure_ascii=False))


def _explicit_fail_count(text: str) -> int | None:
    matches = re.findall(r"\b(\d+)\s+FAIL\b", text or "", re.I)
    if not matches:
        return None
    try:
        counts = [int(match) for match in matches]
    except ValueError:
        return None
    nonzero = [count for count in counts if count != 0]
    return nonzero[-1] if nonzero else counts[-1]


def _candidate_signals(
    *,
    raw_text: str,
    scoped_text: str,
    metrics: dict[str, float],
    thresholds: dict[str, float],
    expression: str,
    has_result_scope: bool,
    average_present: bool,
    strong_present: bool,
    fail_count: int | None,
) -> list[str]:
    if not has_result_scope:
        return []
    if fail_count is not None and fail_count != 0:
        return []
    if re.search(r"\bNeeds\s+Improvement\b", scoped_text or "", re.I):
        return []

    signals: list[str] = []
    if strong_present and fail_count == 0:
        signals.append("strong_with_zero_fail")
    if average_present and fail_count == 0:
        signals.append("average_with_zero_fail")
    if _has_valid_alpha_payload(scoped_text, metrics):
        signals.append("valid_alpha_payload")
    if _metrics_meet_success_thresholds(metrics, thresholds):
        signals.append("score_threshold")
    if _expression_present(raw_text, expression):
        signals.append("expression_present")
    return signals


def _has_valid_alpha_payload(text: str, metrics: dict[str, float]) -> bool:
    if len(metrics) >= 2:
        return True
    if metrics and re.search(r"\bIS Summary\b|\bAggregate Data\b", text or "", re.I):
        return True
    return bool(
        re.search(r"\b(?:Sharpe|Fitness|Turnover|Drawdown|Margin|Returns)\b[\s\S]{0,80}\b-?\d+(?:\.\d+)?%?", text or "", re.I)
        and re.search(r"\bIS Summary\b|\bAggregate Data\b|\bLast Run\b", text or "", re.I)
    )


def _metrics_meet_success_thresholds(metrics: dict[str, float], thresholds: dict[str, float]) -> bool:
    if not metrics:
        return False
    checks: list[bool] = []
    if "sharpe" in metrics and "sharpe_min" in thresholds:
        checks.append(metrics["sharpe"] >= thresholds["sharpe_min"])
    if "fitness" in metrics and "fitness_min" in thresholds:
        checks.append(metrics["fitness"] >= thresholds["fitness_min"])
    if "sub_universe_sharpe" in metrics and "sub_universe_sharpe_min" in thresholds:
        checks.append(metrics["sub_universe_sharpe"] >= thresholds["sub_universe_sharpe_min"])
    if "turnover" in metrics and "turnover_min" in thresholds:
        checks.append(metrics["turnover"] >= thresholds["turnover_min"])
    if "turnover" in metrics and "turnover_max" in thresholds:
        checks.append(metrics["turnover"] <= thresholds["turnover_max"])
    if "drawdown" in metrics and "drawdown_max" in thresholds:
        checks.append(metrics["drawdown"] <= thresholds["drawdown_max"])
    return bool(checks) and all(checks)


def _expression_present(text: str, expression: str) -> bool:
    compact_expression = _compact_expression(expression)
    if len(compact_expression) < 24:
        return False
    compact_text = _compact_expression(text)
    if compact_expression in compact_text:
        return True
    head = compact_expression[: min(120, len(compact_expression))]
    return len(head) >= 40 and head in compact_text


def _compact_expression(value: str) -> str:
    return re.sub(r"\s+", "", value or "").lower()


def _candidate_reason(signals: list[str]) -> str:
    return ",".join(signals)


def _result_uncertain(text: str, has_result_scope: bool, candidate_success: bool) -> bool:
    if candidate_success:
        return True
    if not (text or "").strip():
        return True
    return has_result_scope and not re.search(r"\b\d+\s+(?:PASS|FAIL|PENDING)\b", text or "", re.I)


def _result_scope(text: str) -> str:
    compact = text or ""
    markers = [
        "IS Summary",
        "IS Testing Status",
        "EXPANDED IS TESTING STATUS",
        "Aggregate Data",
        "Last Run",
    ]
    positions = [match.start() for marker in markers for match in re.finditer(re.escape(marker), compact, re.I)]
    if not positions:
        return compact
    start = max(0, min(positions) - 240)
    return compact[start:]


def _has_result_marker(text: str) -> bool:
    return bool(re.search(r"IS Summary|IS Testing Status|EXPANDED IS TESTING STATUS|Aggregate Data|Last Run", text or "", re.I))


def _section_after(text: str, marker: str) -> str:
    match = re.search(re.escape(marker), text or "", re.I)
    if not match:
        return ""
    tail = text[match.start() :]
    next_marker = re.search(
        r"\b(?:OS Summary|OS Testing Status|Settings|Properties|Tutorial Checks|Performance Comparison|Correlation|Chart)\b",
        tail[len(marker) :],
        re.I,
    )
    if next_marker:
        return tail[: len(marker) + next_marker.start()]
    return tail
