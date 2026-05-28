# Release Process

## CI Safety Gate

Current CI validates source compilation and release artifact hygiene. Full pytest is kept as a local/pre-release diagnostic gate until the existing environment-dependent/core test failures are stabilized in a dedicated change.

The CI workflow currently checks:

- dependency installation from `requirements.txt`
- `python -m compileall wq_workflow tools`
- `python tools/build_release.py --version ci`
- release zip hygiene for local config, secrets, runtime state, logs, databases, screenshots, cookies, tokens, and browser artifacts

CI intentionally does not run the complete pytest suite yet. Do not treat this as a claim that all tests pass.

## GitHub Releases

Release artifacts are built by `tools/build_release.py` and uploaded from `dist/*.zip`. The release archive name is `alphaforge-<version>.zip`, and the zip root directory is `alphaforge-<version>/`.

The release workflow only runs for pushed tags matching `v*`. It does not run on normal `main` pushes, does not publish GitHub Packages, and does not build Docker images.

## Pre-release Checklist

Before publishing a tag, run locally:

```bash
python -m compileall wq_workflow tools
python tools/build_release.py --version <tag>
```

Full pytest should be used as a local diagnostic gate and its failures should be reviewed before important releases. Existing environment-dependent/core test failures should be stabilized in a dedicated core-test change, not hidden by repository maintenance changes.
