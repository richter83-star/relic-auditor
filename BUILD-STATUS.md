# Build status

Relic Auditor 0.12.0 is a local production-foundation release candidate based
on the verified v0.11.0 source and Windows workflow.

## Implemented

- exact Codex sandbox-profile verification and fail-closed process policy
- active process-tree cancellation with checkpoint restoration
- separately pinned Ed25519 update and entitlement trust roots
- signed update-manifest verification before download
- signed entitlement refresh without storing the original license key
- persistent provider runtime truth across setup checks and restarts
- visible five-step product route and more readable evidence tables

## Local verification

- updater, licensing, supervisor, cancellation, and provider-health tests pass
- all available non-GUI source tests pass
- Python sources compile
- deterministic source archive, wheel, and sdist are regenerated below

## Remaining release gates

- complete GitHub Actions Windows source and frozen-source suites
- bundled and installed GUI/CLI smoke tests
- repeat-install and stale-runtime cleanup verification on Windows
- provisioned update/licensing public keys and external services
- permanent public update endpoint and trusted Dracanus AI code-signing certificate

The updater will not trust an unsigned manifest or launch an unsigned installer.
Until signing, keys, and permanent hosting are configured, manual installation
remains the internal-test path and licensing remains Free.
