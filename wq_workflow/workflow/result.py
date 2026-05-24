from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StepResult:
    ok: bool = True
    data: dict[str, Any] = field(default_factory=dict)
    error: Any = ""
    warnings: list[str] = field(default_factory=list)
    fatal: bool = False
    skip_remaining: bool = False
    source: str = ""
    message: str = ""
