from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .ast import ASTNode, serialize_ast, walk
from .mutation_constraints import MutationConstraints
from .operators import OPERATOR_ARITY, semantic_safe_field_swap


@dataclass
class MutationCandidate:
    ast: ASTNode
    expression: str
    mutation_type: str
    description: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


class StructuralMutator:
    def __init__(self, constraints: MutationConstraints | None = None) -> None:
        self.constraints = constraints or MutationConstraints()

    def generate(
        self,
        ast: ASTNode,
        strategy: object | None = None,
        constraints: MutationConstraints | None = None,
        operator_graph: object | None = None,
    ) -> list[MutationCandidate]:
        active_constraints = constraints or self.constraints
        strategy_name = str(getattr(strategy, "name", strategy or "")).lower()
        mutations = self._strategy_mutations(strategy_name)
        candidates: list[MutationCandidate] = []
        for mutation in mutations:
            if mutation == "replace_window":
                candidates.extend(self.replace_window(ast))
            elif mutation == "wrap_node":
                wrappers = _recommended_wrappers(operator_graph, strategy_name)
                for wrapper in wrappers:
                    candidates.extend(self.wrap_node(ast, wrapper))
            elif mutation == "replace_operator":
                candidates.extend(self.replace_operator(ast))
            elif mutation == "insert_node":
                candidates.extend(self.insert_node(ast))
            elif mutation == "remove_node":
                candidates.extend(self.remove_node(ast))
            elif mutation == "simplify_branch":
                candidates.extend(self.simplify_branch(ast))
        return _dedupe_candidates(
            candidate
            for candidate in candidates
            if active_constraints.validate(candidate.ast).passed
        )

    def replace_operator(self, ast: ASTNode) -> list[MutationCandidate]:
        replacements = {
            "ts_mean": ["ts_rank", "ts_zscore"],
            "ts_rank": ["ts_mean", "ts_zscore"],
            "ts_zscore": ["ts_rank", "ts_scale"],
            "group_neutralize": ["group_zscore", "group_rank"],
            "group_zscore": ["group_neutralize", "group_rank"],
            "rank": ["scale"],
            "scale": ["rank"],
        }
        candidates: list[MutationCandidate] = []
        for path, node in _operator_paths(ast):
            for replacement in replacements.get(node.name, []):
                if _arity_compatible(replacement, node):
                    clone = ast.clone()
                    target = _get_path(clone, path)
                    target.name = replacement
                    target.metadata["replaced_from"] = node.name
                    candidates.append(_candidate(clone, "replace_operator", f"{node.name}->{replacement}"))
        return candidates

    def replace_window(self, ast: ASTNode) -> list[MutationCandidate]:
        candidates: list[MutationCandidate] = []
        for path, node in _operator_paths(ast):
            if isinstance(node.parameters.get("window"), int):
                for value in _nearby_windows(int(node.parameters["window"])):
                    clone = ast.clone()
                    target = _get_path(clone, path)
                    old = target.parameters["window"]
                    target.parameters["window"] = value
                    candidates.append(_candidate(clone, "replace_window", f"{node.name} window {old}->{value}"))
            for child_index, child in enumerate(node.children):
                if child.type != "number":
                    continue
                for value in _nearby_windows(int(child.value)):
                    clone = ast.clone()
                    target = _get_path(clone, path)
                    target.children[child_index].value = value
                    candidates.append(_candidate(clone, "replace_window", f"{node.name} window {child.value}->{value}"))
        return candidates

    def insert_node(self, ast: ASTNode) -> list[MutationCandidate]:
        return self.wrap_node(ast, "rank") + self.wrap_node(ast, "winsorize")

    def remove_node(self, ast: ASTNode) -> list[MutationCandidate]:
        candidates: list[MutationCandidate] = []
        removable = {"rank", "scale", "winsorize", "hump"}
        for path, node in _operator_paths(ast):
            if node.name not in removable or len(node.children) != 1:
                continue
            clone = ast.clone()
            _replace_path(clone, path, node.children[0])
            candidates.append(_candidate(clone, "remove_node", f"remove {node.name}"))
        return candidates

    def wrap_node(self, ast: ASTNode, wrapper: str = "ts_decay_exp_window", window: int = 8) -> list[MutationCandidate]:
        candidates: list[MutationCandidate] = []
        for path, node in _signal_paths(ast):
            wrapped = self._wrapper_node(wrapper, node.clone(), window)
            if not wrapped:
                continue
            clone = ast.clone()
            _replace_path(clone, path, wrapped)
            candidates.append(_candidate(clone, "wrap_node", f"wrap {node.display_name} with {wrapper}"))
        return candidates

    def simplify_branch(self, ast: ASTNode) -> list[MutationCandidate]:
        candidates: list[MutationCandidate] = []
        for path, node in _operator_paths(ast):
            if len(node.children) == 1 and node.children[0].type == "operator" and node.children[0].name == node.name:
                clone = ast.clone()
                _replace_path(clone, path, node.children[0])
                candidates.append(_candidate(clone, "simplify_branch", f"collapse {node.name}({node.name}())"))
            if node.name in {"group_neutralize", "group_zscore"} and node.children and node.children[0].type == "operator":
                child = node.children[0]
                if child.name == node.name and child.children:
                    clone = ast.clone()
                    replacement = child.children[0].clone()
                    _replace_path(clone, path, ASTNode(type="operator", name=node.name, children=[replacement, *node.children[1:]]))
                    candidates.append(_candidate(clone, "simplify_branch", f"collapse repeated {node.name}"))
        return candidates

    def replace_field(self, ast: ASTNode, source: str, replacement: str) -> MutationCandidate | None:
        if not semantic_safe_field_swap(source, replacement):
            return None
        clone = ast.clone()
        changed = False
        for node in walk(clone):
            if node.type == "field" and node.name.lower() == source.lower():
                node.name = replacement
                changed = True
        return _candidate(clone, "replace_field", f"{source}->{replacement}") if changed else None

    def _strategy_mutations(self, strategy_name: str) -> list[str]:
        if "turnover" in strategy_name:
            return ["wrap_node", "replace_window", "simplify_branch"]
        if "simplification" in strategy_name or "repair" in strategy_name:
            return ["simplify_branch", "remove_node", "replace_operator", "replace_window"]
        if "diversity" in strategy_name:
            return ["replace_operator", "wrap_node", "replace_window", "insert_node"]
        return ["replace_window", "wrap_node", "replace_operator", "simplify_branch"]

    def _wrapper_node(self, wrapper: str, node: ASTNode, window: int) -> ASTNode | None:
        if wrapper == "ts_decay_exp_window":
            return ASTNode(type="operator", name="ts_decay_exp_window", children=[node], parameters={"window": window})
        if wrapper == "ts_mean":
            return ASTNode(type="operator", name="ts_mean", children=[node], parameters={"window": max(5, window)})
        if wrapper == "hump":
            return ASTNode(type="operator", name="hump", children=[node])
        if wrapper == "rank":
            return ASTNode(type="operator", name="rank", children=[node])
        if wrapper == "winsorize":
            return ASTNode(type="operator", name="winsorize", children=[node])
        return None


