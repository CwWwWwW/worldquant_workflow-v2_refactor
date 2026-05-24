from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    type: str
    value: str
    position: int


_SYMBOL_OPERATORS = set("+-*/><=%!^")


def _previous_allows_signed_number(tokens: list[Token]) -> bool:
    if not tokens:
        return True
    return tokens[-1].type in {"COMMA", "LPAREN", "OPERATOR_SYMBOL"}


def tokenize(expression: str) -> list[Token]:
    text = str(expression or "")
    tokens: list[Token] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch.isalpha() or ch == "_":
            start = i
            i += 1
            while i < n and (text[i].isalnum() or text[i] == "_"):
                i += 1
            tokens.append(Token("IDENT", text[start:i], start))
            continue
        if ch in {'"', "'"}:
            quote = ch
            start = i
            i += 1
            while i < n and text[i] != quote:
                i += 1
            if i < n:
                i += 1
            tokens.append(Token("IDENT", text[start + 1 : i - 1 if i <= n else i], start))
            continue
        signed_number = ch in "+-" and i + 1 < n and (text[i + 1].isdigit() or text[i + 1] == ".") and _previous_allows_signed_number(tokens)
        if ch.isdigit() or (ch == "." and i + 1 < n and text[i + 1].isdigit()) or signed_number:
            start = i
            if text[i] in "+-":
                i += 1
            seen_dot = False
            while i < n and (text[i].isdigit() or (text[i] == "." and not seen_dot)):
                if text[i] == ".":
                    seen_dot = True
                i += 1
            tokens.append(Token("NUMBER", text[start:i], start))
            continue
        if ch == ",":
            tokens.append(Token("COMMA", ch, i))
            i += 1
            continue
        if ch == "(":
            tokens.append(Token("LPAREN", ch, i))
            i += 1
            continue
        if ch == ")":
            tokens.append(Token("RPAREN", ch, i))
            i += 1
            continue
        if ch in _SYMBOL_OPERATORS:
            start = i
            i += 1
            if i < n and text[start:i] + text[i] in {">=", "<=", "==", "!=", "&&", "||"}:
                i += 1
            tokens.append(Token("OPERATOR_SYMBOL", text[start:i], start))
            continue
        tokens.append(Token("UNKNOWN", ch, i))
        i += 1
    tokens.append(Token("EOF", "", n))
    return tokens
