# Build status

Relic Auditor v1.0.1 is the current public release. The repository's authoritative `main` line is the reconciled history containing the validated v0.12 production foundation plus the selectively ported Resurrection and Technical Truth work.

## Authoritative repository state

- authoritative `main` cutover commit: `f78204b93c9b3279df14ea830dccf4247b29b44a`
- preserved disconnected historical line: `archive/disconnected-main-v1.0.0` at `ee216fab38d4560acfdc6d2c9709a0635842f4df`
- public release tag: `v1.0.1`
- tag target / canonical release commit: `300d4efeb6747671ade474e51fed8e45b229c757`
- canonical release tree: `05a2e8efc3aac86760f00cbdfbee4d6cf84c350c`
- public release: https://github.com/richter83-star/relic-auditor/releases/tag/v1.0.1

The cutover commit intentionally connects the previously disconnected histories while retaining the exact canonical v1.0.1 release tree. The tag remains on the exact commit whose source and Windows artifacts were validated.

## Release validation

Canonical GitHub Actions run `32453647140` completed successfully on Windows Server 2025 / Python 3.12.

It verified:

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
- configuration preservation after uninstall
- CLI PATH cleanup after uninstall
- release manifest and checksum generation
- artifact upload

## Canonical v1.0.1 artifacts

- Actions artifact ID: `9436635474`
- Actions artifact ZIP SHA-256: `267b3d59e7ec54391bf2a475e2a1c66f04046bd0be4842c9e07328594469083e`
- frozen source SHA-256: `800e3bd250b81475542c150bcd89d537ad46dc26f8840a18ea071f500770af1b`
- installer: `Relic-Auditor-Setup-1.0.1-x64.exe`
- installer SHA-256: `56c3e20c9cdcf8e2a6beae76b0e05d928e1af0002e92240c83d1ace773069d10`
- installer size: `73,928,624` bytes
- Authenticode: `NotSigned`

The GitHub Release contains the installer, frozen source ZIP, release manifest, SHA256SUMS, and installer README. The immutable publication record is stored in `releases/v1.0.1/PUBLICATION.json`.

## Security and update status

The public v1.0.1 Windows installer is unsigned. Windows may therefore show an unknown-publisher warning. The automatic updater remains disabled and fail-closed for this release because the pinned Authenticode requirement is not satisfied.

Automatic updates must not be enabled until all of the following are provisioned and validated:

1. a trusted production Authenticode certificate;
2. Actions signing credentials for the production certificate;
3. a newly built and lifecycle-tested signed installer;
4. a signed stable update manifest using the pinned update trust root; and
5. permanent stable-manifest and installer hosting.

## Repository governance still external

The connected GitHub automation does not expose repository ruleset / branch-protection administration. `main` should be protected in GitHub repository settings with required pull requests, required `source-validation` and `windows-installer-rc` checks, conversation resolution, and force-push / deletion blocking.

The durable `.github/workflows/reconcile-v1.yml` workflow validates pull requests targeting `main` and source changes pushed to `main`; its historical filename is retained to avoid an unnecessary workflow-file rename during the post-release record update.
