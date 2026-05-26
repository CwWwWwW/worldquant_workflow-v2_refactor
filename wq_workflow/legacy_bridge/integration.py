from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from wq_workflow import paths

from .observer import LegacyIterationObserver
from .utils import summarize_payload

_FORBIDDEN_PAYLOAD_KEYS = {"page", "browser", "context", "html", "cookie", "session", "token", "password"}


def observer_enabled(config: Any | None) -> bool:
    try:
        return bool(getattr(config, "enable_legacy_iteration_observer", True))
    except Exception:
        return True


def build_legacy_observer(config: Any | None, *, root: str | Path | None = None) -> LegacyIterationObserver | None:
    if not observer_enabled(config):
        return None
    try:
        return LegacyIterationObserver(config=config, root=root or paths.ROOT, enabled=True)
    except Exception:
        try:
            logging.getLogger(__name__).warning("LegacyIterationObserver unavailable; continuing legacy workflow", exc_info=True)
        except Exception:
            pass
        return None


def _clean_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in kwargs.items():
        lowered = str(key).lower()
        if lowered in _FORBIDDEN_PAYLOAD_KEYS or any(part in lowered for part in _FORBIDDEN_PAYLOAD_KEYS):
            cleaned[key] = "[REDACTED]"
        else:
            cleaned[key] = value
    if "raw_payload" in cleaned:
        cleaned["raw_payload"] = summarize_payload(cleaned.get("raw_payload"))
    return cleaned


def safe_observe(observer: Any | None, method_name: str, **kwargs: Any) -> None:
    if observer is None:
        return
    try:
        method = getattr(observer, method_name, None)
        if not callable(method):
            return
        method(**_clean_kwargs(kwargs))
    except Exception:
        try:
            logging.getLogger(__name__).debug("legacy observer hook skipped: %s", method_name, exc_info=True)
        except Exception:
            pass
