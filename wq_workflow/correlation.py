from __future__ import annotations

import difflib
import hashlib
import json
import logging
import re
from datetime import datetime
from typing import Any

from .core.parser import ExpressionParser, ParseError
from .core.semantic_similarity import SemanticSimilarity, operator_sequence, semantic_signature
from .models import CorrelationResult
from .paths import CORRELATION_LOG_FILE, LOCAL_LIBRARY_FIELDS, LOCAL_LIBRARY_FILE, append_csv, read_csv
from .platform_sc import apply_correlation_quality, sc_payload_from_metrics
from .v2_engine import build_behavior_fingerprint, estimate_self_corr


CHAR_THRESHOLD = 0.45
LEGACY_STRUCTURE_THRESHOLD = 0.60
LEGACY_SEMANTIC_THRESHOLD = 0.65
STRUCTURE_THRESHOLD = 0.78
SEMANTIC_THRESHOLD = 0.80
BEHAVIOR_THRESHOLD = 0.72


def md5_text(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def normalize_code(code: str) -> str:
    lines = []
    for raw in code.splitlines():
        line = raw.split("#", 1)[0].strip().lower()
        if line:
            lines.append(re.sub(r"\s+", "", line))
    return "\n".join(lines)


def extract_structure(code: str) -> dict[str, Any]:
    try:
        ast = ExpressionParser().parse(code)
    except ParseError:
        functions = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", code)
        functions = [item for item in functions if item not in {"if", "for", "while", "return"}]
        windows = re.findall(r"\b(?:ts_[A-Za-z_]+|delay|delta)\s*\([^)]*,\s*(\d+)", code)
        groups = sorted(set(re.findall(r"\b(industry|sector|subindustry|market|exchange|cap|size)\b", code, re.I)))
        return {"functions": functions, "windows": windows, "groups": groups, "ast_parseable": False}
    signature = semantic_signature(ast)
    windows = re.findall(r"\b(?:ts_[A-Za-z_]+|delay|delta)\s*\([^)]*,\s*(\d+)", code)
    groups = sorted(set(re.findall(r"\b(industry|sector|subindustry|market|exchange|cap|size)\b", code, re.I)))
    return {
        "functions": operator_sequence(ast),
        "windows": windows,
        "groups": groups,
        "semantic_signature": signature,
        "ast_parseable": True,
    }


def sequence_overlap(left: list[str], right: list[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return difflib.SequenceMatcher(None, left, right).ratio()


def structure_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    lf = [str(item).lower() for item in left.get("functions", [])]
    rf = [str(item).lower() for item in right.get("functions", [])]
    lw = [str(item) for item in left.get("windows", [])]
    rw = [str(item) for item in right.get("windows", [])]
    lg = [str(item).lower() for item in left.get("groups", [])]
    rg = [str(item).lower() for item in right.get("groups", [])]
    return round(sequence_overlap(lf, rf) * 0.65 + sequence_overlap(lw, rw) * 0.2 + sequence_overlap(lg, rg) * 0.15, 6)


def log_correlation(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    with CORRELATION_LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    logging.info("[SelfCorrelation] %s", message)


def check_self_correlation(
    current_code: str,
    current_structure: dict[str, Any],
    *,
    metrics: dict[str, float] | None = None,
    enable_v2_engine: bool = True,
    enable_behavior_sc_pipeline: bool = True,
) -> CorrelationResult:
    assert current_code is not None and current_structure is not None, "self-correlation check must be explicit"
    rows = read_csv(LOCAL_LIBRARY_FILE)
    current_hash = md5_text(current_code)
    current_norm = normalize_code(current_code)
    current_struct = current_structure or extract_structure(current_code)
    parser = ExpressionParser()
    semantic = SemanticSimilarity(duplicate_threshold=SEMANTIC_THRESHOLD if enable_v2_engine else LEGACY_SEMANTIC_THRESHOLD)
    try:
        current_ast = parser.parse(current_code)
    except ParseError:
        current_ast = None
    details: list[dict[str, Any]] = []

    if not rows:
        log_correlation("local_library_empty result=pass")
        return CorrelationResult(True, "local library empty", details)

    for row in rows:
        alpha_id = row.get("alpha_id", "")
        code = row.get("code", "")
        lib_hash = row.get("md5", "")
        if lib_hash == current_hash:
            reason = f"MD5 duplicate alpha: {alpha_id}"
            log_correlation(f"alpha_id={alpha_id} md5_duplicate result=reject")
            return CorrelationResult(False, reason, details)

        char_ratio = difflib.SequenceMatcher(None, current_norm, normalize_code(code)).ratio()
        detail = {"alpha_id": alpha_id, "char_ratio": round(char_ratio, 6)}
        if not enable_v2_engine and char_ratio > CHAR_THRESHOLD:
            reason = f"character overlap {char_ratio:.2%} > 45%: {alpha_id}"
            log_correlation(f"alpha_id={alpha_id} char_ratio={char_ratio:.6f} result=reject")
            details.append(detail)
            return CorrelationResult(False, reason, details)

        lib_structure = _safe_json(row.get("core_structure", "")) or extract_structure(code)
        struct_ratio = structure_similarity(current_struct, lib_structure)
        detail["structure_ratio"] = struct_ratio
        details.append(detail)
        if not enable_v2_engine and struct_ratio > LEGACY_STRUCTURE_THRESHOLD:
            reason = f"structure similarity {struct_ratio:.2%} > 60%: {alpha_id}"
            log_correlation(f"alpha_id={alpha_id} structure_ratio={struct_ratio:.6f} result=reject")
            return CorrelationResult(False, reason, details)

        if current_ast is not None:
            try:
                lib_ast = parser.parse(code)
            except ParseError:
                lib_ast = None
            if lib_ast is not None:
                semantic_ratio = semantic.similarity(current_ast, lib_ast)
                detail["semantic_ratio"] = semantic_ratio
                if not enable_v2_engine and semantic_ratio > LEGACY_SEMANTIC_THRESHOLD:
                    reason = f"semantic similarity {semantic_ratio:.2%} > 65%: {alpha_id}"
                    log_correlation(f"alpha_id={alpha_id} semantic_ratio={semantic_ratio:.6f} result=reject")
                    return CorrelationResult(False, reason, details)

        log_correlation(f"alpha_id={alpha_id} char_ratio={char_ratio:.6f} structure_ratio={struct_ratio:.6f} result=pass")

    if enable_v2_engine and enable_behavior_sc_pipeline:
        estimate = estimate_self_corr(current_code, rows, metrics=metrics)
        estimated = float(estimate.get("estimated_self_corr") or 0.0)
        behavior = float(estimate.get("max_behavior_similarity") or 0.0)
        limit = float(estimate.get("similarity_limit") or 0.75)
        details.append(
            {
                "alpha_id": estimate.get("nearest_alpha_id", ""),
                "estimated_self_corr": estimated,
                "behavior_ratio": behavior,
                "final_similarity": estimate.get("max_final_similarity", 0.0),
                "similarity_limit": limit,
                "behavior_family": estimate.get("behavior_family", "legacy"),
            }
        )
        if behavior > BEHAVIOR_THRESHOLD and estimated > limit:
            reason = f"V2 behavior self-correlation proxy {estimated:.2%} > {limit:.2%}: {estimate.get('nearest_alpha_id', '')}"
            log_correlation(f"v2_estimated_self_corr={estimated:.6f} behavior={behavior:.6f} result=reject")
            return CorrelationResult(False, reason, details)
    return CorrelationResult(True, "passed local multi-layer self-correlation check", details)


def append_alpha_library(
    alpha_id: str,
    code: str,
    structure: dict[str, Any],
    metrics: dict[str, float],
    *,
    enable_v2_engine: bool = True,
    enable_behavior_sc_pipeline: bool = True,
    platform_sc: dict[str, Any] | None = None,
) -> None:
    fingerprint = build_behavior_fingerprint(code) if enable_v2_engine else {}
    metrics_payload = apply_correlation_quality(metrics if isinstance(metrics, dict) else {})
    estimate = (
        estimate_self_corr(code, read_csv(LOCAL_LIBRARY_FILE), metrics=metrics_payload)
        if enable_behavior_sc_pipeline
        else {}
    )
    if "estimated_self_corr" not in metrics_payload and estimate:
        try:
            metrics_payload["estimated_self_corr"] = float(estimate.get("estimated_self_corr") or 0.0)
        except (TypeError, ValueError):
            pass
        metrics_payload = apply_correlation_quality(metrics_payload)
    sc_payload = sc_payload_from_metrics(metrics_payload, platform_sc)
    platform_sc_json = json.dumps(platform_sc, ensure_ascii=False, default=str) if isinstance(platform_sc, dict) else ""
    append_csv(
        LOCAL_LIBRARY_FILE,
        LOCAL_LIBRARY_FIELDS,
        {
            "alpha_id": alpha_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "md5": md5_text(code),
            "code": code,
            "core_structure": json.dumps(structure, ensure_ascii=False),
            "metrics": json.dumps(metrics_payload, ensure_ascii=False),
            "returns_path": "",
            "behavior_family": fingerprint.get("family", "") if fingerprint else "",
            "behavior_fingerprint": json.dumps(fingerprint, ensure_ascii=False) if fingerprint else "",
            "estimated_self_corr": estimate.get("estimated_self_corr", metrics_payload.get("estimated_self_corr", ""))
            if estimate
            else metrics_payload.get("estimated_self_corr", ""),
            "platform_sc_status": sc_payload.get("platform_sc_status", ""),
            "platform_sc_max": sc_payload.get("platform_sc_max", ""),
            "platform_sc_min": sc_payload.get("platform_sc_min", ""),
            "platform_sc_abs_max": sc_payload.get("platform_sc_abs_max", ""),
            "real_self_corr": sc_payload.get("real_self_corr", ""),
            "sc_source": sc_payload.get("sc_source", ""),
            "correlation_quality": sc_payload.get("correlation_quality", ""),
            "submission_quality": sc_payload.get("submission_quality", ""),
            "platform_sc_json": platform_sc_json,
        },
    )


def _safe_json(text: str) -> Any:
    try:
        return json.loads(text) if text else None
    except json.JSONDecodeError:
        return None
