from __future__ import annotations


def test_cli_help_entry_compat(capsys):
    from wq_workflow.cli import main

    rc = main(["--help"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "run" in out.lower() or "help" in out.lower()
