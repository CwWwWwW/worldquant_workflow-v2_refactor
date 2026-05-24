from __future__ import annotations

import json
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterator

from .manifest import load_manifest, manifest_entries, save_manifest
from .models import ReplayEvent
from .parsers.csv_parser import iter_csv_rows
from .parsers.jsonl_parser import iter_jsonl
from .parsers.log_parser import parse_log_line


def replay_logs(
    source: str | Path,
    output_path: str | Path | None = None,
    selectors: dict[str, Any] | None = None,
) -> list[ReplayEvent]:
    source_path = Path(source).resolve()
    temp_dir: Path | None = None
    try:
        export_dir = _resolve_export_dir(source_path)
        if export_dir is None:
            temp_dir = Path(tempfile.mkdtemp(prefix="log_manager_replay_"))
            export_dir = _extract_archive(source_path, temp_dir)
        events = list(iter_replay_events(export_dir, selectors=selectors or {}))
        events.sort(key=lambda item: item.timestamp or "")
        if output_path:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("w", encoding="utf-8") as fh:
                for event in events:
                    fh.write(json.dumps(event.to_dict(), ensure_ascii=False, default=str) + "\n")
            summary_path = out.with_name("replay_summary.json")
            save_manifest(summary_path, _summary(events))
        return events
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


def iter_replay_events(export_dir: Path, selectors: dict[str, Any] | None = None) -> Iterator[ReplayEvent]:
    selectors = selectors or {}
    manifest = load_manifest(export_dir / "manifest.json")
    for entry in manifest_entries(manifest):
        path = export_dir / "files" / entry.relative_path
        if not path.exists():
            continue
        parser = entry.parser
        if parser in {"jsonl", "reward"} or path.suffix.lower() == ".jsonl":
            yield from _jsonl_events(path, entry.relative_path, selectors)
        elif parser == "csv" or path.suffix.lower() == ".csv":
            yield from _csv_events(path, entry.relative_path, selectors)
        elif parser == "json" or path.suffix.lower() == ".json":
            yield from _json_events(path, entry.relative_path, selectors)
        elif parser == "log" or path.suffix.lower() == ".log":
            yield from _log_events(path, entry.relative_path, selectors)


def _jsonl_events(path: Path, rel: str, selectors: dict[str, Any]) -> Iterator[ReplayEvent]:
    for line_no, _raw, payload, error in iter_jsonl(path):
        if not payload:
            if error:
                payload = {"error": error}
            else:
                continue
        event = _event_from_payload(payload, rel, line_no)
        if _selected(event, selectors):
            yield event


def _json_events(path: Path, rel: str, selectors: dict[str, Any]) -> Iterator[ReplayEvent]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        event = ReplayEvent("", _source_for_path(rel), "json_error", "", "", {"error": str(exc)}, rel, 0)
        if _selected(event, selectors):
            yield event
        return
    if isinstance(payload, dict) and payload.get("schema") == "workflow_sqlite_snapshot_v1":
        yield from _sqlite_snapshot_events(payload, rel, selectors)
        return
    if isinstance(payload, list):
        for index, row in enumerate(payload, start=1):
            event = _event_from_payload(row if isinstance(row, dict) else {"value": row}, rel, index)
            if _selected(event, selectors):
                yield event
    elif isinstance(payload, dict):
        event = _event_from_payload(payload, rel, 1)
        if _selected(event, selectors):
            yield event


def _sqlite_snapshot_events(payload: dict[str, Any], rel: str, selectors: dict[str, Any]) -> Iterator[ReplayEvent]:
    events = payload.get("events") if isinstance(payload.get("events"), list) else []
    for index, row in enumerate(events, start=1):
        if not isinstance(row, dict):
            continue
        event_payload = row.get("payload") if isinstance(row.get("payload"), dict) else dict(row)
        event = ReplayEvent(
            timestamp=str(row.get("timestamp") or event_payload.get("time") or event_payload.get("timestamp") or ""),
            source=str(row.get("source") or _source_for_path(str(row.get("original_path") or rel), event_payload)),
            event_type=str(row.get("event_type") or event_payload.get("event") or event_payload.get("action") or "log"),
            alpha_id=str(row.get("alpha_id") or event_payload.get("alpha_id") or event_payload.get("alpha_name") or ""),
            state=str(row.get("state") or event_payload.get("state") or event_payload.get("current_state") or ""),
            payload=event_payload,
            original_path=str(row.get("original_path") or rel),
            line_no=int(row.get("line_no") or index),
        )
        if _selected(event, selectors):
            yield event


def _csv_events(path: Path, rel: str, selectors: dict[str, Any]) -> Iterator[ReplayEvent]:
    for line_no, row, error in iter_csv_rows(path):
        payload: dict[str, Any] = dict(row)
        if error:
            payload["error"] = error
        event = _event_from_payload(payload, rel, line_no)
        if _selected(event, selectors):
            yield event


