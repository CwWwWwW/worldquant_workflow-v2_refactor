from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class JSONStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self, default: Any = None) -> Any:
        if not self.path.exists():
            return default
        try:
            return json.loads(self.path.read_text(encoding="utf-8-sig"))
        except Exception:
            backup = self.path.with_suffix(self.path.suffix + ".broken." + datetime.now().strftime("%Y%m%d_%H%M%S"))
            try:
                backup.write_bytes(self.path.read_bytes())
            except Exception:
                pass
            return default

    def save(self, payload: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)
