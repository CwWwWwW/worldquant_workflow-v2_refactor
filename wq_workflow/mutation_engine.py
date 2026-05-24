from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .core.ast import ASTNode, walk
from .core.mutation_constraints import (
    MutationConstraints,
    ast_depth,
    neutralization_layers,
    operator_count,
    parameter_windows,
    ts_operator_count,
)
from .core.operators import OPERATOR_ARITY, SAFE_FIELDS
from .core.parser import ExpressionParser, ParseError
from .core.semantic_similarity import semantic_signature
from .core.strategy_engine import StrategyEngine
from .fast_expression import iter_function_calls, validate_fast_expression
from .safe_io import finite_float


MUTATION_OPERATORS = [
    "change_window",
    "add_decay",
    "add_rank",
    "replace_group",
    "add_neutralization",
    "reduce_turnover",
    "replace_price_source",
    "winsorize_signal",
    "simplify_expression",
    "hump",
    "bucket",
    "rank",
    "replace_signal",
]

DEFAULT_FORBIDDEN_MUTATIONS = ["full_rewrite", "new_unknown_operator"]
LOW_SHARPE_CUTOFF = 0.8
LOW_FITNESS_CUTOFF = 1.0
HIGH_TURNOVER_CUTOFF = 65.0


@dataclass
class MutationPlan:
    allowed_mutations: list[str]
    forbidden_mutations: list[str]
    priority: str
    mutation_goal: str
    complexity_limit: dict[str, int] = field(default_factory=dict)
    allowed_structural_mutations: list[str] = field(default_factory=list)
    current_strategy: str = ""
    ast_summary: dict[str, Any] = field(default_factory=dict)
    operator_graph_recommendations: list[str] = field(default_factory=list)
    similarity_threshold: float = 0.75
    diversity_requirement: str = "Preserve semantic diversity; reject candidates above similarity threshold."
    mutation_weights_hint: dict[str, float] = field(default_factory=dict)

    def primary_mutation(self) -> str:
        if self.allowed_structural_mutations:
            return self.allowed_structural_mutations[0]
        return self.priority or (self.allowed_mutations[0] if self.allowed_mutations else "change_window")

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "allowed_mutations": self.allowed_mutations,
            "forbidden_mutations": self.forbidden_mutations,
            "priority": self.priority,
            "mutation_goal": self.mutation_goal,
            "complexity_limit": self.complexity_limit,
            "allowed_structural_mutations": self.allowed_structural_mutations,
            "current_strategy": self.current_strategy,
            "ast_summary": self.ast_summary,
            "operator_graph_recommendations": self.operator_graph_recommendations,
            "similarity_threshold": self.similarity_threshold,
            "diversity_requirement": self.diversity_requirement,
        }
        if self.mutation_weights_hint:
            payload["mutation_weights_hint"] = self.mutation_weights_hint
        return payload


class MutationPlanner:
    def plan(
        self,
        current_metrics: dict[str, float] | None,
        current_expression: str,
        failure_reason: str = "",
        *,
        weight_hint: dict[str, float] | None = None,
        enable_evolution_policy: bool = False,
    ) -> MutationPlan:
        metrics = current_metrics or {}
        sharpe = _metric(metrics, "sharpe")
        fitness = _metric(metrics, "fitness")
        turnover = normalize_turnover(metrics.get("turnover", 0.0))
        reason = (failure_reason or "").lower()

        allowed: list[str] = []
        forbidden: list[str] = list(DEFAULT_FORBIDDEN_MUTATIONS)
        goal = "Improve the alpha with a small controlled mutation."

        if turnover > HIGH_TURNOVER_CUTOFF or "turnover" in reason:
            allowed.extend(["add_decay", "reduce_turnover", "hump"])
            forbidden.extend(["replace_signal", "replace_price_source", "full_rewrite"])
            goal = "Reduce turnover while preserving the core signal and data fields."
        elif fitness < LOW_FITNESS_CUTOFF and sharpe >= LOW_SHARPE_CUTOFF:
            allowed.extend(["add_neutralization", "bucket", "rank"])
            forbidden.extend(["replace_price_source", "full_rewrite"])
            goal = "Improve fitness using neutralization, bucketing, or ranking without changing the core signal."
        elif sharpe < LOW_SHARPE_CUTOFF or "sharpe" in reason:
            allowed.extend(["simplify_expression", "replace_signal"])
            forbidden.extend(["replace_price_source", "full_rewrite"])
            goal = "Improve Sharpe by simplifying noisy structure or replacing only the weak signal layer."

        if re.search(r"unknown operator|inaccessible|unsupported|invalid number of inputs|operator", reason):
            allowed.extend(["simplify_expression", "replace_group", "change_window"])
            forbidden.extend(["new_unknown_operator", "full_rewrite"])
            goal = "Repair operator misuse with the smallest valid rewrite."
        if re.search(r"unit|vector data|matrix data|scalar data|must be|should be", reason):
            allowed.extend(["simplify_expression", "winsorize_signal", "replace_group"])
            forbidden.extend(["replace_price_source", "full_rewrite"])
            goal = "Repair data type or unit mismatch without broad expression rewrites."
        if re.search(r"invalid group|group_neutralize|bucket", reason):
            allowed.extend(["replace_group", "add_neutralization", "bucket"])
            forbidden.extend(["replace_price_source", "full_rewrite"])
            goal = "Repair group or bucket structure with valid WorldQuant grouping."

        if not allowed:
            allowed.extend(["change_window", "add_rank", "winsorize_signal"])

        allowed = _dedupe_valid_mutations(allowed)
        forbidden = _dedupe_valid_forbidden(forbidden, allowed)
        priority = allowed[0] if allowed else "change_window"
        strategy = StrategyEngine().choose(metrics, [], [])
        return MutationPlan(
            allowed_mutations=allowed,
            forbidden_mutations=forbidden,
            priority=priority,
            mutation_goal=goal,
            complexity_limit=dynamic_complexity_limit(metrics, current_expression),
            allowed_structural_mutations=_structural_mutations_for_allowed(allowed, strategy.allowed_mutations),
            current_strategy=strategy.name.value,
            ast_summary=ast_summary(current_expression),
            operator_graph_recommendations=["No operator graph recommendation yet."],
            similarity_threshold=0.85 if fitness > LOW_FITNESS_CUTOFF else 0.75,
            mutation_weights_hint=_safe_weight_hint(weight_hint) if enable_evolution_policy else {},
        )


