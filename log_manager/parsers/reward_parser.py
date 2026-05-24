from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterator

from .jsonl_parser import iter_jsonl


REWARD_REQUIRED_FIELDS = ["alpha_id", "legacy_reward", "v2_reward", "final_reward", "state"]


def iter_reward_entries(path: Path) -> Iterator[tuple[int, dict[str, Any] | None, list[str]]]:
    if path.suffix.lower() == ".jsonl":
        for line_no, _raw, payload, error in iter_jsonl(path):
            errors = [error] if error else []
            if payload is not None:
                errors.extend(validate_reward_entry(payload))
            yield line_no, payload, errors
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        yield 0, None, [str(exc)]
        return
    if isinstance(payload, list):
        for index, item in enumerate(payload, start=1):
            value = item if isinstance(item, dict) else None
            yield index, value, validate_reward_entry(value or {})
    elif isinstance(payload, dict):
        yield 1, payload, validate_reward_entry(payload)
    else:
        yield 1, None, ["reward json is not an object or list"]


def validate_reward_entry(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["reward entry is not an object"]
    for field in REWARD_REQUIRED_FIELDS:
        if field not in payload:
            errors.append(f"missing {field}")
    for field in ["legacy_reward", "v2_reward", "final_reward"]:
        if field in payload:
            try:
                value = float(payload.get(field))
            except (TypeError, ValueError):
                errors.append(f"invalid numeric {field}")
                continue
            if not math.isfinite(value):
                errors.append(f"invalid numeric {field}")
    return errors
