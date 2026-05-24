from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterator


def iter_csv_rows(path: Path) -> Iterator[tuple[int, dict[str, str], str | None]]:
    with path.open("r", newline="", encoding="utf-8-sig", errors="replace") as fh:
        try:
            reader = csv.DictReader(fh)
        except csv.Error as exc:
            yield 0, {}, str(exc)
            return
        if not reader.fieldnames:
            yield 0, {}, "missing csv header"
            return
        for line_no, row in enumerate(reader, start=2):
            try:
                if row is None:
                    yield line_no, {}, "empty csv row"
                else:
                    yield line_no, dict(row), None
            except csv.Error as exc:
                yield line_no, {}, str(exc)
