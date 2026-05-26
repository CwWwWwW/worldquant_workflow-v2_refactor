from __future__ import annotations

from types import SimpleNamespace

from wq_workflow.observability.source_adapters import WorkflowStatusAdapter, _read_csv_tail, read_text_tail


def test_read_csv_tail_uses_bounded_tail_and_preserves_header(tmp_path):
    path = tmp_path / "iteration_log.csv"
    rows = ["time,success,stage"]
    for idx in range(20_000):
        rows.append(f"t{idx},{'true' if idx >= 19_990 else 'false'},s{idx}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    tail_text = read_text_tail(path, max_bytes=1024)
    assert "t0," not in tail_text
    tail_rows = _read_csv_tail(path, limit=5, max_bytes=1024)
    assert [row["time"] for row in tail_rows] == [f"t{idx}" for idx in range(19_995, 20_000)]


def test_workflow_adapter_large_iteration_log_fail_open(tmp_path):
    path = tmp_path / "iteration_log.csv"
    path.write_text("time,success,stage\n" + "\n".join(f"t{i},true,s" for i in range(1000)), encoding="utf-8")
    result = WorkflowStatusAdapter(config=SimpleNamespace(storage_db_path=str(tmp_path / "missing.db")), root=tmp_path).collect()
    names = {metric["metric_name"]: metric["value"] for metric in result["metrics"]}
    assert names["workflow.recent_success_count"] == 100
    assert names["workflow.recent_failure_count"] == 0


def test_csv_tail_missing_and_encoding_errors_are_nonfatal(tmp_path):
    assert read_text_tail(tmp_path / "missing.csv") == ""
    bad = tmp_path / "bad.csv"
    bad.write_bytes(b"time,success\n\xff,true\n")
    assert _read_csv_tail(bad, limit=10)[0]["success"] == "true"
