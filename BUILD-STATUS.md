# Build status

Relic Auditor v1.0.1 is the unified release-candidate line built from the validated v0.12 production foundation plus selectively ported Resurrection and Technical Truth corrections.

This file describes engineering readiness only. It is not a publication, signing, tag, or default-branch claim.

## Unified architecture

The v1.0.1 line contains and preserves:

- deterministic static estate scanning and Technical Truth
- Reusable Assets / Capability Acquisition analysis
- Product Opportunity analysis
- deterministic Build Packs and evidence/provenance controls
- entitlement and OS credential-vault boundaries
- approval-gated Assisted Build Supervisor/runtime
- checkpoint restoration and cancellation controls
- updater and pinned trust-root infrastructure
- optional bounded LLM reasoning and runtime health truth
- standalone `relic resurrect` salvageability analysis
- Windows desktop, CLI, installer, upgrade, cleanup, and uninstall machinery

The scanned target remains read-only. Build execution, where eligible, operates only through separately approved and confined managed-workspace paths.

## Verified reconciliation evidence

The pre-documentation v1.0.1 RC code head `f36791ac1df3e0f8e2068f883bb8907d2dc2bdf0` passed GitHub Actions run `32453060126` on Windows Server 2025 / Python 3.12.

That run verified:

- complete source test suite
- unified CLI smoke
- wheel and sdist construction
- exact-commit frozen source archive and SHA-256 gate
- frozen-source test suite
- PyInstaller GUI and CLI builds
- bundled audit / acquisition / Resurrection smoke
- bundled GUI smoke
- clean Windows install
- installed audit / acquisition / Resurrection smoke
- installed GUI smoke
- user PATH registration
- preservation of pre-existing Relic user configuration
- in-place upgrade
- stale GUI and CLI runtime cleanup
- upgraded CLI version
- silent uninstall
- user configuration preservation after uninstall
- CLI PATH cleanup after uninstall
- release manifest and checksum generation
- workflow artifact upload

For that exact commit, the workflow recorded:

- frozen source SHA-256: `2974e6f2c3b8485278327a23536d2b946435ab55d929d6bcc31d20c1c88a5479`
- installer: `Relic-Auditor-Setup-1.0.1-x64.exe`
- installer SHA-256: `51223411a5de103ff9d2e5df1c746cefe85f7997cd9355c9ccfd68e217ceafe0`
- installer size: `73,927,403` bytes
- Authenticode: `NotSigned`
- uploaded RC artifact ID: `9436396583`
- uploaded RC artifact size: `79,412,406` bytes
- uploaded artifact ZIP SHA-256: `62f825e651243d1b213842117f74a53cd79be1344c44435ee26d94d86f7e1ab2`

The workflow artifact contains `release-manifest.json`, `SHA256SUMS.txt`, the exact frozen source ZIP, installer README, and installer executable. The release manifest is authoritative for the artifact it accompanies.

## After documentation changes

Any commit after the verified head changes the frozen source archive, even when the code is unchanged. Therefore the exact-head Windows RC workflow must be green again before that later commit can be treated as the final release source. Do not reuse the hashes above for a different commit.

## Remaining publication gates

Engineering validation is not the same thing as public release authorization. The remaining gates are:

1. green exact-head RC validation after the final documentation commit;
2. explicit decision on how the disconnected default `main` history will be reconciled;
3. repository branch protection / required checks on the authoritative line;
4. production Authenticode signing and trusted stable-update manifest if automatic updating is to be enabled;
5. explicit authorization before any merge to `main`, default-branch change, tag, GitHub Release, package-index upload, or public installer publication.

Until signing is provisioned, the updater correctly refuses automatic installation of the unsigned RC.
