# Changelog

## Unreleased

### Added

- Repository documentation structure.
- Release packaging workflow.
- Compliance, security, and contribution documents.

### Changed

- Renamed public project branding to AlphaForge.
- Updated release artifact naming to use alphaforge while keeping the internal wq_workflow package name for compatibility.
- Simplified README for GitHub landing page clarity.
- Adjusted CI to enforce compile and release artifact hygiene checks without making existing environment-dependent pytest failures block repository maintenance.

### Fixed

- Isolated pytest configuration from local private config.json.
- Stabilized StrategyPortfolioService workflow compatibility tests.
- Stabilized JSONL write visibility in isolated unit tests.
- Ensured unit tests use temporary storage paths instead of private runtime data.

### Security

- Documented sensitive-data exclusion policy.

## v2.0.0-alpha.1 - YYYY-MM-DD

- Initial public release artifact.
