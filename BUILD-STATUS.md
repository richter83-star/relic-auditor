# Build status

The Relic Auditor 1.0.0 Windows distribution and Resurrection Mode engine are built, verified, and ready.

## Verified locally

- Version bumped to `1.0.0` in `src/relic_auditor/__init__.py`, `pyproject.toml`, and Inno Setup configuration.
- Full test suite passes: 275 tests passed, 0 failures.
- PyInstaller compilation completed cleanly for `relic-cli` and `Relic Auditor` GUI.
- Smoke tests verified on compiled `dist/relic-cli/relic.exe` (1.0.0):
  - `relic.exe --version` outputs `relic 1.0.0`.
  - `relic.exe resurrect` executes deterministic subgraph extraction, evaluates the salvageability gate, formats real-time market contexts, and writes JSON/Markdown plans with secret redaction.


## Windows build result

GitHub Actions run
[`30589898811`](https://github.com/richter83-star/relic-auditor/actions/runs/30589898811)
completed successfully on `windows-latest`.

- Installer: `Relic-Auditor-Setup-0.8.3-x64.exe`
- Size: `69,242,848` bytes
- SHA-256: `0f1d1efe8375772d8ff23ad959cc96867174e7d0e4becded663933b09927daeb`
- Source tests: passed
- Bundled CLI/GUI smoke tests: passed
- Clean install and installed CLI/GUI smoke tests: passed
- Uninstall, user-config preservation, and PATH cleanup: passed
- Authenticode: `NotSigned`

The unsigned build is suitable for internal testing. Windows SmartScreen may
warn until a trusted signing certificate is configured.
