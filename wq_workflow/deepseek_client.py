from __future__ import annotations

import json
import logging
import re
import asyncio
from decimal import Decimal, InvalidOperation
from typing import Any

from .fast_expression import syntax_guidance
from .models import QualityReport, WorkflowConfig


DEEPSEEK_MAX_OUTPUT_TOKENS = 384_000


def build_structured_task_block(context: dict[str, Any] | None) -> str:
    if not context:
        return ""
    allowed = _list_or_default(
        context.get("allowed_structural_mutations") or context.get("allowed_mutations"),
        ["replace_window"],
    )
    forbidden = _list_or_default(context.get("forbidden_mutations"), ["full_rewrite", "new_unknown_operator"])
    metrics = context.get("current_metrics") if isinstance(context.get("current_metrics"), dict) else {}
    complexity = context.get("complexity") if isinstance(context.get("complexity"), dict) else {}
    limit = context.get("complexity_limit") if isinstance(context.get("complexity_limit"), dict) else {}
    ast_summary = context.get("ast_summary") if isinstance(context.get("ast_summary"), dict) else {}
    strategy = str(context.get("current_strategy") or "sharpe_optimization")
    operator_graph = context.get("operator_graph_recommendations") or []
    similarity_threshold = context.get("similarity_threshold", 0.85)
    diversity_requirement = str(
        context.get("diversity_requirement")
        or "Do not generate candidates that converge to the same operator/field structure."
    )
    historical = context.get("historical_successful_mutations") or []
    failures = context.get("recent_failed_patterns") or []
    operator_stats = context.get("operator_statistics") if isinstance(context.get("operator_statistics"), dict) else {}
    research_insights = context.get("research_insights") or ""
    current_expression = str(context.get("current_expression") or "")
    mutation_goal = str(context.get("mutation_goal") or "Improve the alpha with a small controlled mutation.")
    behavior_family = str(context.get("behavior_family") or "")
    behavior_fingerprint = context.get("behavior_fingerprint") if isinstance(context.get("behavior_fingerprint"), dict) else {}
    estimated_self_corr = context.get("estimated_self_corr", "")
    schedule = context.get("mutation_schedule") if isinstance(context.get("mutation_schedule"), dict) else {}

    return f"""
Structured Alpha Optimization Task:
1. Current expression:
{current_expression}

2. Current AST summary:
{json.dumps(ast_summary, ensure_ascii=False, indent=2)}

3. Current behavior context:
- Behavior family: {behavior_family or "legacy"}
- Estimated self-correlation: {estimated_self_corr}
- Behavior fingerprint: {json.dumps(behavior_fingerprint, ensure_ascii=False)}
- V2 mutation schedule: {json.dumps(schedule, ensure_ascii=False)}

4. Current Strategy:
{strategy}

5. Current metrics:
{json.dumps(metrics, ensure_ascii=False, indent=2)}

6. Mutation goal:
{mutation_goal}

7. Allowed Structural Mutations:
{_bullet_lines(allowed)}

8. Forbidden:
{_bullet_lines(forbidden)}

9. Operator Graph Recommendations:
{_bullet_lines([str(item) for item in operator_graph])}

10. Similarity constraints:
- Similarity threshold: {similarity_threshold}
- Reject candidates above the threshold.

11. Complexity limits:
Current complexity: {json.dumps(complexity, ensure_ascii=False)}
Allowed maximum: {json.dumps(limit, ensure_ascii=False)}

12. Recent successful lineages:
{_format_historical_successes(historical, operator_stats)}

13. Recent failed patterns:
{_format_failure_patterns(failures)}

14. Long-term Research Insights:
{_format_research_insights(research_insights)}

15. Diversity requirements:
- {diversity_requirement}

16. Output format constraints:
- Output only one legal WorldQuant Fast Expression.
- Do not output Markdown, explanations, comments, JSON, or extra text.
- Use only the allowed mutation intent; do not freely rewrite the whole alpha.
- Do not invent operators outside the local Fast Expression allowlist.
""".strip()


