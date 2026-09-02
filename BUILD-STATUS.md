# Build status

Relic Auditor v1.0.1 remains the current public release. The repository's
authoritative `main` line now contains the merged and validated v1.0.3 focused
product correction. v1.0.3 tightens opportunity selection and contextual
Technical Evidence without changing the scanner, Build Pack, Supervisor,
entitlement, updater, or target-safety boundaries.

## Authoritative repository state

- v1.0.3 reviewed source head: `dd14d84f5eddd403759eee923bbe70ddbf26d018`
- v1.0.3 merge commit: `e8f77f61d0bbb95e3e55d61d26e4c2fff1cb69ba`
- public release tag: `v1.0.1`
- tag target / canonical release commit: `300d4efeb6747671ade474e51fed8e45b229c757`
- canonical release tree: `05a2e8efc3aac86760f00cbdfbee4d6cf84c350c`
- public release: https://github.com/richter83-star/relic-auditor/releases/tag/v1.0.1

The v1.0.1 tag remains on the exact commit whose source and Windows artifacts
were validated. The v1.0.3 merge does not create a public release, signed
installer, stable update manifest, or updater authorization.

## Validated v1.0.3 candidate

The v1.0.3 candidate was based on the merged v1.0.2 line and preserves its
release-hardening changes, including exact-head source provenance, retained
JUnit evidence, non-persistent checkout credentials, and serialized Supervisor
state writes.

Both required pull-request jobs passed against the exact candidate head:

- `source-validation`
- `windows-installer-rc`

The Windows job proved a clean install, same-version repair, upgrade
from the public v1.0.1 installer, configuration preservation, uninstall/PATH
cleanup, read-only target behavior, and exact frozen-source test parity.

## Release validation

Candidate GitHub Actions run `33580568870` and post-merge `main` validation run
`33596917191` completed successfully on Windows / Python 3.12.

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

The retained v1.0.3 RC evidence records:

- Actions artifact ID: `9828395283`
- Actions artifact ZIP SHA-256: `c7ca2c45cace3d49886e341ddfe5bf97ff433abf8bc29859e2625e631fe24d18`
- frozen source SHA-256: `544e24b954c618db9a30a5bffdd63f95745df440270d8f23233337bdb7b0597d`
- installer SHA-256: `e3079d9e6e06cdaf90e95855fcea7e49e55691b904f27eb3bbee26bfc5f1a67c`
- installer size: `73,978,812` bytes
- Authenticode: `NotSigned`

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

## Signing and repository governance still external

The repository now contains a manual SignPath trusted-build workflow, provider
artifact configuration, source/build policy, and fail-closed finalizer. They do
not activate signing. Remaining external prerequisites are SignPath Foundation
approval, SignPath GitHub App/project provisioning, an independent reviewer,
an active `main` ruleset, the submitter token and organization variable, and
confirmation that the issued certificate identity matches the updater's
pinned publisher.

`main` must be protected in GitHub repository settings with required pull
requests, required `source-validation` and `windows-installer-rc` checks,
conversation resolution, independent approval, and force-push / deletion
blocking.

The durable `.github/workflows/reconcile-v1.yml` workflow validates pull requests targeting `main` and source changes pushed to `main`; its historical filename is retained to avoid an unnecessary workflow-file rename during the post-release record update.
