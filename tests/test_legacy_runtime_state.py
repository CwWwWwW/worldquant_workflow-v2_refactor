from __future__ import annotations

from wq_workflow.legacy_bridge.runtime_state import RuntimeStateReader, RuntimeStateWriter
from wq_workflow.legacy_bridge.schema import RuntimeStateSnapshot


def test_runtime_state_writer_reader_and_stale(tmp_path):
    path = tmp_path / "runtime/status/runtime_state.json"
    writer = RuntimeStateWriter(path)
    assert writer.write_snapshot(RuntimeStateSnapshot(current_state="WAIT_RESULT", current_iteration=2)) is True
    ok, snapshot, warnings = RuntimeStateReader(path).read_snapshot()
    assert ok and snapshot and snapshot.current_state == "WAIT_RESULT" and warnings == []
    assert RuntimeStateReader(path).is_stale(999999) is False


def test_runtime_state_reader_corrupt_not_fatal(tmp_path):
    path = tmp_path / "runtime/status/runtime_state.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    ok, snapshot, warnings = RuntimeStateReader(path).read_snapshot()
    assert ok is False and snapshot is None and warnings


def test_runtime_state_write_fail_open_disabled_and_no_db(tmp_path):
    path = tmp_path / "runtime/status/runtime_state.json"
    writer = RuntimeStateWriter(path, enabled=False)
    assert writer.write_snapshot(RuntimeStateSnapshot()) is False
    result = writer.write_fail_open({"current_state": "IDLE"})
    assert result["ok"] is True
    assert not (tmp_path / "runtime/db/workflow.db").exists()
