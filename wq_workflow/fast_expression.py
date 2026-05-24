from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from .models import BASE_URL
from .paths import LOG_DIR


OPERATOR_CACHE_FILE = LOG_DIR / "fast_expression_operator_cache.json"
OPERATOR_DOC_URLS = [
    f"{BASE_URL}/learn/data-and-operators/detailed-operator-descriptions",
    f"{BASE_URL}/learn/data-and-operators/operators",
    f"{BASE_URL}/learn",
]

KNOWN_UNAVAILABLE_OPERATORS = {
    "delay",
    "floor",
    "group_bucket",
    "group_median",
    "group_min",
    "group_normalize",
    "group_quantile",
    "group_residual",
    "int",
    "neutralize",
    "pow",
    "regression",
    "regression_neut",
    "regression_neutralize",
    "ts_ir",
    "ts_entropy",
    "ts_information_ratio",
    "ts_max",
    "ts_min",
    "ts_std",
    "ts_stddev",
    "ts_winsorize",
}

RESERVED_ASSIGNMENT_NAMES = KNOWN_UNAVAILABLE_OPERATORS | {
    "alpha",
    "bucket",
    "densify",
    "group",
    "group_mean",
    "group_neutralize",
    "group_rank",
    "group_zscore",
    "hump",
    "rank",
    "scale",
    "trade_when",
    "ts_backfill",
    "ts_decay_exp_window",
    "ts_delta",
    "ts_mean",
    "ts_rank",
    "ts_scale",
    "ts_std_dev",
    "ts_zscore",
    "vec_avg",
    "vec_count",
    "winsorize",
}

OPERATOR_ARITY = {
    "abs": (1, 1),
    "bucket": (2, 2),
    "densify": (1, 1),
    "group_mean": (3, 3),
    "group_neutralize": (2, 2),
    "group_rank": (2, 2),
    "group_zscore": (2, 2),
    "hump": (1, 2),
    "inverse": (1, 1),
    "log": (1, 1),
    "rank": (1, 1),
    "scale": (1, 1),
    "signed_power": (2, 2),
    "sign": (1, 1),
    "trade_when": (3, 3),
    "ts_backfill": (2, 2),
    "ts_corr": (3, 3),
    "ts_count_nans": (2, 2),
    "ts_decay_exp_window": (2, 3),
    "ts_delta": (2, 2),
    "ts_mean": (2, 2),
    "ts_product": (2, 2),
    "ts_rank": (2, 2),
    "ts_scale": (2, 2),
    "ts_std_dev": (2, 2),
    "ts_sum": (2, 2),
    "ts_zscore": (2, 2),
    "vec_avg": (1, 1),
    "vec_count": (1, 1),
    "winsorize": (1, 2),
}

SAFE_FIELDS = {
    "cap",
    "close",
    "high",
    "industry",
    "low",
    "market",
    "open",
    "returns",
    "sector",
    "subindustry",
    "volume",
    "vwap",
    "adv20",
    "exchange",
}


def syntax_guidance() -> str:
    cached = _read_operator_cache_summary()
    if cached:
        return cached
    unavailable = ", ".join(sorted(KNOWN_UNAVAILABLE_OPERATORS))
    signatures = ", ".join(f"{name}/{limits[0]}" for name, limits in sorted(OPERATOR_ARITY.items()) if limits[0] == limits[1])
    fields = ", ".join(sorted(SAFE_FIELDS))
    return f"""
Fast Expression 语法约束（本地保守规则，优先避免平台已反复拒绝的写法）：
- 只使用已确认常见字段或用户模板中的真实字段；常见字段：{fields}。
- 已知当前平台不可用或高风险算子，禁止使用：{unavailable}。
- 常用算子参数个数：{signatures}。
- group_mean 必须写成 group_mean(x, weight, group)，例如 group_mean(returns, 1, sector)。
- group_neutralize/group_rank/group_zscore 通常只接受 (x, group) 两个参数；第三个 "mean" 或 1 不要传。
- bucket 通常写成 bucket(rank(cap), range="0.1,1,0.1")；不要写 bucket(rank(cap), range = 10)。
- 不要把 trade_when、rank、bucket、group_*、ts_*、vec_* 等算子名当变量名赋值。
- 不要输出占位符、Markdown、解释文本或未闭合括号；最后一行必须是表达式。
""".strip()


