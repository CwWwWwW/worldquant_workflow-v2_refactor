from __future__ import annotations

from typing import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Compatible CLI entrypoint.

    The legacy menu implementation is preserved in ``wq_workflow.cli_legacy``;
    this package keeps the public ``wq_workflow.cli`` import stable while the
    refactored app/services become the only new code path for lower layers.
    """
    from wq_workflow import cli_legacy

    args = None if argv is None else list(argv)
    return int(cli_legacy.main(args))
