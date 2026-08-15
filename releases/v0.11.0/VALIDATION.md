# Relic Auditor 0.11.0 release-candidate validation

Validation date: 2026-08-15

## Completed in the Linux build environment

- 310 non-GUI/non-installer tests were collected.
- 309 passed and 1 was skipped.
- 44 focused v0.11 licensing, supervisor, rollback, tamper, and CLI lifecycle
  tests passed.
- Python byte compilation completed successfully.
- `git diff --check` completed successfully.
- `relic --version` returned `relic 0.11.0`.
- `relic license status --json` failed closed to Free with only audit and
  activation-client capabilities.
- The wheel and source distribution built successfully.
- The frozen source ZIP reproduced byte-for-byte on a second build.

## Windows workflow

The Linux runner does not provide the `libEGL.so.1` system library required to
import PySide6 QtGui, so GUI execution was not falsely reported as passed.
GitHub Actions run `31898548266` subsequently verified the frozen source hash,
ran the complete Windows suite, built both executables, passed clean-install,
repeat-install, CLI/GUI smoke, and uninstall checks, and uploaded the installer
artifact from commit `c3321550fd8906ca61f112ede1c87d8b7f8c56e1`.

Verified Windows installer:

- File: `Relic-Auditor-Setup-0.11.0-x64.exe`
- Size: `74,195,364` bytes
- SHA-256: `c0016dbe82370ce8b34e3362c95283a84d32653ea5afd0073ab2f004a414f64f`
- Authenticode: `NotSigned`
- Workflow artifact: `9250519145`
- Artifact ZIP SHA-256: `5568a5ee47f4ff8a6d91e68b2e15bd78307b7139647d1c19d80185d94a66ee40`

The unsigned installer is verified for manual RC testing. The secure in-app
updater correctly refuses automatic installation until an Authenticode-signed
installer and matching stable update manifest are provisioned.

## Artifact identifiers

- Frozen source ZIP: `5fbfedd72b61f97def61691200e9c40b61a6a5309f34e4882051db2a2e675e70`
- Wheel: `aee1b39d248d1208923998f15513e89235c6e7bf97d3a91e9b14f1b8e767fe2a`
- Source distribution: `6503c00137e583f3345c23d64b25001826ecd4499783386b7199c5b919dd0a88`
