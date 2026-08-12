# Build status

The Relic Auditor 0.8.3 Windows installer source and release automation are ready for the verified GitHub Actions build.

## Verified locally

- Frozen v0.8.3 archive SHA-256 matches `1f3a20833ff454c08a681a1fb6dc6dfd8888992f7383045544dc98d0b5ba794f`.
- Installer source safeguards pass.
- Python entry points compile.
- Icon and Inno Setup wizard assets render correctly.
- No Relic analysis-engine file was modified.

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
