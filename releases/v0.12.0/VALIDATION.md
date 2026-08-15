# Relic Auditor 0.12.0 release-candidate validation

Validation date: 2026-08-15

## Completed locally

- 324 available non-GUI tests passed and 2 were skipped.
- 69 focused updater, licensing, supervisor, cancellation, and provider-health
  tests passed.
- The real default process runner was cancelled during a test, its child
  process tree terminated, and its checkpoint restored.
- Python byte compilation and `git diff --check` passed.
- `relic --version` returned `relic 0.12.0` from source and the unpacked wheel.
- The unpacked wheel preserved empty production trust roots and accepted only
  the exact Codex production profile.
- Frozen source and wheel reproduced byte-for-byte under a fixed source epoch.
- The sdist was normalized to sorted entries, fixed timestamps and ownership,
  and a deterministic gzip header; two independent outputs matched.

## Windows workflow

The installed PySide6 build cannot import QtGui because `libEGL.so.1` is not
available. Four GUI suites were therefore excluded rather than falsely
reported as passed locally.

GitHub Actions run `31901610921` subsequently verified the frozen source hash,
ran the complete Windows suite without exclusions, built both executables, and
passed bundled CLI/GUI smoke, clean install, in-place upgrade, stale-runtime
cleanup, configuration preservation, PATH cleanup, and uninstall checks from
commit `cfe1f0c0f545d0ecdc74a5a97b53b772292054cd`.

Verified Windows installer:

- File: `Relic-Auditor-Setup-0.12.0-x64.exe`
- Size: `74,225,494` bytes
- SHA-256: `5d5c8747eff13a1f0360152f0c9e2faeb2691cacc322dc37bb0f8b19a6870229`
- Authenticode: `NotSigned`
- Workflow artifact: `9251297173`
- Artifact ZIP size: `74,229,717` bytes
- Artifact ZIP SHA-256: `20a6ec4b42aa28a427bdc8de7f556641e77ad16a5c4f0da57e813ae24c488bf4`

The unsigned installer is verified for manual RC testing. The secure in-app
updater correctly refuses automatic installation until an Authenticode-signed
installer and matching signed stable update manifest are provisioned.

## Artifact identifiers

- Frozen source ZIP: `a5c0b6f90b18b6198a9c10af8c57b2fd54ee82054c1e3f16b6f4bf3bf22df732`
- Wheel: `8a6145f38d8349fea96e226da45c59b62223eee2e69bc12b4fd44b02dc30b398`
- Source distribution: `1e05520e871941762258fec0c3710cdad498693886f3e5c434dfc168ddbeecc7`

## External gates

- Windows workflow: passed for the published branch RC.
- Authenticode certificate: not provisioned.
- Update and license public keys/services: not provisioned.
- Permanent stable-manifest and installer hosting: not provisioned.
- Tag and GitHub Release: intentionally not created.
