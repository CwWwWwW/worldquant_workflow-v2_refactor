# Roadmap

## Current Focus

- Stable production path through the legacy official workflow.
- Observability and read-only status reporting.
- Historical log, memory, state, lineage, reward, cache, and candidate pool compatibility.
- Shadow/advisory learning that does not silently take over production execution.

## Near Term

- Clean GitHub Release zip artifacts.
- CI for unit and compatibility tests.
- Deployment and configuration documentation.
- Clear runtime database and key-log backup guidance before production upgrades.

## Long Term

- Optional Docker-based deployment if it becomes operationally useful.
- Possible GitHub Container Registry usage if Docker deployment is introduced.
- More complete replay and evaluation systems while preserving conservative production boundaries.

Packages are not currently the primary distribution mechanism. GitHub Releases with clean zip artifacts remain the preferred release path.
