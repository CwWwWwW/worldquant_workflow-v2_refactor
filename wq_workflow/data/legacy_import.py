from __future__ import annotations

from typing import Any


class LegacyImportRepository:
    def __init__(self, storage: Any | None = None, logger: Any | None = None) -> None:
        self.storage = storage
        self.logger = logger

    def run_legacy_full_import_once(self) -> dict[str, Any]:
        if self.storage is None:
            return {"ok": False, "reason": "storage_unavailable"}
        try:
            from wq_workflow.storage.legacy_full_importer import run_legacy_full_import_once

            result = run_legacy_full_import_once(self.storage)
            return result if isinstance(result, dict) else {"ok": True, "result": result}
        except ImportError:
            return {"ok": False, "reason": "legacy_importer_unavailable"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def check_legacy_import_status(self) -> dict[str, Any]:
        try:
            meta = getattr(self.storage, "meta", None)
            if meta is not None and hasattr(meta, "get"):
                return {"legacy_full_import_completed": bool(meta.get("legacy_full_import_completed", False))}
        except Exception:
            pass
        return {"legacy_full_import_completed": False}
