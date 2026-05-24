from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..ast.ast_node import ASTNode
from ..operators import OPERATOR_ARITY, SAFE_FIELDS

WINDOW_OPERATORS = {
    "ts_backfill",
    "ts_corr",
    "ts_count_nans",
    "ts_decay_exp_window",
    "ts_delta",
    "ts_mean",
    "ts_product",
    "ts_rank",
    "ts_scale",
    "ts_std_dev",
    "ts_sum",
    "ts_zscore",
}


class ParseError(ValueError):
    pass


@dataclass(frozen=True)
class Token:
    type: str
    value: str
    position: int


class ExpressionParser:
    def parse(self, expression: str) -> ASTNode:
        tokens = self.tokenize(expression)
        return self.build_ast(tokens)

    def tokenize(self, expression: str) -> list[Token]:
        tokens: list[Token] = []
        text = expression or ""
        index = 0
        while index < len(text):
            char = text[index]
            if char in " \t\r":
                index += 1
                continue
            if char == "\n" or char == ";":
                tokens.append(Token("SEPARATOR", char, index))
                index += 1
                continue
            if char.isalpha() or char == "_":
                start = index
                index += 1
                while index < len(text) and (text[index].isalnum() or text[index] == "_"):
                    index += 1
                tokens.append(Token("IDENT", text[start:index], start))
                continue
            if char.isdigit() or (char == "." and index + 1 < len(text) and text[index + 1].isdigit()):
                start = index
                index += 1
                while index < len(text) and (text[index].isdigit() or text[index] == "."):
                    index += 1
                tokens.append(Token("NUMBER", text[start:index], start))
                continue
            if char in {'"', "'"}:
                quote = char
                start = index
                index += 1
                value = []
                while index < len(text):
                    current = text[index]
                    if current == "\\" and index + 1 < len(text):
                        value.append(text[index + 1])
                        index += 2
                        continue
                    if current == quote:
                        index += 1
                        break
                    value.append(current)
                    index += 1
                else:
                    raise ParseError(f"Unclosed string at {start}")
                tokens.append(Token("STRING", "".join(value), start))
                continue
            two_char = text[index : index + 2]
            if two_char in {">=", "<=", "==", "!="}:
                tokens.append(Token(two_char, two_char, index))
                index += 2
                continue
            if char in "(),=+-*/<>":
                tokens.append(Token(char, char, index))
                index += 1
                continue
            raise ParseError(f"Unexpected character {char!r} at {index}")
        tokens.append(Token("EOF", "", len(text)))
        return tokens

    def build_ast(self, tokens: list[Token]) -> ASTNode:
        stream = _TokenStream(tokens)
        statements: list[ASTNode] = []
        while not stream.match("EOF"):
            if stream.match("SEPARATOR"):
                stream.advance()
                continue
            statements.append(self._statement(stream))
            while stream.match("SEPARATOR"):
                stream.advance()
        if len(statements) == 1:
            return statements[0]
        return ASTNode(type="program", children=statements)

    def _statement(self, stream: "_TokenStream") -> ASTNode:
        if stream.match("IDENT") and stream.peek(1).type == "=":
            name = stream.advance().value
            stream.expect("=")
            return ASTNode(type="assignment", name=name, children=[self._expression(stream)])
        return self._expression(stream)

    def _expression(self, stream: "_TokenStream") -> ASTNode:
        return self._comparison(stream)

    def _comparison(self, stream: "_TokenStream") -> ASTNode:
        left = self._binary(stream, min_precedence=0)
        if stream.current().type in {">", "<", ">=", "<=", "==", "!="}:
            operator = stream.advance().type
            right = self._binary(stream, min_precedence=0)
            return ASTNode(type="comparison", operator=operator, children=[left, right])
        return left

    def _binary(self, stream: "_TokenStream", min_precedence: int) -> ASTNode:
        left = self._unary(stream)
        while stream.current().type in {"+", "-", "*", "/"}:
            operator = stream.current().type
            precedence = 1 if operator in {"+", "-"} else 2
            if precedence < min_precedence:
                break
            stream.advance()
            right = self._binary(stream, precedence + 1)
            left = ASTNode(type="binary", operator=operator, children=[left, right])
        return left

    def _unary(self, stream: "_TokenStream") -> ASTNode:
        if stream.match("+", "-"):
            operator = stream.advance().type
            return ASTNode(type="unary", operator=operator, children=[self._unary(stream)])
        return self._primary(stream)

    def _primary(self, stream: "_TokenStream") -> ASTNode:
        token = stream.current()
        if token.type == "NUMBER":
            stream.advance()
            value: Any = float(token.value) if "." in token.value else int(token.value)
            return ASTNode(type="number", value=value)
        if token.type == "STRING":
            stream.advance()
            return ASTNode(type="string", value=token.value)
        if token.type == "IDENT":
            name = stream.advance().value
            if stream.match("("):
                return self._call(stream, name)
            lowered = name.lower()
            node_type = "field" if lowered in SAFE_FIELDS else "variable"
            return ASTNode(type=node_type, name=name)
        if stream.match("("):
            stream.advance()
            node = self._expression(stream)
            stream.expect(")")
            return node
        raise ParseError(f"Unexpected token {token.type} at {token.position}")

    def _call(self, stream: "_TokenStream", name: str) -> ASTNode:
        stream.expect("(")
        children: list[ASTNode] = []
        parameters: dict[str, Any] = {}
        while not stream.match(")"):
            if stream.match("EOF"):
                raise ParseError(f"Unclosed call {name}")
            if stream.match("IDENT") and stream.peek(1).type == "=":
                key = stream.advance().value
                stream.expect("=")
                value = self._expression(stream)
                parameters[key] = _literal_or_node(value)
            else:
                children.append(self._expression(stream))
            if stream.match(","):
                stream.advance()
                continue
            if not stream.match(")"):
                raise ParseError(f"Expected comma or ')' at {stream.current().position}")
        stream.expect(")")
        lowered = name.lower()
        if lowered in WINDOW_OPERATORS and children and children[-1].type == "number" and "window" not in parameters:
            parameters["window"] = children.pop().value
        metadata = {}
        if lowered in OPERATOR_ARITY:
            metadata["arity"] = OPERATOR_ARITY[lowered]
        return ASTNode(type="operator", name=lowered, children=children, parameters=parameters, metadata=metadata)


def _literal_or_node(node: ASTNode) -> Any:
    if node.type in {"number", "string"}:
        return node.value
    return node


class _TokenStream:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.index = 0

    def current(self) -> Token:
        return self.tokens[self.index]

    def peek(self, offset: int) -> Token:
        index = min(self.index + offset, len(self.tokens) - 1)
        return self.tokens[index]

    def match(self, *types: str) -> bool:
        return self.current().type in types

    def advance(self) -> Token:
        token = self.current()
        if self.index < len(self.tokens) - 1:
            self.index += 1
        return token

    def expect(self, token_type: str) -> Token:
        if not self.match(token_type):
            current = self.current()
            raise ParseError(f"Expected {token_type}, got {current.type} at {current.position}")
        return self.advance()
