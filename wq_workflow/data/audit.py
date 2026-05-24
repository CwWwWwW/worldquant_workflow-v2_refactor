from __future__ import annotations

from typing import Any


def record_data_audit_failure(logger: Any | None, *, operation: str, error: Exception | str, storage: Any | None = None, context: dict[str, Any] | None = None) -> None:
    message = f"data-layer operation failed: {operation}: {error}"
    try:
        if logger is not None:
            logger.warning(message)
    except Exception:
        pass
    try:
        if storage is not None and hasattr(storage, "write_event"):
            storage.write_event(
                "logs/data_audit.jsonl",
                {"event": "data_audit_failure", "operation": operation, "error": str(error), "context": context or {}},
                max_bytes=16384,
            )
    except Exception:
        pass
