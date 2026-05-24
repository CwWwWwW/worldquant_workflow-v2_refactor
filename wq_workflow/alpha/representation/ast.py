from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AlphaASTNode:
    node_type: str
    value: str
    children: list["AlphaASTNode"] = field(default_factory=list)
    raw: str = ""
    depth: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def walk(self) -> list["AlphaASTNode"]:
        nodes = [self]
        for child in self.children:
            nodes.extend(child.walk())
        return nodes

    def operators(self) -> list[str]:
        return [n.value for n in self.walk() if n.node_type == "operator"]

    def fields(self) -> list[str]:
        return [n.value for n in self.walk() if n.node_type == "field"]

    def numbers(self) -> list[float]:
        out: list[float] = []
        for n in self.walk():
            if n.node_type == "number":
                try:
                    out.append(float(n.value))
                except Exception:
                    pass
        return out

    def max_depth(self) -> int:
        return max((n.depth for n in self.walk()), default=0)

    def node_count(self) -> int:
        return len(self.walk())


def serialize_ast(node: AlphaASTNode | None) -> dict[str, Any] | None:
    if node is None:
        return None
    return {
        "node_type": node.node_type,
        "value": node.value,
        "raw": node.raw,
        "depth": node.depth,
        "metadata": dict(node.metadata or {}),
        "children": [serialize_ast(child) for child in node.children],
    }
