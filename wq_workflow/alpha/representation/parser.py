from __future__ import annotations

from .ast import AlphaASTNode
from .errors import AlphaParseError
from .normalizer import normalize_identifier
from .tokenizer import Token, tokenize


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.index = 0

    def current(self) -> Token:
        return self.tokens[min(self.index, len(self.tokens) - 1)]

    def peek(self, offset: int = 1) -> Token:
        return self.tokens[min(self.index + offset, len(self.tokens) - 1)]

    def advance(self) -> Token:
        token = self.current()
        if self.index < len(self.tokens) - 1:
            self.index += 1
        return token

    def parse(self) -> AlphaASTNode | None:
        if self.current().type == "EOF":
            return None
        node = self.parse_node(depth=0)
        if node is None:
            return None
        while self.current().type not in {"EOF", "RPAREN"}:
            # tolerate trailing symbols/unknowns, but consume them to avoid loops
            self.advance()
        if self.current().type == "RPAREN":
            raise AlphaParseError("unmatched right parenthesis")
        return node

    def parse_node(self, depth: int) -> AlphaASTNode:
        token = self.current()
        if token.type == "IDENT":
            if self.peek().type == "LPAREN":
                return self.parse_operator_call(depth)
            self.advance()
            value = normalize_identifier(token.value) or token.value
            return AlphaASTNode(node_type="field", value=value, raw=token.value, depth=depth)
        if token.type == "NUMBER":
            self.advance()
            return AlphaASTNode(node_type="number", value=token.value, raw=token.value, depth=depth)
        if token.type in {"OPERATOR_SYMBOL", "UNKNOWN"}:
            self.advance()
            return AlphaASTNode(node_type="unknown", value=token.value, raw=token.value, depth=depth)
        if token.type == "LPAREN":
            self.advance()
            child = self.parse_node(depth + 1)
            if self.current().type == "RPAREN":
                self.advance()
            return child
        raise AlphaParseError(f"unexpected token {token.type} at {token.position}")

    def parse_operator_call(self, depth: int) -> AlphaASTNode:
        ident = self.advance()
        self.advance()  # LPAREN
        value = normalize_identifier(ident.value) or ident.value
        children: list[AlphaASTNode] = []
        while True:
            token = self.current()
            if token.type == "EOF":
                raise AlphaParseError(f"unclosed operator call {ident.value}")
            if token.type == "RPAREN":
                self.advance()
                break
            if token.type == "COMMA":
                self.advance()
                continue
            try:
                children.append(self.parse_node(depth + 1))
            except AlphaParseError:
                bad = self.advance()
                children.append(AlphaASTNode(node_type="unknown", value=bad.value, raw=bad.value, depth=depth + 1))
        return AlphaASTNode(node_type="operator", value=value, children=children, raw=ident.value, depth=depth)


def _assign_depths(node: AlphaASTNode | None, depth: int = 0) -> None:
    if node is None:
        return
    node.depth = depth
    for child in node.children:
        _assign_depths(child, depth + 1)


def parse_expression(expression: str) -> AlphaASTNode | None:
    parser = _Parser(tokenize(expression))
    node = parser.parse()
    _assign_depths(node)
    return node
