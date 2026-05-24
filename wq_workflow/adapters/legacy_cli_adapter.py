from __future__ import annotations


def main(argv=None) -> int:
    from wq_workflow.cli import main as _main

    return int(_main(argv))