def normalize_turnover(value: Any) -> float:
    turnover = finite_float(value)
    if 0 < abs(turnover) <= 1.0:
        return turnover * 100.0
    return turnover


def complexity_score(expression: str) -> dict[str, int]:
    text = expression or ""
    ast = _parse_ast(text)
    if ast:
        windows = parameter_windows(ast)
        return {
            "operator_count": operator_count(ast),
            "nesting_depth": ast_depth(ast),
            "ts_operator_count": ts_operator_count(ast),
            "neutralization_layers": neutralization_layers(ast),
            "window_count": len(windows),
        }
    calls = iter_function_calls(text)
    functions = [name.lower() for name, _args in calls]
    return {
        "operator_count": len(functions),
        "nesting_depth": _nesting_depth(text),
        "ts_operator_count": sum(1 for name in functions if name.startswith("ts_")),
        "neutralization_layers": sum(
            1
            for name in functions
            if name in {"group_neutralize", "group_rank", "group_zscore", "group_mean", "bucket"}
        ),
    }


def dynamic_complexity_limit(metrics: dict[str, float] | None, expression: str) -> dict[str, int]:
    metrics = metrics or {}
    current = complexity_score(expression)
    sharpe = _metric(metrics, "sharpe")
    turnover = normalize_turnover(metrics.get("turnover", 0.0))

    if sharpe < LOW_SHARPE_CUTOFF:
        max_operator_count = min(max(current["operator_count"] + 2, 12), 18)
    else:
        max_operator_count = min(max(current["operator_count"] + 3, 14), 24)

    max_nesting_depth = current["nesting_depth"] + (2 if turnover > HIGH_TURNOVER_CUTOFF else 3)
    return {
        "current_operator_count": current["operator_count"],
        "max_operator_count": max_operator_count,
        "current_nesting_depth": current["nesting_depth"],
        "max_nesting_depth": max_nesting_depth,
        "current_ts_operator_count": current["ts_operator_count"],
        "max_ts_operator_count": current["ts_operator_count"] + 2,
        "current_neutralization_layers": current["neutralization_layers"],
        "max_neutralization_layers": current["neutralization_layers"] + 2,
        "current_expression_length": len(expression or ""),
        "max_expression_length": min(max(len(expression or "") + 220, 400), 900),
    }


