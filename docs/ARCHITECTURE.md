# Architecture

## Legacy Official Workflow

The legacy official workflow is the current production default path. It owns stable execution of the existing main workflow and remains the safe operational baseline.

## Refactored Pipeline

The refactored pipeline is a structured modernization path. It remains shadow/advisory unless explicitly enabled and must not silently take over production execution.

## Runtime State and Database

`runtime/db` and related runtime folders are local state. They are not part of the public repository or release artifact.

The project is designed to remain compatible with historical logs, memory imports, runtime state, cache, lineage, reward history, and candidate pool data. Runtime databases and execution artifacts are private local state.

## Learning / Evolution Layer

Learning and evolution components support candidate selection, strategy observation, and experience accumulation. They do not change the Submit boundary and should remain controlled by explicit configuration gates.

## Dashboard / Observability

Dashboard, final status, and observability readers are for state inspection. They should avoid competing with the main workflow for writes, remain read-only where applicable, and fail open on missing, stale, corrupt, or locked local state.
