from wq_workflow.alpha.representation.tokenizer import tokenize


def test_tokenize_common_expression():
    tokens = tokenize("ts_rank(close, 20)")
    types = [t.type for t in tokens]
    values = [t.value for t in tokens]
    assert types[:6] == ["IDENT", "LPAREN", "IDENT", "COMMA", "NUMBER", "RPAREN"]
    assert values[:6] == ["ts_rank", "(", "close", ",", "20", ")"]
    assert tokens[-1].type == "EOF"


def test_tokenize_unknown_does_not_crash():
    tokens = tokenize("rank(close) @")
    assert any(t.type == "UNKNOWN" and t.value == "@" for t in tokens)
    assert tokens[-1].type == "EOF"


def test_tokenize_operator_symbol_and_negative_number():
    tokens = tokenize("trade_when(volume > 0, rank(close), -1)")
    assert any(t.type == "OPERATOR_SYMBOL" and t.value == ">" for t in tokens)
    assert any(t.type == "NUMBER" and t.value == "-1" for t in tokens)