def validate_controlled_expression(
    before: str,
    after: str,
    plan: MutationPlan | dict[str, Any],
    *,
    enable_v2_engine: bool = True,
) -> str:
    syntax_error = validate_fast_expression(after, enable_v2_engine=enable_v2_engine)
    if syntax_error:
        return syntax_error

    plan_dict = plan.to_dict() if isinstance(plan, MutationPlan) else plan
    limit = plan_dict.get("complexity_limit", {}) if isinstance(plan_dict, dict) else {}
    complexity = complexity_score(after)
    if complexity["operator_count"] > int(limit.get("max_operator_count", 64)):
        return (
            f"Controlled mutation rejected: operator_count {complexity['operator_count']} "
            f"> {limit.get('max_operator_count')}"
        )
    if complexity["nesting_depth"] > int(limit.get("max_nesting_depth", 64)):
        return (
            f"Controlled mutation rejected: nesting_depth {complexity['nesting_depth']} "
            f"> {limit.get('max_nesting_depth')}"
        )
    if len(after or "") > int(limit.get("max_expression_length", 10000)):
        return "Controlled mutation rejected: expression length exceeds complexity limit"

    after_ast = _parse_ast(after)
    if after_ast:
        constraints = MutationConstraints(
            max_depth=int(limit.get("max_nesting_depth", 64)),
            max_operator_count=int(limit.get("max_operator_count", 64)),
            max_neutralization_layers=int(limit.get("max_neutralization_layers", 4)),
        )
        constraint_result = constraints.validate(after_ast)
        if not constraint_result.passed:
            return "Controlled mutation rejected: " + constraint_result.reason

    forbidden = set(plan_dict.get("forbidden_mutations", [])) if isinstance(plan_dict, dict) else set()
    if "replace_price_source" in forbidden:
        new_fields = expression_fields(after) - expression_fields(before)
        if enable_v2_engine:
            new_fields -= {"adv20", "exchange", "volume", "returns", "cap"}
        if new_fields:
            return "Controlled mutation rejected: new data fields are forbidden: " + ", ".join(sorted(new_fields))

    if "full_rewrite" in forbidden and _looks_like_full_rewrite(before, after):
        return "Controlled mutation rejected: expression appears to rewrite the core structure"

    if after_ast:
        for node in walk(after_ast):
            if node.type == "operator" and node.name.lower() not in OPERATOR_ARITY:
                return f"Controlled mutation rejected: expression operator is outside allowlist: {node.name.lower()}"
            if node.type == "operator" and node.name.lower() == "trade_when" and not enable_v2_engine:
                return "Controlled mutation rejected: trade_when is disabled"
    else:
        for name, _args in iter_function_calls(after):
            if name.lower() not in OPERATOR_ARITY:
                return f"Controlled mutation rejected: expression operator is outside allowlist: {name.lower()}"
            if name.lower() == "trade_when" and not enable_v2_engine:
                return "Controlled mutation rejected: trade_when is disabled"
    return ""


def expression_fields(expression: str) -> set[str]:
    tokens = {match.group(0).lower() for match in re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]*\b", expression or "")}
    return tokens & {field.lower() for field in SAFE_FIELDS}


def _metric(metrics: dict[str, float], key: str) -> float:
    return finite_float(metrics.get(key, 0.0))


def _nesting_depth(text: str) -> int:
    depth = 0
    max_depth = 0
    for char in text or "":
        if char == "(":
            depth += 1
            max_depth = max(max_depth, depth)
        elif char == ")":
            depth = max(0, depth - 1)
    return max_depth


def _dedupe_valid_mutations(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in MUTATION_OPERATORS or value in result:
            continue
        result.append(value)
    return result or ["change_window"]


def _dedupe_valid_forbidden(values: list[str], allowed: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value in allowed or value in result:
            continue
        result.append(value)
    return result


def _safe_weight_hint(values: dict[str, float] | None) -> dict[str, float]:
    if not isinstance(values, dict):
        return {}
    result: dict[str, float] = {}
    for key, value in values.items():
        name = str(key)
        if name not in MUTATION_OPERATORS:
            continue
        result[name] = round(finite_float(value, 0.0, minimum=0.0), 6)
    return result


def _looks_like_full_rewrite(before: str, after: str) -> bool:
    before_functions = [name.lower() for name, _args in iter_function_calls(before)]
    after_functions = [name.lower() for name, _args in iter_function_calls(after)]
    if len(before_functions) < 2 or len(after_functions) < 2:
        return False
    shared = len(set(before_functions) & set(after_functions))
    return shared / max(len(set(before_functions)), 1) < 0.25


def ast_summary(expression: str) -> dict[str, Any]:
    ast = _parse_ast(expression)
    if not ast:
        return {
            "parseable": False,
            "complexity": complexity_score(expression),
            "operators": [name.lower() for name, _args in iter_function_calls(expression)],
        }
    fields = sorted({node.name.lower() for node in walk(ast) if node.type == "field"})
    operators = [node.name for node in walk(ast) if node.type == "operator"]
    return {
        "parseable": True,
        "root_type": ast.type,
        "operators": operators,
        "fields": fields,
        "complexity": complexity_score(expression),
        "semantic_signature": semantic_signature(ast),
    }


def _parse_ast(expression: str) -> ASTNode | None:
    try:
        return ExpressionParser().parse(_strip_fast_expression_comments(expression))
    except (ParseError, RecursionError, ValueError):
        return None


def _strip_fast_expression_comments(expression: str) -> str:
    lines = []
    for line in (expression or "").splitlines():
        stripped = line.split("#", 1)[0].strip()
        if stripped:
            lines.append(stripped)
    return "\n".join(lines)


def _structural_mutations_for_allowed(allowed: list[str], strategy_allowed: list[str]) -> list[str]:
    mapping = {
        "change_window": "replace_window",
        "add_decay": "wrap_node",
        "add_rank": "wrap_node",
        "replace_group": "replace_operator",
        "add_neutralization": "wrap_node",
        "reduce_turnover": "wrap_node",
        "replace_price_source": "replace_field",
        "winsorize_signal": "wrap_node",
        "simplify_expression": "simplify_branch",
        "hump": "wrap_node",
        "bucket": "insert_node",
        "rank": "wrap_node",
        "replace_signal": "replace_operator",
    }
    result: list[str] = []
    for value in list(strategy_allowed) + [mapping.get(item, item) for item in allowed]:
        if value not in result:
            result.append(value)
    return result or ["replace_window"]