async def refresh_operator_cache_from_platform(page) -> None:
    """Best-effort cache refresh from the logged-in BRAIN Learn pages."""
    try:
        for url in OPERATOR_DOC_URLS:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_selector("body", state="visible", timeout=15000)
                text = await page.locator("body").inner_text(timeout=15000)
            except Exception as exc:
                logging.info("Fast Expression 官方语法页读取失败，尝试下一个：%s error=%s", url, exc)
                continue
            summary = summarize_operator_page(text)
            if summary:
                OPERATOR_CACHE_FILE.write_text(
                    json.dumps(
                        {
                            "source": url,
                            "updated_at": datetime.now().isoformat(timespec="seconds"),
                            "summary": summary,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                logging.info("Fast Expression 官方语法缓存已刷新：%s", OPERATOR_CACHE_FILE)
                return
    except Exception as exc:
        logging.info("Fast Expression 官方语法缓存刷新失败，继续使用本地保守规则：%s", exc)


def summarize_operator_page(text: str) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if len(compact) < 500 or not re.search(r"\b(operator|operators|expression|syntax)\b", compact, re.I):
        return ""
    operator_lines = []
    for line in (text or "").splitlines():
        stripped = re.sub(r"\s+", " ", line).strip()
        if not stripped:
            continue
        if re.search(r"\b(rank|bucket|group_|ts_|vec_|winsorize|trade_when|decay|neutralize|zscore|scale)\b", stripped, re.I):
            operator_lines.append(stripped)
        if len(operator_lines) >= 120:
            break
    if not operator_lines:
        return ""
    return "\n".join(operator_lines)[:6000]


def validate_fast_expression(code: str, *, enable_v2_engine: bool = True) -> str:
    text = code or ""
    if not text.strip():
        return "代码为空"
    if "{" in text or "}" in text:
        return "代码包含花括号占位符，例如 {data}，WorldQuant Fast Expression 不接受占位符"
    if re.search(r"<\s*(?:field|data|your_data|alpha|expression|template|placeholder|[A-Za-z_][A-Za-z0-9_]*_PLACEHOLDER)\s*>|your_data|DATA_PLACEHOLDER|placeholder", text, re.I):
        return "代码包含未替换的数据占位符"
    if re.search(r"\b\d+(?:\.\d+)?e[+-]?\d+\b", text, re.I):
        return "代码包含科学计数法数字，例如 1e-10；WorldQuant Fast Expression 需要十进制小数写法"
    if text.count("(") != text.count(")"):
        return "代码括号数量不匹配，可能会触发 Unexpected end of input"

    for assignment in re.finditer(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", text):
        name = assignment.group(1)
        if name in RESERVED_ASSIGNMENT_NAMES or name.startswith(("ts_", "group_", "vec_")) or re.fullmatch(r"adv\d+", name, re.I):
            return f"中间变量名 {name} 与算子/保留名前缀冲突，请改成普通变量名如 alpha_signal 或 ret_signal"

    for name, args in iter_function_calls(text):
        lowered = name.lower()
        if lowered == "trade_when" and not enable_v2_engine:
            return "当前自动迭代默认禁止 trade_when，请改成普通信号或乘法 gating，避免平台 exit trigger 错误"
        if lowered in KNOWN_UNAVAILABLE_OPERATORS:
            return f"代码包含平台当前不可用算子：{lowered}，请改用本地语法包中的常用算子"
        if lowered not in OPERATOR_ARITY:
            return f"未知或未批准算子：{lowered}，请只使用本地语法包 allowlist 中的算子"
        if lowered in OPERATOR_ARITY:
            min_args, max_args = OPERATOR_ARITY[lowered]
            parts = split_args(args)
            count = len(parts)
            if count < min_args or count > max_args:
                expected = str(min_args) if min_args == max_args else f"{min_args}-{max_args}"
                return f"{lowered} 参数个数为 {count}，本地语法包要求 {expected} 个"
            if lowered == "group_mean" and count >= 3 and not _safe_group_mean_weight(parts[1]):
                return "group_mean(x, weight, group) 的 weight 不要直接使用 cap/volume/price 等带单位字段，请使用 1、rank(cap) 或 rank(1/cap)"
    if re.search(r"\btrade_when\s*=", text):
        return "trade_when 是平台算子/特殊结构，不要作为变量名赋值"
    if re.search(r"\btrade_when\s*\(", text) and not enable_v2_engine:
        return "当前自动迭代默认禁止 trade_when，请改成普通信号或乘法 gating，避免平台 exit trigger 错误"
    return ""


def iter_function_calls(code: str) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []
    for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", code):
        name = match.group(1)
        args, end = _extract_parenthesized(code, match.end() - 1)
        if end > match.end():
            calls.append((name, args))
    return calls


def split_args(args: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    quote = ""
    for index, char in enumerate(args):
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in {'"', "'"}:
            quote = char
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            part = args[start:index].strip()
            if part:
                parts.append(part)
            start = index + 1
    tail = args[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _extract_parenthesized(text: str, open_index: int) -> tuple[str, int]:
    depth = 0
    quote = ""
    start = open_index + 1
    for index in range(open_index, len(text)):
        char = text[index]
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in {'"', "'"}:
            quote = char
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start:index], index + 1
    return text[start:], len(text)


def _first_call_args(text: str, name: str) -> str:
    match = re.search(rf"\b{re.escape(name)}\s*\(", text)
    if not match:
        return ""
    args, _ = _extract_parenthesized(text, match.end() - 1)
    return args


def _safe_group_mean_weight(arg: str) -> bool:
    compact = re.sub(r"\s+", "", arg or "").lower()
    if compact in {"1", "1.0", "rank(cap)", "rank(1/cap)", "rank(inverse(cap))"}:
        return True
    return bool(re.fullmatch(r"rank\([^)]+\)", compact))


def _read_operator_cache_summary() -> str:
    if not OPERATOR_CACHE_FILE.exists():
        return ""
    try:
        data = json.loads(OPERATOR_CACHE_FILE.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return ""
    summary = str(data.get("summary") or "").strip() if isinstance(data, dict) else ""
    return summary[:6000]
