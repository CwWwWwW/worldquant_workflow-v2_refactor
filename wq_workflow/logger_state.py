from __future__ import annotations

import json
import logging
import time
from typing import Any

from .paths import STATE_LOG_FILE
from .safe_io import append_jsonl


STATE_ENTER = "STATE_ENTER"
STATE_EXIT = "STATE_EXIT"
STATE_TIMEOUT = "STATE_TIMEOUT"
STATE_PROGRESS = "STATE_PROGRESS"
STATE_RETRY = "STATE_RETRY"
STATE_RECOVER = "STATE_RECOVER"
STATE_FATAL = "STATE_FATAL"

_RESERVED_STATE_LOG_FIELDS = {
    "time",
    "event",
    "alpha_id",
    "state",
    "duration",
    "retry",
    "recovery",
    "error",
    "simulation_id",
}


def _append_optional_fields(payload: dict[str, Any], extra: dict[str, Any] | None) -> None:
    if not extra:
        return
    for key, value in extra.items():
        if key in _RESERVED_STATE_LOG_FIELDS:
            logging.warning("Ignored state log extra field that would overwrite legacy field: %s", key)
            continue
        payload[key] = value


def log_state_event(
    event: str,
    *,
    alpha_id: str,
    state: str,
    duration: float | None = None,
    retry: int | None = None,
    recovery: str | None = None,
    error: str | None = None,
    simulation_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "event": event,
        "alpha_id": alpha_id,
        "state": state,
    }
    if duration is not None:
        payload["duration"] = round(float(duration), 3)
    if retry is not None:
        payload["retry"] = retry
    if recovery:
        payload["recovery"] = recovery
    if error:
        payload["error"] = error
    if simulation_id:
        payload["simulation_id"] = simulation_id
    _append_optional_fields(payload, extra)

    append_jsonl(STATE_LOG_FILE, payload)

    logging.info("FSM %s %s", event, json.dumps(payload, ensure_ascii=False, default=str))
    return payload


def log_recovery_sidecar(
    label: str,
    *,
    action: str,
    alpha_id: str = "",
    state: str = "",
    recovery: str = "",
    error: str = "",
    **metadata: Any,
) -> None:
    parts = [f"[{label}]", f"action={action}"]
    if alpha_id:
        parts.append(f"alpha_id={alpha_id}")
    if state:
        parts.append(f"state={state}")
    if recovery:
        parts.append(f"recovery={recovery}")
    for key, value in metadata.items():
        if value is None or value == "":
            continue
        parts.append(f"{key}={value}")
    if error:
        parts.append(f"error={error}")
    logging.warning(" ".join(parts))
