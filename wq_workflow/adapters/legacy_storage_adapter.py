from __future__ import annotations


def initialize_schema(conn):
    from wq_workflow.storage.schema import initialize_schema as _initialize_schema

    return _initialize_schema(conn)
