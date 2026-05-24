from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ast import AlphaASTNode


@dataclass
class AlphaRepresentation:
    raw_expression: str
    normalized_expression: str
    expression_hash: str
    parse_status: str = "ok"
    parse_error: str = ""
    ast: AlphaASTNode | None = None

    operator_sequence: list[str] = field(default_factory=list)
    field_sequence: list[str] = field(default_factory=list)
    numeric_params: list[float] = field(default_factory=list)

    root_operator: str = ""
    ast_depth: int = 0
    node_count: int = 0
    operator_count: int = 0
    field_count: int = 0
    unique_operator_count: int = 0
    unique_field_count: int = 0

    subtree_fingerprints: list[str] = field(default_factory=list)
    operator_path_features: dict[str, Any] = field(default_factory=dict)

    behavior_family: str = ""
    behavior_fingerprint: str = ""

    feature_vector: list[float] = field(default_factory=list)
    features: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "expression_hash": self.expression_hash,
            "parse_status": self.parse_status,
            "root_operator": self.root_operator,
            "operator_count": self.operator_count,
            "field_count": self.field_count,
            "ast_depth": self.ast_depth,
            "behavior_family": self.behavior_family,
            "behavior_fingerprint": self.behavior_fingerprint,
        }
