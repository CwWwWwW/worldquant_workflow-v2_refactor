from __future__ import annotations

import json
import subprocess
import sys


def test_cli_final_status_json_and_flags():
    result = subprocess.run([sys.executable, "tools/show_final_status.py", "--json", "--no-db", "--no-logs"], text=True, capture_output=True, check=True)
    payload = json.loads(result.stdout)
    assert "runtime" in payload and "sources" in payload


def test_cli_final_status_compact_verbose_limit():
    compact = subprocess.run([sys.executable, "tools/show_final_status.py", "--no-db", "--no-logs"], text=True, capture_output=True, check=True)
    assert "Runtime:" in compact.stdout
    verbose = subprocess.run([sys.executable, "tools/show_final_status.py", "--verbose", "--limit", "2", "--no-db"], text=True, capture_output=True, check=True)
    assert "Recent events:" in verbose.stdout
