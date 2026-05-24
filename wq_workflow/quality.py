from __future__ import annotations

from difflib import SequenceMatcher
import re

from .models import QualityReport


QUALITY_ADVICE_EXAMPLES = [
    "try to use bucket operator to neutralize your alpha using custom groups",
    "try using bucket operator to neutralize alpha with custom groups",
    "use bucket operator to neutralize your alpha using custom groups",
]


def parse_percent_or_float(value: str) -> float | None:
    try:
        return float(value.replace("%", "").replace("‰", "").strip())
    except ValueError:
        return None


def extract_metrics(text: str) -> dict[str, float]:
    patterns = {
        "sharpe": [r"\bSharpe\b\s*[:：]?\s*(-?\d+(?:\.\d+)?)"],
        "turnover": [r"\bTurnover\b\s*[:：]?\s*(-?\d+(?:\.\d+)?%?)"],
        "fitness": [r"\bFitness\b\s*[:：]?\s*(-?\d+(?:\.\d+)?)"],
        "returns": [r"\bReturns\b\s*[:：]?\s*(-?\d+(?:\.\d+)?%?)"],
        "drawdown": [r"\bDrawdown\b\s*[:：]?\s*(-?\d+(?:\.\d+)?%?)"],
        "margin": [r"\bMargin\b\s*[:：]?\s*(-?\d+(?:\.\d+)?[%‰]?)"],
        "sub_universe_sharpe": [r"Sub[- ]universe\s+Sharpe\s+of\s+(-?\d+(?:\.\d+)?)"],
    }
    metrics: dict[str, float] = {}
    for key, key_patterns in patterns.items():
        for pattern in key_patterns:
            match = re.search(pattern, text, re.I)
            if not match:
                continue
            value = parse_percent_or_float(match.group(1))
            if value is not None:
                metrics[key] = abs(value) if key == "drawdown" else value
                break
    return metrics


def _count_status(label: str, text: str) -> int:
    matches = re.findall(rf"\b(\d+)\s+{label}\b", text, re.I)
    return int(matches[-1]) if matches else 0


def _status_messages(text: str, label: str) -> list[str]:
    expanded = _expanded_status_messages(text, label)
    if expanded:
        return expanded
    section = _slice_section(text, "IS Testing Status", 2500) or text
    lines = [line.strip(" •\t") for line in section.splitlines() if line.strip()]
    messages: list[str] = []
    collecting = False
    for line in lines:
        if _is_status_heading(line, label):
            collecting = True
            continue
        if collecting and _is_any_status_heading(line):
            break
        if collecting and _is_plausible_status_message(line) and (
            looks_like_quality_advice(line)
            or re.search(r"cutoff|well distributed|Self-correlation|match|above|below|pending|Sharpe|Fitness|Turnover|Drawdown|Margin", line, re.I)
        ):
            messages.append(line)
    return messages


def parse_quality_report(text: str) -> QualityReport:
    text = _strip_tutorial_sections(text)
    metrics = extract_metrics(text)
    pass_count = _count_status("PASS", text)
    fail_count = _count_status("FAIL", text)
    pending_count = _count_status("PENDING", text)

    summary_status = "unknown"
    if re.search(r"Needs\s+Improvement", text, re.I):
        summary_status = "needs_improvement"
    elif re.search(r"\bAverage\b", text, re.I):
        summary_status = "average"
    elif re.search(r"\bExcellent\b|\bGood\b|\bReady\b", text, re.I):
        summary_status = "pass"

    fail_messages = _status_messages(text, "FAIL")
    fail_messages = _dedupe(fail_messages)
    pass_messages = _dedupe(_status_messages(text, "PASS"))
    pending_messages = _dedupe(_status_messages(text, "PENDING"))

    explicit_status_seen = bool(
        pass_count
        or fail_count
        or pending_count
        or "IS Summary" in text
        or "IS Testing Status" in text
    )
    has_concrete_quality = bool(pass_count or fail_count or pending_count or metrics)
    passed = (
        explicit_status_seen
        and has_concrete_quality
        and fail_count == 0
        and pending_count == 0
        and summary_status not in {"needs_improvement", "average"}
    )

    return QualityReport(
        passed=passed,
        status=summary_status,
        pass_count=pass_count,
        fail_count=fail_count,
        pending_count=pending_count,
        metrics=metrics,
        pass_messages=pass_messages,
        fail_messages=fail_messages,
        pending_messages=pending_messages,
        summary_text=_slice_section(text, "IS Summary", 5000),
        testing_text=_testing_status_text(text),
    )


def _testing_status_text(text: str) -> str:
    expanded = _slice_section(text, "EXPANDED IS TESTING STATUS", 12000)
    if expanded:
        return expanded
    return _slice_section(text, "IS Testing Status", 5000)


def _strip_tutorial_sections(text: str) -> str:
    lines: list[str] = []
    for line in (text or "").splitlines():
        compact = re.sub(r"\s+", " ", line).strip()
        if re.search(r"Tutorial Checks|Tutorial task|Exit tutorial mode|Completed task|Show test period", compact, re.I):
            continue
        lines.append(line)
    return "\n".join(lines)


