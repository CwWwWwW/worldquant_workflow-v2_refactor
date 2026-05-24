from __future__ import annotations

import hashlib
import re


def normalize_expression(expr: str) -> str:
    if not expr:
        return ""
    return re.sub(r"\s+", "", str(expr)).lower()


def stable_hash(text: str) -> str:
    return hashlib.md5((text or "").encode("utf-8")).hexdigest()


def normalize_identifier(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "", str(text or "")).lower()