def build_improve_quality_prompt(code: str, quality: QualityReport, page_text: str, context: dict[str, Any] | None = None) -> str:
    structured = build_structured_task_block(context)
    structured_section = f"\n\n{structured}" if structured else ""
    return f"""
平台回测已经成功，但 IS Summary 或 IS Testing Status 未达标。请根据网页返回的失败项继续优化。
 {worldquant_rules()}
{structured_section}

当前代码：
{code}

IS Summary / IS Testing Status 解析结果：
{json.dumps(quality.to_dict(), ensure_ascii=False, indent=2)}

网页原文片段：
{page_text[-10000:]}

优化重点：
- Fail 项必须逐条处理，例如 Sharpe、Fitness、Sub-universe Sharpe、Turnover、Drawdown、Margin。
- 若 Turnover 过高，增加平滑、延长窗口、降低短期噪声。
- 若 Sharpe/Fitness 不足，温和调整窗口、rank、group_neutralize、scale、winsorize。
- 保留模板核心逻辑，不要大幅换题。
""".strip()


def _list_or_default(value: Any, default: list[str]) -> list[str]:
    if isinstance(value, list):
        result = [str(item) for item in value if str(item).strip()]
        if result:
            return result
    return default


def _bullet_lines(values: list[str]) -> str:
    return "\n".join(f"- {value}" for value in values)


def _format_historical_successes(rows: Any, operator_stats: dict[str, Any]) -> str:
    lines: list[str] = []
    if isinstance(operator_stats, dict):
        for name, stats in sorted(operator_stats.items()):
            if not isinstance(stats, dict):
                continue
            lines.append(
                "- "
                f"{name}: avg_sharpe_gain={stats.get('avg_sharpe_gain', 0)}, "
                f"avg_turnover_reduction={stats.get('avg_turnover_reduction', 0)}, "
                f"success_rate={stats.get('success_rate', 0)}"
            )
    if isinstance(rows, list):
        for row in rows[:5]:
            if not isinstance(row, dict):
                continue
            lines.append(
                "- "
                f"{row.get('mutation_type', 'unknown')}: reward={row.get('reward', 0)}, "
                f"delta={json.dumps(row.get('delta', {}), ensure_ascii=False)}"
            )
    return "\n".join(lines[:8]) if lines else "- No historical successful mutation yet."


def _format_failure_patterns(rows: Any) -> str:
    if not isinstance(rows, list) or not rows:
        return "- No recent failed pattern yet."
    lines: list[str] = []
    for row in rows[:5]:
        if not isinstance(row, dict):
            continue
        root = str(row.get("root_cause") or "")[:180]
        fix = str(row.get("successful_fix") or "")[:120]
        suffix = f"; successful_fix={fix}" if fix else ""
        lines.append(f"- {row.get('error_type', 'unknown')}: {root}{suffix}")
    return "\n".join(lines) if lines else "- No recent failed pattern yet."


def _format_research_insights(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, list):
        lines = [str(item).strip() for item in value if str(item).strip()]
        if lines:
            return "\n".join(lines[:8])
    return "- No long-term research insight distilled yet."


def worldquant_rules() -> str:
    return f"""
WorldQuant Fast Expression 迭代原则：
1. 只输出一个可直接粘贴到 Simulate 编辑器的 Alpha 表达式或少量中间变量加最终表达式。
2. 算子数量尽量控制在 64 以内，减少重复计算。
3. 尽量避免单位不兼容；权重可优先尝试 1、rank(1/cap)、rank(cap) 等无单位形式。
4. 保留模板的核心研究思路，优先做参数、窗口、中性化、平滑、rank、winsorize、scale 等温和修正。
5. 不输出 Markdown 代码块，不输出解释，不执行 Submit。
6. 不保留占位符，例如 {{data}}、<field>、your_data、DATA_PLACEHOLDER；替换为真实字段。可优先考虑常见字段 close、open、high、low、volume、cap、returns、vwap 以及 sector/industry/subindustry 分组。
7. 必须遵守当前 Fast Expression 语法包；不要使用语法包标记为禁用、未知或高风险的算子。
8. 对 vec_*、bucket、group_neutralize、group_mean 等调用，优先参考语法包和平台返回的真实错误修复。
9. 平台若提示 "At least one of buckets, range is required"、"Invalid number of inputs"、单位错误、字段不可用或算子不可用，按该错误精准修复。
10. 中间变量名尽量使用 alpha_signal、ret_signal、cap_bucket、risk_adj 等普通名称，减少和平台算子名混淆。

{syntax_guidance()}
""".strip()


class DeepSeekClient:
    def __init__(self, config: WorkflowConfig) -> None:
        self.config = config
        if not config.deepseek_api_key:
            raise RuntimeError("缺少 DeepSeek API Key，请设置 DEEPSEEK_API_KEY 或 config.json.deepseek.api_key")

    async def _client(self):
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError("缺少 openai 依赖，请运行 pip install openai") from exc
        return AsyncOpenAI(api_key=self.config.deepseek_api_key, base_url=self.config.deepseek_base_url, timeout=120.0)

    async def chat(self, system: str, prompt: str, *, json_mode: bool = False, max_tokens: int | None = None) -> str:
        client = await self._client()
        kwargs: dict[str, Any] = {
            "model": self.config.deepseek_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.config.deepseek_temperature,
            "max_tokens": DEEPSEEK_MAX_OUTPUT_TOKENS,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = None
            for attempt in range(2):
                try:
                    response = await client.chat.completions.create(**kwargs)
                    break
                except Exception:
                    if json_mode and kwargs.get("response_format"):
                        kwargs.pop("response_format", None)
                        response = await client.chat.completions.create(**kwargs)
                        break
                    if attempt >= 1:
                        raise
                    await asyncio.sleep(2 ** attempt)
        finally:
            close = getattr(client, "close", None)
            if close is not None:
                await close()
        if response is None:
            raise RuntimeError("DeepSeek returned empty response")
        choices = getattr(response, "choices", None)
        if not choices:
            raise RuntimeError("DeepSeek returned no choices")
        choice = choices[0]
        message = getattr(choice, "message", None)
        if message is None:
            raise RuntimeError("DeepSeek returned choice without message")
        content = (choice.message.content or "").strip()
        logging.info("DeepSeek 返回：finish_reason=%s content_chars=%s", choice.finish_reason, len(content))
        return content

    async def split_templates(self, raw_text: str, max_count: int | None) -> list[dict[str, str]]:
        limit_text = "全部可用模板" if max_count is None else f"最多返回 {max_count} 个"
        prompt = f"""
请从用户给出的混合文本中筛出所有可用的 WorldQuant Fast Expression Alpha 模板，并逐个分割。
文本可能包含解释、标题、中文说明、多个模板、Markdown 代码块或普通段落。

要求：
- 由你完成模板筛分、清洗和取舍；本地收到 JSON 后不会再做质量、语法或重复率筛选。
- 保留你认为应进入后续 Alpha 准备流程的表达式代码。
- 可以自动补齐明显缺失的行连接和分号，但不要凭空创造新因子。
- 删除解释文字、标题、编号和明显不是模板的普通说明。
- {limit_text}。
- 输出 JSON，格式为：
{{"templates":[{{"name":"template_001","code":"...","reason":"保留原因"}}]}}

用户文本：
{raw_text}
""".strip()
        raw = await self.chat(
            "你是 WorldQuant Fast Expression 模板清洗器。必须只输出紧凑 JSON，不输出解释。",
            prompt,
            json_mode=True,
        )
        data = _safe_json(raw)
        templates = data.get("templates", []) if isinstance(data, dict) else []
        result: list[dict[str, str]] = []
        for index, item in enumerate(templates, start=1):
            if not isinstance(item, dict):
                continue
            code = clean_code(str(item.get("code", "")))
            if not code:
                continue
            result.append(
                {
                    "name": str(item.get("name") or f"template_{index:03d}"),
                    "code": code,
                    "reason": str(item.get("reason", "")),
                }
            )
        return result

    async def prepare_alpha(self, template_code: str) -> tuple[str, str]:
        prompt = f"""
请把以下模板整理成一个可直接在 WorldQuant Brain Simulate 运行的 Alpha 因子。

{worldquant_rules()}

模板：
{template_code}
""".strip()
        raw = await self.chat("你只输出 Fast Expression 代码本体。不要解释，第一行直接给代码。", prompt, max_tokens=8000)
        return clean_code(raw), raw

    async def repair_platform_error(
        self,
        code: str,
        error_text: str,
        page_text: str,
        mutation_context: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        structured = build_structured_task_block(mutation_context)
        structured_section = f"\n\n{structured}" if structured else ""
        rules = worldquant_rules()
        prompt = f"""
平台回测返回错误。请根据错误修复代码，并返回可运行的 Fast Expression 代码。

{worldquant_rules()}

当前代码：
{code}

平台错误：
{error_text}

页面上下文摘要：
{page_text[-6000:]}
""".strip()
        raw = await self.chat("你是 WorldQuant 表达式修复器，只输出修复后的代码。第一行直接给代码。", prompt, max_tokens=8000)
        return clean_code(raw), raw

    async def improve_quality(self, code: str, quality: QualityReport, page_text: str) -> tuple[str, str]:
        prompt = f"""
平台回测已成功，但 IS Summary 或 IS Testing Status 未达标。请根据网页返回的失败项继续优化。

{worldquant_rules()}

当前代码：
{code}

IS Summary / IS Testing Status 解析结果：
{json.dumps(quality.to_dict(), ensure_ascii=False, indent=2)}

网页原文片段：
{page_text[-10000:]}

优化重点：
- Fail 项必须逐条处理，例如 Sharpe、Fitness、Sub-universe Sharpe、Turnover、Drawdown、Margin。
- 若 Turnover 过高，增加平滑、延长窗口、降低短期噪声。
- 若 Sharpe/Fitness 不足，温和调整窗口、rank、group_neutralize、scale、winsorize。
- 保留模板核心逻辑，不要大幅换题。
""".strip()
        raw = await self.chat("你是 WorldQuant Alpha 质量迭代器，只输出优化后的代码。第一行直接给代码。", prompt, max_tokens=10000)
        return clean_code(raw), raw

    async def avoid_correlation(self, code: str, reason: str) -> tuple[str, str]:
        prompt = f"""
本地强制自相关红线阻断了当前因子。请在保留核心思路的前提下做结构差异化修改。

{worldquant_rules()}

当前代码：
{code}

自相关阻断原因：
{reason}

要求：调整窗口、归一化、中性化层级或权重构造，使字符和结构相似度下降。
""".strip()
        raw = await self.chat("你只输出差异化后的 Fast Expression 代码。第一行直接给代码。", prompt, max_tokens=8000)
        return clean_code(raw), raw


async def _structured_repair_platform_error(
    self: DeepSeekClient,
    code: str,
    error_text: str,
    page_text: str,
    mutation_context: dict[str, Any] | None = None,
) -> tuple[str, str]:
    structured = build_structured_task_block(mutation_context)
    structured_section = f"\n\n{structured}" if structured else ""
    prompt = f"""
WorldQuant platform returned an error. Repair the expression with the smallest legal change.
{worldquant_rules()}
{structured_section}

Current expression:
{code}

Platform/local error:
{error_text}

Page context:
{page_text[-6000:]}
""".strip()
    raw = await self.chat(
        "You are a WorldQuant Fast Expression repair engine. Output only the repaired expression.",
        prompt,
        max_tokens=8000,
    )
    return clean_code(raw), raw


async def _structured_improve_quality(
    self: DeepSeekClient,
    code: str,
    quality: QualityReport,
    page_text: str,
    mutation_context: dict[str, Any] | None = None,
) -> tuple[str, str]:
    prompt = build_improve_quality_prompt(code, quality, page_text, mutation_context)
    raw = await self.chat(
        "You are a WorldQuant Alpha quality optimizer. Output only the optimized Fast Expression.",
        prompt,
        max_tokens=10000,
    )
    return clean_code(raw), raw


DeepSeekClient.repair_platform_error = _structured_repair_platform_error
DeepSeekClient.improve_quality = _structured_improve_quality


def clean_code(raw_text: str) -> str:
    text = raw_text.strip()
    fenced = re.search(r"```(?:python|text|fast.?expression|code)?\s*(.*?)```", text, re.I | re.S)
    if fenced:
        text = fenced.group(1).strip()
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("```"):
            continue
        if re.match(r"^(explanation|note|说明|解释|建议)\s*[:：]", stripped, re.I):
            break
        lines.append(line.rstrip())
    return normalize_fast_expression_code("\n".join(lines).strip())


def normalize_fast_expression_code(code: str) -> str:
    return re.sub(r"\b\d+(?:\.\d+)?e[+-]?\d+\b", _decimal_notation, code, flags=re.I)


def _decimal_notation(match: re.Match[str]) -> str:
    try:
        value = Decimal(match.group(0))
    except InvalidOperation:
        return match.group(0)
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _safe_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            logging.warning("DeepSeek 未返回 JSON：%s", text[:500])
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            logging.warning("DeepSeek JSON 解析失败：%s", text[:500])
            return {}
