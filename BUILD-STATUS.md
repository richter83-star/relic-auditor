# Build status

Relic Auditor 0.10.2 is a local release candidate based on the verified
v0.10.1 source archive.

## Implemented

- strict stable-channel update manifest and semantic version comparison
- bounded HTTPS installer download with atomic finalization
- exact size and SHA-256 verification
- pinned Dracanus AI Authenticode verification and pre-launch recheck
- visible manual update check and cadence-limited checks in installed builds
- three-step download, verify, and install dialog
- same-AppId in-place installer upgrade with managed runtime cleanup
- clean-install, repeat-install, configuration-preservation, and uninstall gates

## Local verification

- updater unit tests pass
- available non-GUI source suite passes
- Python sources compile
- deterministic source archive, wheel, and sdist can be generated

## Remaining release gates

- commit/push approval
- complete GitHub Actions Windows source and frozen-source suites
- bundled and installed GUI/CLI smoke tests
- repeat-install and stale-runtime cleanup verification on Windows
- permanent public update endpoint
- trusted Dracanus AI code-signing certificate

The updater will not launch an unsigned installer. Until signing and permanent
hosting are configured, manual installation remains the internal-test path.
