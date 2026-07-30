# Build status

The Relic Auditor 0.8.2 Windows installer source and release automation are complete.

## Verified locally

- Frozen v0.8.2 archive SHA-256 matches `de4b55657b60074cdf70fc0c01a116c75425324bcdda93f1ec777ae7e3582ff1`.
- Installer source safeguards pass.
- Python entry points compile.
- Icon and Inno Setup wizard assets render correctly.
- No Relic analysis-engine file was modified.

## Windows build result

GitHub Actions run
[`30589898811`](https://github.com/richter83-star/relic-auditor/actions/runs/30589898811)
completed successfully on `windows-latest`.

- Installer: `Relic-Auditor-Setup-0.8.2-x64.exe`
- Size: `69,242,848` bytes
- SHA-256: `0f1d1efe8375772d8ff23ad959cc96867174e7d0e4becded663933b09927daeb`
- Source tests: passed
- Bundled CLI/GUI smoke tests: passed
- Clean install and installed CLI/GUI smoke tests: passed
- Uninstall, user-config preservation, and PATH cleanup: passed
- Authenticode: `NotSigned`

The unsigned build is suitable for internal testing. Windows SmartScreen may
warn until a trusted signing certificate is configured.
