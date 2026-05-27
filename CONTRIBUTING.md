# Contributing

Before contributing:

1. Do not commit credentials, cookies, API keys, runtime databases, logs, screenshots, or private alpha results.
2. Keep production defaults conservative.
3. Do not make refactored/shadow/advisory components silently take over production execution.
4. Preserve compatibility with existing logs, runtime state, and memory imports.
5. Run tests before submitting changes:

   ```bash
   python -m pytest
   ```

Pull request checklist:

- [ ] No secrets or private runtime data committed.
- [ ] Tests pass.
- [ ] README/docs updated if behavior changed.
- [ ] Production defaults remain safe.
- [ ] No Submit automation introduced.