def _tutorial_messages(text: str) -> list[str]:
    if not re.search(r"Tutorial Checks|Tutorial task", text, re.I):
        return []
    messages: list[str] = []
    lines = [line.strip(" \t") for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if re.search(r"Tutorial task not met|task not met", line, re.I):
            messages.append(line)
            for follow in lines[index + 1 : index + 4]:
                if re.search(r"button|go back|exit tutorial|show test period", follow, re.I):
                    continue
                messages.append(follow)
    if not messages:
        for line in lines:
            if re.search(r"Tutorial Checks|vwap/close|turnover below|task", line, re.I):
                messages.append(line)
    return _dedupe(messages)


def extract_quality_advice_messages(text: str) -> list[str]:
    messages: list[str] = []
    section = _slice_section(text, "IS Testing Status", 2500) or text
    for line in [line.strip(" •\t") for line in section.splitlines() if line.strip()]:
        if not _is_plausible_status_message(line):
            continue
        if looks_like_quality_advice(line):
            messages.append(line)
    if not messages and looks_like_quality_advice(text):
        messages.append(_compact_text(text)[:500])
    return _dedupe(messages)


def _expanded_status_messages(text: str, label: str) -> list[str]:
    expanded = _slice_section(text, "EXPANDED IS TESTING STATUS", 12000)
    if not expanded:
        return []
    markers = list(re.finditer(r"(?im)^\s*\[\s*(PASS|FAIL|PENDING)\s*\]\s*$", expanded))
    messages: list[str] = []
    for index, marker in enumerate(markers):
        if marker.group(1).upper() != label.upper():
            continue
        end = markers[index + 1].start() if index + 1 < len(markers) else len(expanded)
        block = expanded[marker.end() : end]
        for line in [line.strip(" •\t") for line in block.splitlines() if line.strip()]:
            if _is_plausible_status_message(line) and (
                looks_like_quality_advice(line)
                or re.search(r"cutoff|well distributed|Self-correlation|match|above|below|pending|Sharpe|Fitness|Turnover|Drawdown|Margin|novelty|operator", line, re.I)
            ):
                messages.append(line)
    return _dedupe(messages)


def _is_status_heading(line: str, label: str) -> bool:
    return bool(
        re.search(rf"^\s*(?:\[\s*{label}\s*\]|\d+\s+{label}\b|{label}\b)\s*$", line, re.I)
    )


def _is_any_status_heading(line: str) -> bool:
    return bool(
        re.search(r"^\s*(?:\[\s*(?:PASS|FAIL|PENDING)\s*\]|\d+\s+(?:PASS|FAIL|PENDING)\b|(?:PASS|FAIL|PENDING)\b)\s*$", line, re.I)
    )


def looks_like_quality_advice(text: str) -> bool:
    compact = _compact_text(text)
    if not compact:
        return False
    if re.search(r"\b(?:sub[- ]?universe sharpe|turnover|fitness|sharpe|margin)\b.*\b(?:cutoff|above|below|improve|limit)\b", compact, re.I):
        return True
    if re.search(r"\bself[- ]?correlation\b.*\b(?:pending|above|below|match|limit)\b", compact, re.I):
        return True
    if re.search(r"\b(?:novelty|try operators|operator descriptions|detailed operator descriptions|reduce correlation)\b", compact, re.I):
        return True
    if re.search(r"\buse\b.*\b(?:vwap|close|returns|volume|cap)\b.*\bexpression\b", compact, re.I):
        return True
    return looks_like_try_to_use_advice(compact)


def looks_like_try_to_use_advice(text: str) -> bool:
    normalized = _normalize_for_fuzzy(text)
    if not normalized:
        return False
    if len(normalized) > 220:
        return False
    if not re.search(r"\b(?:try|please|recommend|suggest|should|use|using)\b", normalized):
        return False
    if re.search(r"\b(?:simulate|alphas|learn|community|notifications|user menu|simulation \d|code results|submit alpha)\b", normalized):
        return False
    if "bucket" in normalized and "operator" in normalized and ("neutral" in normalized or "custom group" in normalized or "alpha" in normalized):
        return True
    if re.search(r"\btry\s+(?:to\s+)?use\b", normalized) and ("operator" in normalized or "bucket" in normalized):
        return True
    return any(SequenceMatcher(None, normalized, example).ratio() >= 0.72 for example in QUALITY_ADVICE_EXAMPLES)


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _normalize_for_fuzzy(text: str) -> str:
    text = _compact_text(text).lower()
    text = re.sub(r"[\(\)\[\]\{\}\"'`.,:;!?/\\|]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_plausible_status_message(line: str) -> bool:
    compact = _compact_text(line)
    if not compact or len(compact) > 260:
        return False
    if re.search(r"\b(Simulate|Alphas|Competitions|Community|Consultant program|Refer a friend|Notifications|User menu)\b", compact):
        return False
    if re.search(r"\b(Submit Alpha|Check Submission|Add Alpha to a List|Open alpha details|Customize Alpha Details Menu)\b", compact, re.I):
        return False
    return True


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = re.sub(r"\s+", " ", value).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _slice_section(text: str, marker: str, max_chars: int) -> str:
    index = text.lower().find(marker.lower())
    if index < 0:
        return ""
    return text[index : index + max_chars]
