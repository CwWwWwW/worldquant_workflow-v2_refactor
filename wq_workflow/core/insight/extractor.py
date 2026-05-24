from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from ...paths import ROOT
from ...safe_io import finite_float, safe_read_json
from ...v2_engine import build_behavior_fingerprint
from ..ast import walk
from ..parser import ExpressionParser, ParseError
from .models import ResearchSample


SAFE_FIELD_PATTERN = re.compile(
    r"\b(?:cap|close|high|industry|low|market|open|returns|sector|subindustry|volume|vwap|adv20|exchange)\b",
    re.I,
)
OPERATOR_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
GROUP_FIELDS = {"industry", "sector", "subindustry", "market", "exchange"}


class InsightExtractor:
    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else ROOT
        self.alpha_lineage_file = self.root / "memory" / "evolution" / "alpha_lineage.json"
        self.candidate_pool_file = self.root / "memory" / "evolution" / "candidate_pool.json"
        self.survival_memory_file = self.root / "memory" / "evolution" / "survival_memory.json"
        self.pending_rewards_file = self.root / "memory" / "evolution" / "pending_rewards.json"
        self.template_stats_file = self.root / "memory" / "evolution" / "template_stats.json"
        self.operator_statistics_file = self.root / "memory" / "statistics" / "operator_statistics.json"
        self.failure_patterns_file = self.root / "memory" / "failure_patterns" / "failures.json"
        self.iteration_log_file = self.root / "iteration_log.csv"

    def extract_all(self) -> list[ResearchSample]:
        survival = self._survival_map()
        samples: list[ResearchSample] = []
        samples.extend(self._lineage_samples(survival))
        samples.extend(self._candidate_samples(survival))
        samples.extend(self._failure_samples(survival))
        samples.extend(self._iteration_samples(survival))

        # Read compatibility-only sources so corrupt legacy files cannot surprise
        # the distillation path later. They currently enrich future versions.
        self._read_compat(self.pending_rewards_file, {})
        self._read_compat(self.template_stats_file, {})
        self._read_compat(self.operator_statistics_file, {})

        deduped: dict[str, ResearchSample] = {}
        for sample in samples:
            if not sample.expression:
                continue
            deduped.setdefault(sample.sample_id, sample)
        return sorted(deduped.values(), key=lambda item: (item.source_round, item.timestamp, item.sample_id))

    def _lineage_samples(self, survival: dict[str, dict[str, Any]]) -> list[ResearchSample]:
        rows = self._read_list(self.alpha_lineage_file)
        result: list[ResearchSample] = []
        for index, row in enumerate(rows, start=1):
            expression = str(row.get("expression_after") or row.get("expression") or "")
            alpha_id = str(row.get("alpha_id") or f"lineage:{index}")
            metrics = _metrics(row.get("metrics_after") if isinstance(row.get("metrics_after"), dict) else row.get("metrics"))
            failure_text = str(row.get("failure_reason") or row.get("root_cause") or "")
            result.append(
                self._sample(
                    source="lineage",
                    alpha_id=alpha_id,
                    expression=expression,
                    metrics=metrics,
                    reward=finite_float(row.get("reward")),
                    passed=bool(row.get("passed")),
                    quality_passed=bool(row.get("quality_passed")),
                    failure_type=str(row.get("failure_type") or _classify_failure(failure_text)),
                    family=str(row.get("behavior_family") or ""),
                    survival=survival,
                    estimated_self_corr=finite_float(row.get("estimated_self_corr")),
                    source_round=_source_round(alpha_id, index),
                    timestamp=str(row.get("timestamp") or ""),
                )
            )
        return result

    def _candidate_samples(self, survival: dict[str, dict[str, Any]]) -> list[ResearchSample]:
        rows = self._read_list(self.candidate_pool_file)
        result: list[ResearchSample] = []
        for index, row in enumerate(rows, start=1):
            expression = str(row.get("expression") or row.get("code") or "")
            alpha_id = str(row.get("alpha_id") or f"candidate:{index}")
            result.append(
                self._sample(
                    source="candidate",
                    alpha_id=alpha_id,
                    expression=expression,
                    metrics=_metrics(row.get("metrics")),
                    reward=finite_float(row.get("reward") or row.get("effective_reward")),
                    passed=bool(row.get("passed") or row.get("template_success")),
                    quality_passed=bool(row.get("quality_passed")),
                    failure_type=str(row.get("failure_type") or ""),
                    family=str(row.get("behavior_family") or ""),
                    survival=survival,
                    estimated_self_corr=finite_float(row.get("estimated_self_corr")),
                    source_round=_source_round(alpha_id, index),
                    timestamp=str(row.get("timestamp") or ""),
                )
            )
        return result

    def _failure_samples(self, survival: dict[str, dict[str, Any]]) -> list[ResearchSample]:
        rows = self._read_list(self.failure_patterns_file)
        result: list[ResearchSample] = []
        for index, row in enumerate(rows, start=1):
            expression = str(row.get("expression") or row.get("code") or "")
            alpha_id = str(row.get("alpha_id") or f"failure:{index}")
            failure_type = str(row.get("error_type") or _classify_failure(str(row.get("root_cause") or "")))
            result.append(
                self._sample(
                    source="failure",
                    alpha_id=alpha_id,
                    expression=expression,
                    metrics={},
                    reward=-0.2,
                    passed=False,
                    quality_passed=False,
                    failure_type=failure_type,
                    family="",
                    survival=survival,
                    estimated_self_corr=0.0,
                    source_round=_source_round(alpha_id, index),
                    timestamp=str(row.get("timestamp") or ""),
                )
            )
        return result

    def _iteration_samples(self, survival: dict[str, dict[str, Any]]) -> list[ResearchSample]:
        rows = self._read_csv(self.iteration_log_file)
        result: list[ResearchSample] = []
        for index, row in enumerate(rows, start=1):
            expression = str(row.get("code") or "")
            alpha_name = str(row.get("alpha_name") or "iteration")
            iteration = _int(row.get("iteration"), index)
            alpha_id = f"{alpha_name}:{iteration}:iteration"
            quality = _json_dict(row.get("quality_json"))
            metrics = _json_dict(row.get("metrics_json"))
            platform_error = str(row.get("platform_error") or "")
            result.append(
                self._sample(
                    source="iteration_log",
                    alpha_id=alpha_id,
                    expression=expression,
                    metrics=_metrics(metrics),
                    reward=0.0,
                    passed=str(row.get("stage") or "").lower() in {"platform_result", "favorite", "success"},
                    quality_passed=bool(quality.get("passed")),
                    failure_type=_classify_failure(platform_error),
                    family=str(row.get("behavior_family") or ""),
                    survival=survival,
                    estimated_self_corr=finite_float(row.get("estimated_self_corr")),
                    source_round=iteration,
                    timestamp=str(row.get("time") or ""),
                )
            )
        return result

    def _sample(
        self,
        *,
        source: str,
        alpha_id: str,
        expression: str,
        metrics: dict[str, float],
        reward: float,
        passed: bool,
        quality_passed: bool,
        failure_type: str,
        family: str,
        survival: dict[str, dict[str, Any]],
        estimated_self_corr: float,
        source_round: int,
        timestamp: str,
    ) -> ResearchSample:
        operators, fields, windows = _expression_features(expression)
        fingerprint = build_behavior_fingerprint(expression) if expression else {"family": "legacy"}
        final_family = family or str(fingerprint.get("family") or "legacy")
        return ResearchSample(
            sample_id=_sample_id(source, alpha_id, expression, timestamp),
            alpha_id=alpha_id,
            expression=expression,
            operators=operators,
            fields=fields,
            windows=windows,
            metrics=metrics,
            reward=finite_float(reward),
            passed=bool(passed),
            quality_passed=bool(quality_passed),
            failure_type=failure_type if failure_type != "unknown" else "",
            family=final_family or "legacy",
            survival_rounds=_survival_rounds(alpha_id, survival),
            estimated_self_corr=finite_float(estimated_self_corr),
            source_round=max(0, int(source_round)),
            timestamp=timestamp,
        )

    def _survival_map(self) -> dict[str, dict[str, Any]]:
        data = self._read_compat(self.survival_memory_file, {})
        if isinstance(data, list):
            return {str(row.get("alpha_id") or index): row for index, row in enumerate(data) if isinstance(row, dict)}
        if isinstance(data, dict):
            return {str(key): value for key, value in data.items() if isinstance(value, dict)}
        return {}

    def _read_list(self, path: Path) -> list[dict[str, Any]]:
        data = self._read_compat(path, [])
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            return [value for value in data.values() if isinstance(value, dict)]
        return []

    def _read_compat(self, path: Path, default: Any) -> Any:
        try:
            data = safe_read_json(path, default)
        except OSError:
            return default
        if isinstance(data, dict) and "data" in data and isinstance(data.get("data"), (dict, list)):
            return data["data"]
        return data

    def _read_csv(self, path: Path) -> list[dict[str, str]]:
        if not path.exists():
            return []
        try:
            with path.open("r", newline="", encoding="utf-8-sig", errors="replace") as fh:
                return list(csv.DictReader(fh))
        except OSError:
            return []


