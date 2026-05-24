from __future__ import annotations


def log_export_menu() -> int:
    from wq_workflow import cli_legacy

    return int(cli_legacy.log_export_menu())


def log_import_menu() -> int:
    from wq_workflow import cli_legacy

    return int(cli_legacy.log_import_menu())
