from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class ASTNode:
    type: str
    name: str = ""
    operator: str = ""
    children: list["ASTNode"] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    value: Any = None

    def clone(self) -> "ASTNode":
        return ASTNode(
            type=self.type,
            name=self.name,
            operator=self.operator,
            children=[child.clone() for child in self.children],
            parameters=dict(self.parameters),
            metadata=dict(self.metadata),
            value=self.value,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"type": self.type}
        if self.name:
            payload["name"] = self.name
        if self.operator:
            payload["operator"] = self.operator
        if self.parameters:
            payload["parameters"] = self.parameters
        if self.children:
            payload["children"] = [child.to_dict() for child in self.children]
        if self.value is not None and self.type in {"number", "string"}:
            payload["value"] = self.value
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload

    @property
    def display_name(self) -> str:
        return self.name or self.operator or str(self.value or self.type)


def walk(node: ASTNode) -> Iterator[ASTNode]:
    yield node
    for child in node.children:
        yield from walk(child)


def replace_child(root: ASTNode, target: ASTNode, replacement: ASTNode) -> ASTNode:
    clone = root.clone()
    _replace_child_in_place(clone, target, replacement)
    return clone


def _replace_child_in_place(node: ASTNode, target: ASTNode, replacement: ASTNode) -> bool:
    for index, child in enumerate(node.children):
        if child is target or child.to_dict() == target.to_dict():
            node.children[index] = replacement.clone()
            return True
        if _replace_child_in_place(child, target, replacement):
            return True
    return False

