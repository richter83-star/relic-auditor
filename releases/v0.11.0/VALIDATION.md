# Relic Auditor 0.11.0 local validation

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

## Environment-specific gate still required

The Linux runner does not provide the `libEGL.so.1` system library required to
import PySide6 QtGui, so GUI execution was not falsely reported as passed.
The frozen archive includes all GUI suites, including the new five-step
supervisor and unprovisioned-license tests. The Windows installer workflow must
run the complete suite, build both executables, run clean-install/in-place-
upgrade/uninstall checks, and upload the workflow artifact before this RC can
be considered Windows-verified.

## Artifact identifiers

- Frozen source ZIP: `5fbfedd72b61f97def61691200e9c40b61a6a5309f34e4882051db2a2e675e70`
- Wheel: `aee1b39d248d1208923998f15513e89235c6e7bf97d3a91e9b14f1b8e767fe2a`
- Source distribution: `6503c00137e583f3345c23d64b25001826ecd4499783386b7199c5b919dd0a88`
