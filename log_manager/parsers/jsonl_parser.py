from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator


def iter_jsonl(path: Path) -> Iterator[tuple[int, str, dict[str, Any] | None, str | None]]:
    with path.open("r", encoding="utf-8-sig", errors="replace") as fh:
        for line_no, raw_line in enumerate(fh, start=1):
            text = raw_line.rstrip("\r\n")
            if not text.strip():
                yield line_no, raw_line, None, None
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                yield line_no, raw_line, None, str(exc)
                continue
            if not isinstance(payload, dict):
                yield line_no, raw_line, None, "jsonl row is not an object"
                continue
            yield line_no, raw_line, payload, None
