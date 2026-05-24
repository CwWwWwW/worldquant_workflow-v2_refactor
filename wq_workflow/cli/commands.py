from __future__ import annotations


def run_command(args: list[str] | None = None, guided: bool = False) -> int:
    from wq_workflow import cli_legacy

    return int(cli_legacy.run_command(args or [], guided=guided))


def split_command(args: list[str] | None = None) -> int:
    from wq_workflow import cli_legacy

    return int(cli_legacy.split_command(args or []))


def status_command() -> int:
    from wq_workflow import cli_legacy

    return int(cli_legacy.status_command())


def init_command() -> int:
    from wq_workflow import cli_legacy

    return int(cli_legacy.init_command())