def _expression_features(expression: str) -> tuple[list[str], list[str], list[int]]:
    try:
        ast = ExpressionParser().parse(expression)
        operators = [node.name.lower() for node in walk(ast) if node.type == "operator"]
        fields = [node.name.lower() for node in walk(ast) if node.type == "field"]
        windows: list[int] = []
        for node in walk(ast):
            if node.type != "operator":
                continue
            value = node.parameters.get("window")
            if isinstance(value, int):
                windows.append(value)
            for child in node.children:
                if child.type == "number":
                    number = finite_float(child.value)
                    if number.is_integer() and number >= 2:
                        windows.append(int(number))
        return _unique(operators), _unique(fields), sorted(set(windows))
    except (ParseError, ValueError, RecursionError):
        operators = [item.lower() for item in OPERATOR_PATTERN.findall(expression or "")]
        fields = [item.lower() for item in SAFE_FIELD_PATTERN.findall(expression or "")]
        windows = [int(item) for item in re.findall(r"\b([2-9]\d{0,2})\b", expression or "")]
        return _unique(operators), _unique(fields), sorted(set(windows))


def _sample_id(source: str, alpha_id: str, expression: str, timestamp: str) -> str:
    digest = hashlib.sha1(f"{source}|{alpha_id}|{expression}|{timestamp}".encode("utf-8", errors="ignore")).hexdigest()
    return digest[:16]