def _candidate(ast: ASTNode, mutation_type: str, description: str) -> MutationCandidate:
    return MutationCandidate(ast=ast, expression=serialize_ast(ast), mutation_type=mutation_type, description=description)


def _dedupe_candidates(candidates: Iterable[MutationCandidate]) -> list[MutationCandidate]:
    seen: set[str] = set()
    result: list[MutationCandidate] = []
    for candidate in candidates:
        key = "".join(candidate.expression.lower().split())
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def _operator_paths(ast: ASTNode) -> list[tuple[tuple[int, ...], ASTNode]]:
    return [(path, node) for path, node in _paths(ast) if node.type == "operator"]


def _signal_paths(ast: ASTNode) -> list[tuple[tuple[int, ...], ASTNode]]:
    return [
        (path, node)
        for path, node in _paths(ast)
        if node.type in {"field", "variable", "operator"} and node.type != "program"
    ]


def _paths(ast: ASTNode, path: tuple[int, ...] = ()) -> list[tuple[tuple[int, ...], ASTNode]]:
    rows = [(path, ast)]
    for index, child in enumerate(ast.children):
        rows.extend(_paths(child, path + (index,)))
    return rows


def _get_path(ast: ASTNode, path: tuple[int, ...]) -> ASTNode:
    node = ast
    for index in path:
        node = node.children[index]
    return node


def _replace_path(ast: ASTNode, path: tuple[int, ...], replacement: ASTNode) -> None:
    if not path:
        ast.type = replacement.type
        ast.name = replacement.name
        ast.operator = replacement.operator
        ast.children = [child.clone() for child in replacement.children]
        ast.parameters = dict(replacement.parameters)
        ast.metadata = dict(replacement.metadata)
        ast.value = replacement.value
        return
    parent = _get_path(ast, path[:-1])
    parent.children[path[-1]] = replacement.clone()


def _arity_compatible(operator: str, node: ASTNode) -> bool:
    min_args, max_args = OPERATOR_ARITY.get(operator, (0, 99))
    count = len(node.children) + len(node.parameters)
    return min_args <= count <= max_args


def _nearby_windows(value: int) -> list[int]:
    canonical = [3, 5, 8, 10, 20, 21, 40, 60, 63, 120, 126, 252]
    if value in canonical:
        index = canonical.index(value)
        values = canonical[max(0, index - 1) : min(len(canonical), index + 2)]
    else:
        values = [max(2, value // 2), value + 5, value * 2]
    return [item for item in values if item != value]


def _recommended_wrappers(operator_graph: object | None, strategy_name: str) -> list[str]:
    if "turnover" in strategy_name:
        return ["hump", "ts_decay_exp_window", "ts_mean"]
    return ["ts_decay_exp_window", "ts_mean", "rank"]