def _log_events(path: Path, rel: str, selectors: dict[str, Any]) -> Iterator[ReplayEvent]:
    with path.open("r", encoding="utf-8-sig", errors="replace") as fh:
        for line_no, line in enumerate(fh, start=1):
            parsed = parse_log_line(line)
            event = ReplayEvent(
                timestamp=parsed.get("timestamp", ""),
                source=parsed.get("source", _source_for_path(rel)),
                event_type=_event_type_for_message(parsed.get("message", "")),
                alpha_id=_extract_alpha(parsed.get("message", "")),
                state="",
                payload=parsed,
                original_path=rel,
                line_no=line_no,
            )
            if _selected(event, selectors):
                yield event


def _event_from_payload(payload: dict[str, Any], rel: str, line_no: int) -> ReplayEvent:
    source = _source_for_path(rel, payload)
    event_type = str(
        payload.get("event")
        or payload.get("action")
        or payload.get("mutation_type")
        or ("snapshot" if rel.endswith(".json") else "log")
    )
    return ReplayEvent(
        timestamp=str(payload.get("time") or payload.get("timestamp") or payload.get("created_at") or ""),
        source=source,
        event_type=event_type,
        alpha_id=str(payload.get("alpha_id") or payload.get("alpha_name") or ""),
        state=str(payload.get("state") or payload.get("current_state") or ""),
        payload=payload,
        original_path=rel,
        line_no=line_no,
    )


def _source_for_path(rel: str, payload: dict[str, Any] | None = None) -> str:
    lower = rel.lower()
    payload = payload or {}
    if "migration" in lower or payload.get("action") in {"rollback", "transition", "blend"}:
        return "migration"
    if "reward" in lower or "legacy_reward" in payload or "v2_reward" in payload:
        return "reward"
    if "sidecar" in lower or "ast_evolution_failures" in lower:
        return "sidecar"
    if "candidate_pool" in lower:
        return "candidate"
    if "alpha_lineage" in lower:
        return "population"
    if "workflow_state" in lower:
        return "simulate"
    if lower.endswith(".csv"):
        return "simulate"
    return "workflow"


def _event_type_for_message(message: str) -> str:
    value = message.lower()
    if "state_enter" in value:
        return "STATE_ENTER"
    if "state_exit" in value:
        return "STATE_EXIT"
    if "rollback" in value:
        return "rollback"
    if "reward" in value:
        return "reward"
    if "repair" in value:
        return "repair"
    return "log"


def _extract_alpha(message: str) -> str:
    for token in message.replace(",", " ").split():
        if token.lower().startswith("auto_alpha") or token.lower().startswith("alpha"):
            return token
    return ""


def _selected(event: ReplayEvent, selectors: dict[str, Any]) -> bool:
    for key in ["alpha_id", "source", "event_type"]:
        value = selectors.get(key)
        if value and getattr(event, key) != str(value):
            return False
    return True


def _summary(events: list[ReplayEvent]) -> dict[str, Any]:
    by_source: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for event in events:
        by_source[event.source] = by_source.get(event.source, 0) + 1
        by_type[event.event_type] = by_type.get(event.event_type, 0) + 1
    return {"event_count": len(events), "by_source": by_source, "by_type": by_type}


def _resolve_export_dir(source: Path) -> Path | None:
    if source.is_dir():
        if (source / "manifest.json").exists():
            return source
        candidates = [path for path in source.iterdir() if path.is_dir() and (path / "manifest.json").exists()]
        if candidates:
            return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)[0]
    return None


def _extract_archive(source: Path, temp_dir: Path) -> Path:
    archive = _recombine_if_part(source, temp_dir)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zf:
            _safe_extract_zip(zf, temp_dir)
    elif tarfile.is_tarfile(archive):
        with tarfile.open(archive) as tf:
            _safe_extract_tar(tf, temp_dir)
    else:
        raise ValueError(f"unsupported archive: {source}")
    resolved = _resolve_export_dir(temp_dir)
    if resolved is None:
        raise FileNotFoundError("manifest not found in archive")
    return resolved


def _recombine_if_part(source: Path, temp_dir: Path) -> Path:
    if ".part" not in source.name:
        return source
    prefix = source.name.split(".part", 1)[0]
    parts = sorted(source.parent.glob(f"{prefix}.part*"))
    combined = temp_dir / prefix
    with combined.open("wb") as dst:
        for part in parts:
            with part.open("rb") as src:
                shutil.copyfileobj(src, dst, length=4 * 1024 * 1024)
    return combined


def _safe_extract_zip(zf: zipfile.ZipFile, target: Path) -> None:
    target_root = target.resolve()
    for member in zf.infolist():
        destination = (target / member.filename).resolve()
        if target_root not in [destination, *destination.parents]:
            raise ValueError(f"unsafe archive path: {member.filename}")
    zf.extractall(target)


def _safe_extract_tar(tf: tarfile.TarFile, target: Path) -> None:
    target_root = target.resolve()
    for member in tf.getmembers():
        destination = (target / member.name).resolve()
        if target_root not in [destination, *destination.parents]:
            raise ValueError(f"unsafe archive path: {member.name}")
    tf.extractall(target)
