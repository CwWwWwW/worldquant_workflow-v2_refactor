from __future__ import annotations


def menu_command() -> int:
    from wq_workflow import cli_legacy

    return int(cli_legacy.menu_command())


def workflow_menu() -> int:
    from wq_workflow import cli_legacy

    return int(cli_legacy.workflow_menu())
