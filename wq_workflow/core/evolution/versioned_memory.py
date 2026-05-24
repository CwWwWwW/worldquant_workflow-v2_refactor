from __future__ import annotations

import atexit
import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Any

from memory.file_locks import lock_for_memory_path

from ...paths import ROOT
from ...safe_io import safe_json_value, safe_read_json


EVOLUTION_MEMORY_VERSION = "1.1.6"


class VersionedEvolutionMemory:
    def __init__(
        self,
        path: Path,
        *,
        default_data: Any | None = None,
        extra_defaults: dict[str, Any] | None = None,
        async_flush: bool = True,
    ) -> None:
        self.path = Path(path)
        self.default_data = {} if default_data is None else default_data
        self.extra_defaults = dict(extra_defaults or {})
        self.async_flush = async_flush and self._is_runtime_path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = lock_for_memory_path(self.path)
        self._flush_event = threading.Event()
        self._stop_event = threading.Event()
        self._pending_payload: dict[str, Any] | None = None
        self._worker: threading.Thread | None = None
        if self.async_flush:
            self._worker = threading.Thread(target=self._flush_loop, name=f"evolution-memory-{self.path.name}", daemon=True)
            self._worker.start()
            atexit.register(self.close)
        if not self.path.exists():
            self.save_data(self.default_data, flush=True)

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def load_payload(self) -> dict[str, Any]:
        with self._lock:
            if self._pending_payload is not None:
                return dict(self._pending_payload)
            payload = safe_read_json(self.path, self._wrapped(self.default_data))
        if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            result = dict(payload)
            result.setdefault("version", EVOLUTION_MEMORY_VERSION)
            for key, value in self.extra_defaults.items():
                result.setdefault(key, value)
            return result
        if isinstance(payload, dict):
            return self._wrapped(payload)
        return self._wrapped(self.default_data)

    def load_data(self) -> dict[str, Any]:
        data = self.load_payload().get("data", {})
        return data if isinstance(data, dict) else {}

    def load_meta(self) -> dict[str, Any]:
        payload = self.load_payload()
        return {key: value for key, value in payload.items() if key not in {"version", "data"}}

    def save_data(self, data: dict[str, Any], *, meta: dict[str, Any] | None = None, flush: bool = False) -> None:
        payload = self._wrapped(data, meta=meta)
        self.save_payload(payload, flush=flush)

    def save_payload(self, payload: dict[str, Any], *, flush: bool = False) -> None:
        wrapped = dict(payload)
        wrapped["version"] = str(wrapped.get("version") or EVOLUTION_MEMORY_VERSION)
        data = wrapped.get("data", {})
        wrapped["data"] = data if isinstance(data, dict) else {}
        for key, value in self.extra_defaults.items():
            wrapped.setdefault(key, value)
        if flush or not self.async_flush:
            self._write_payload(wrapped)
            return
        with self._lock:
            self._pending_payload = wrapped
        self._flush_event.set()

    def flush(self) -> None:
        with self._lock:
            payload = self._pending_payload
            self._pending_payload = None
        if payload is not None:
            self._write_payload(payload)

    def close(self) -> None:
        self.flush()
        if self._worker is None:
            return
        self._stop_event.set()
        self._flush_event.set()
        if self._worker.is_alive():
            self._worker.join(timeout=1.0)

    def _wrapped(self, data: Any, *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {"version": EVOLUTION_MEMORY_VERSION, "data": data if isinstance(data, dict) else {}}
        payload.update(self.extra_defaults)
        if meta:
            payload.update(meta)
        return payload

    def _is_runtime_path(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
            root = ROOT.resolve()
        except OSError:
            return False
        return resolved == root or root in resolved.parents

    def _flush_loop(self) -> None:
        while not self._stop_event.is_set():
            self._flush_event.wait(timeout=0.25)
            self._flush_event.clear()
            self.flush()
        self.flush()

    def _write_payload(self, payload: dict[str, Any]) -> None:
        cleaned = safe_json_value(payload)
        backup = self.path.with_suffix(self.path.suffix + ".bak")
        temp = self.path.with_name(f".{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                if self.path.exists():
                    try:
                        shutil.copyfile(self.path, backup)
                    except OSError:
                        logging.info("Failed to backup evolution memory: %s", self.path, exc_info=True)
                with temp.open("w", encoding="utf-8") as fh:
                    import json

                    json.dump(cleaned, fh, ensure_ascii=False, indent=2, allow_nan=False, default=str)
                    fh.write("\n")
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(temp, self.path)
                try:
                    from ...storage import get_storage_manager

                    get_storage_manager().mirror_json_snapshot(self.path, cleaned)
                except Exception:
                    pass
                try:
                    shutil.copyfile(self.path, backup)
                except OSError:
                    logging.info("Failed to refresh evolution memory backup: %s", self.path, exc_info=True)
            except Exception:
                logging.warning("Failed to write evolution memory: %s", self.path, exc_info=True)
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