def _source_round(alpha_id: str, fallback: int) -> int:
    matches = re.findall(r":(\d+)(?::|$)", alpha_id or "")
    if matches:
        return _int(matches[-1], fallback)
    return fallback


def _survival_rounds(alpha_id: str, survival: dict[str, dict[str, Any]]) -> int:
    candidates = [alpha_id]
    if ":" in alpha_id:
        candidates.append(alpha_id.rsplit(":", 1)[0])
    for candidate in candidates:
        record = survival.get(candidate)
        if isinstance(record, dict):
            return max(0, _int(record.get("survival_rounds")))
    return 0


def _metrics(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    return {str(key): finite_float(item) for key, item in value.items()}


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _classify_failure(text: str) -> str:
    lowered = (text or "").lower()
    if not lowered:
        return ""
    if "unit" in lowered:
        return "unit mismatch"
    if "group" in lowered or "bucket" in lowered:
        return "invalid group"
    if "operator" in lowered or "invalid number of inputs" in lowered:
        return "operator misuse"
    if "nan" in lowered:
        return "NaN explosion"
    if "turnover" in lowered:
        return "high turnover"
    if "fitness" in lowered:
        return "low fitness"
    if "unstable" in lowered or "sharpe" in lowered:
        return "unstable signal"
    return "operator misuse"


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result
