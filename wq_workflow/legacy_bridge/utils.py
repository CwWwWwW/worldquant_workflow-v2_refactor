from __future__ import annotations

import json
import math
import os
import re
import shutil
import uuid
from dataclasses import fields, is_dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

DEFAULT_MAX_TEXT_CHARS = 300
DEFAULT_MAX_PAYLOAD_CHARS = 1000
SENSITIVE_KEY_PARTS = ("cookie", "session", "token", "secret", "password", "authorization", "api_key", "apikey")
LARGE_KEY_PARTS = ("html", "traceback", "prompt", "expression", "template_body", "page_text", "raw_response")


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def truncate_text(value: Any, max_chars: int = DEFAULT_MAX_TEXT_CHARS) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    limit = max(0, int(max_chars or 0))
    if limit and len(text) > limit:
        return text[: max(0, limit - 3)] + "..."
    return text


def is_sensitive_key(key: Any) -> bool:
    lowered = str(key or "").lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def is_large_key(key: Any) -> bool:
    lowered = str(key or "").lower()
    return any(part in lowered for part in LARGE_KEY_PARTS)


def json_safe(value: Any, *, max_text_chars: int = DEFAULT_MAX_TEXT_CHARS, max_payload_chars: int = DEFAULT_MAX_PAYLOAD_CHARS, _depth: int = 0) -> Any:
    if _depth > 5:
        return truncate_text(value, max_text_chars)
    if value is None or isinstance(value, (bool, int, str)):
        return truncate_text(value, max_text_chars) if isinstance(value, str) else value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return json_safe({field.name: getattr(value, field.name, None) for field in fields(value)}, max_text_chars=max_text_chars, max_payload_chars=max_payload_chars, _depth=_depth + 1)
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in list(value.items())[:50]:
            skey = str(key)
            if is_sensitive_key(skey):
                cleaned[skey] = "[REDACTED]"
            elif is_large_key(skey):
                cleaned[skey] = truncate_text(item, max_text_chars)
            else:
                cleaned[skey] = json_safe(item, max_text_chars=max_text_chars, max_payload_chars=max_payload_chars, _depth=_depth + 1)
        return cleaned
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item, max_text_chars=max_text_chars, max_payload_chars=max_payload_chars, _depth=_depth + 1) for item in list(value)[:50]]
    try:
        return truncate_text(str(value), max_text_chars)
    except Exception:
        return "[unserializable]"


def summarize_payload(payload: Any, *, max_payload_chars: int = DEFAULT_MAX_PAYLOAD_CHARS, max_text_chars: int = DEFAULT_MAX_TEXT_CHARS) -> dict[str, Any]:
    cleaned = json_safe(payload if isinstance(payload, dict) else {"value": payload}, max_text_chars=max_text_chars, max_payload_chars=max_payload_chars)
    if not isinstance(cleaned, dict):
        cleaned = {"value": cleaned}
    try:
        encoded = json.dumps(cleaned, ensure_ascii=False, default=str)
    except Exception:
        return {"summary": "payload_unserializable"}
    if len(encoded) <= max(1, int(max_payload_chars)):
        return cleaned
    summary: dict[str, Any] = {}
    for key, value in cleaned.items():
        if isinstance(value, dict):
            summary[key] = {"type": "dict", "keys": list(value.keys())[:8]}
        elif isinstance(value, list):
            summary[key] = {"type": "list", "count": len(value)}
        else:
            summary[key] = truncate_text(value, max_text_chars)
        try:
            if len(json.dumps(summary, ensure_ascii=False, default=str)) >= int(max_payload_chars):
                break
        except Exception:
            break
    summary.setdefault("_truncated", True)
    return summary


def summarize_exception(error: BaseException | str, *, include_traceback: bool = False, max_chars: int = DEFAULT_MAX_TEXT_CHARS) -> str:
    if isinstance(error, BaseException):
        text = f"{type(error).__name__}: {error}"
    else:
        text = str(error)
    if include_traceback:
        return truncate_text(text, max_chars)
    return truncate_text(text.splitlines()[-1] if text else "", max_chars)


def resolve_path(root: str | Path, path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else Path(root) / candidate


def atomic_write_json_direct(path: str | Path, payload: Any) -> bool:
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(json_safe(payload), ensure_ascii=False, indent=2, allow_nan=False, default=str) + "\n", encoding="utf-8")
        tmp.replace(target)
        return True
    except Exception:
        try:
            if 'tmp' in locals() and tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return False


def rotate_if_large_direct(path: str | Path, max_bytes: int | None) -> None:
    if not max_bytes or max_bytes <= 0:
        return
    target = Path(path)
    try:
        if not target.exists() or target.stat().st_size <= int(max_bytes):
            return
        stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        archive = target.with_name(f"{target.stem}.{stamp}{target.suffix}")
        shutil.move(str(target), str(archive))
    except Exception:
        return


def append_jsonl_direct(path: str | Path, payload: dict[str, Any], *, max_bytes: int | None = None, fsync: bool = False) -> bool:
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        rotate_if_large_direct(target, max_bytes)
        line = json.dumps(json_safe(payload), ensure_ascii=False, allow_nan=False, default=str)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            if fsync:
                try:
                    os.fsync(fh.fileno())
                except Exception:
                    pass
        return True
    except Exception:
        return False


def read_jsonl_tail_direct(path: str | Path, *, limit: int = 50, max_bytes: int = 262_144, warnings: list[str] | None = None) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    try:
        with target.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - max(1, int(max_bytes))))
            text = fh.read().decode("utf-8-sig", errors="replace")
        if size > max(1, int(max_bytes)):
            first_newline = text.find("\n")
            if first_newline >= 0:
                text = text[first_newline + 1 :]
    except Exception:
        if warnings is not None:
            warnings.append("jsonl_read_failed")
        return []
    rows: list[dict[str, Any]] = []
    bad_line_warned = False
    for line in text.splitlines()[-max(1, int(limit)):]:
        try:
            value = json.loads(line)
        except Exception:
            if warnings is not None and not bad_line_warned:
                warnings.append("bad_jsonl_line_skipped")
                bad_line_warned = True
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows
