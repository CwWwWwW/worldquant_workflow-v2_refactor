from __future__ import annotations

from typing import Any


class FailureArtifactService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs
