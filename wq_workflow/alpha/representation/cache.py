from __future__ import annotations

from collections import OrderedDict
from typing import Any, Callable

from .normalizer import normalize_expression


class AlphaRepresentationCache:
    def __init__(self, max_size: int = 10000) -> None:
        self.max_size = max(1, int(max_size or 10000))
        self._items: OrderedDict[str, Any] = OrderedDict()

    def get(self, expression: str) -> Any | None:
        key = normalize_expression(expression or "")
        item = self._items.get(key)
        if item is not None:
            self._items.move_to_end(key)
        return item

    def put(self, expression: str, representation: Any) -> None:
        key = normalize_expression(expression or "")
        self._items[key] = representation
        self._items.move_to_end(key)
        while len(self._items) > self.max_size:
            self._items.popitem(last=False)

    def build_or_get(self, expression: str, builder: Callable[[str], Any]) -> Any:
        try:
            cached = self.get(expression)
            if cached is not None:
                return cached
            representation = builder(expression)
            self.put(expression, representation)
            return representation
        except Exception:
            return builder(expression)


_DEFAULT_CACHE = AlphaRepresentationCache()


def get(expression: str) -> Any | None:
    return _DEFAULT_CACHE.get(expression)


def put(expression: str, representation: Any) -> None:
    _DEFAULT_CACHE.put(expression, representation)


def build_or_get(expression: str, builder: Callable[[str], Any], *, cache: AlphaRepresentationCache | None = None) -> Any:
    return (cache or _DEFAULT_CACHE).build_or_get(expression, builder)
