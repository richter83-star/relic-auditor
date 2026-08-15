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

## Not runnable in this Linux environment

The installed PySide6 build cannot import QtGui because `libEGL.so.1` is not
available. Four GUI suites were therefore excluded rather than falsely
reported as passed. The Windows workflow must run the complete source and
frozen-source suites, both GUI/CLI smoke tests, clean install, in-place upgrade,
stale-runtime cleanup, configuration preservation, PATH cleanup, and uninstall.

## Artifact identifiers

- Frozen source ZIP: `a5c0b6f90b18b6198a9c10af8c57b2fd54ee82054c1e3f16b6f4bf3bf22df732`
- Wheel: `8a6145f38d8349fea96e226da45c59b62223eee2e69bc12b4fd44b02dc30b398`
- Source distribution: `1e05520e871941762258fec0c3710cdad498693886f3e5c434dfc168ddbeecc7`

## External gates

- Windows workflow: not run for this local RC.
- Authenticode certificate: not provisioned.
- Update and license public keys/services: not provisioned.
- Permanent stable-manifest and installer hosting: not provisioned.
- Tag and GitHub Release: intentionally not created.
