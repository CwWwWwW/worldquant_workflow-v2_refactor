from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


class CSVStore:
    def __init__(self, path: str | Path, fieldnames: list[str] | None = None) -> None:
        self.path = Path(path)
        self.fieldnames = list(fieldnames or [])

    def append(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = dict(record or {})
        fieldnames = list(dict.fromkeys([*self.fieldnames, *row.keys()]))
        existing: list[dict[str, Any]] = []
        if self.path.exists() and self.path.stat().st_size > 0:
            with self.path.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                fieldnames = list(dict.fromkeys([*(reader.fieldnames or []), *fieldnames]))
                existing = list(reader)
        with self.path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for old in existing:
                writer.writerow({k: old.get(k, "") for k in fieldnames})
            writer.writerow({k: row.get(k, "") for k in fieldnames})
