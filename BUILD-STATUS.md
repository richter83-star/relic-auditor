# Build status

Relic Auditor `1.0.0` source contains the new Resurrection Mode work, but the current `main` lineage is **not yet release-verified as a Windows 1.0.0 distribution**.

This file previously cited GitHub Actions run `30589898811` as v1.0.0 Windows validation. That was incorrect: the run belongs to the older v0.8.x installer line and cannot be used as evidence for v1.0.0.

## Verified locally for the current v1 source

- Version metadata is `1.0.0` in `src/relic_auditor/__init__.py`, `pyproject.toml`, and Inno Setup configuration.
- The v1 implementation commit reported a local suite result of 275 passed, 1 skipped, 0 failures.
- PyInstaller compilation was reported clean for the `relic-cli` and `Relic Auditor` GUI targets.
- Local compiled CLI smoke checks were reported for:
  - `relic.exe --version` -> `relic 1.0.0`.
  - `relic.exe resurrect` -> deterministic subgraph extraction, salvageability gating, JSON/Markdown output, and secret redaction.
- Resurrection market context is currently a bundled **offline heuristic**. No live market-research adapter is implemented in v1.0.0.

These are local-development assertions from the current lineage. They are not a substitute for a clean GitHub Actions Windows release gate.

## Windows v1.0.0 status

**Pending fresh validation.**

The repository still contains legacy v0.8.x workflow/build assumptions that must not be presented as v1 evidence. A new v1 Windows run must verify the exact v1 source and installer before this status can be changed to release-ready.

Required v1 Windows gates:

- complete source test suite on `windows-latest`;
- bundled CLI and GUI smoke tests;
- clean installation of `Relic-Auditor-Setup-1.0.0-x64.exe`;
- in-place upgrade/reinstall behavior;
- installed CLI and GUI smoke tests;
- stale-runtime cleanup;
- user configuration preservation;
- PATH cleanup and uninstall;
- SHA-256 recording for the exact installer artifact;
- Authenticode status recording.

## Lineage reconciliation required

The validated `installer/v0.12.0` lineage contains later Product Builder Bridge, Assisted Build Supervisor, licensing, updater, and release-hardening work that is not present on the current `main` v1 lineage. The two histories do not share a normal merge ancestry.

Before declaring a final v1 release, preserve the v0.12 functionality and integrate the current Resurrection/Technical Truth improvements into one authoritative lineage, then run the combined test and Windows installer gates.

## Signing

Current known internal installer builds are unsigned. Unsigned builds may be used for manual internal testing, but must not be described as production update artifacts. The secure updater design from the v0.12 line correctly requires trusted signing before automatic installation.
