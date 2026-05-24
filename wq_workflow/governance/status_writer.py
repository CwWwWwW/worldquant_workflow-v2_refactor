from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .lifecycle import utc_now_iso
from .schema import TaskGovernanceState


class StatusWriter:
    def __init__(self, status_path: str | Path = "runtime/status/governance_status.json", ml_status_path: str | Path | None = "runtime/status/ml_status.json", logger: Any | None = None, root: str | Path | None = None) -> None:
        from wq_workflow.paths import ROOT
        root_path = Path(root or ROOT)
        self.status_path = Path(status_path)
        if not self.status_path.is_absolute():
            self.status_path = root_path / self.status_path
        self.ml_status_path = Path(ml_status_path) if ml_status_path else None
        if self.ml_status_path is not None and not self.ml_status_path.is_absolute():
            self.ml_status_path = root_path / self.ml_status_path
        self.logger = logger

    def _warn(self, message: str, *args: Any) -> None:
        try:
            if self.logger is not None:
                self.logger.warning(message, *args)
        except Exception:
            pass

    def _load(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"tasks": {}, "updated_at": utc_now_iso()}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {"tasks": {}, "updated_at": utc_now_iso()}
        except Exception as exc:
            try:
                backup = path.with_name(f"{path.name}.broken.{utc_now_iso().replace(':','').replace('+','_')}.bak")
                backup.write_text(path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
            except Exception:
                pass
            self._warn("governance status JSON damaged; rebuilding %s: %s", path, exc)
            return {"tasks": {}, "updated_at": utc_now_iso()}

    def _atomic_write(self, path: Path, data: dict[str, Any]) -> bool:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f".{path.name}.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            os.replace(tmp, path)
            return True
        except Exception as exc:
            self._warn("governance status write failed %s: %s", path, exc)
            return False

    def write_task(self, state: TaskGovernanceState | dict[str, Any], *, extra_paths: bool = True) -> bool:
        payload = state.to_dict() if isinstance(state, TaskGovernanceState) else dict(state or {})
        task = str(payload.get("task_name") or "")
        if not task:
            return False
        payload.setdefault("updated_at", utc_now_iso())
        data = self._load(self.status_path)
        tasks = data.get("tasks") if isinstance(data.get("tasks"), dict) else {}
        tasks[task] = payload
        data["tasks"] = tasks
        data["updated_at"] = utc_now_iso()
        ok = self._atomic_write(self.status_path, data)
        if extra_paths and self.ml_status_path is not None:
            ml_data = self._load(self.ml_status_path)
            ml_tasks = ml_data.get("tasks") if isinstance(ml_data.get("tasks"), dict) else {}
            ml_tasks[task] = payload
            ml_data["tasks"] = ml_tasks
            ml_data["updated_at"] = data["updated_at"]
            self._atomic_write(self.ml_status_path, ml_data)
        return ok
