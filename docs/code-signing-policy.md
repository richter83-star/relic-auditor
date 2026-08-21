# Code signing policy

This policy defines who may approve signed Relic Auditor builds, what may be signed, and what users should expect from signed Windows releases.

## Status

Relic Auditor v1.0.1 is publicly released but its Windows installer is **not Authenticode-signed**. Automatic updater installation therefore remains fail-closed. No document or policy statement changes that fact.

The preferred future signing provider is **SignPath Foundation** through its free open-source program, subject to project approval and all provider requirements. If approved and activated, Relic Auditor release pages will use the provider attribution required by SignPath Foundation:

> Free code signing provided by SignPath.io, certificate by SignPath Foundation

If SignPath Foundation is unavailable or the project is ineligible, the preferred fallback is Microsoft Azure Artifact Signing.

## Repository and release source

- Repository: `https://github.com/richter83-star/relic-auditor`
- License: MIT
- Public releases: `https://github.com/richter83-star/relic-auditor/releases`
- Authoritative branch: `main`
- Release builds must originate from reviewed repository commits and pass the repository's source and Windows lifecycle validation before signing.

## Signing roles

Until additional maintainers are formally added, the repository owner fills the following roles:

- **Committer:** `@richter83-star`
- **Reviewer:** `@richter83-star`
- **Signing approver:** `@richter83-star`

`CODEOWNERS` records the current repository review owner. If a signing provider requires role separation, an additional trusted reviewer or approver must be added before signing is enabled. Provider controls take precedence over this temporary single-maintainer arrangement.

## What may be signed

Only release artifacts produced from the authoritative Relic Auditor repository may be signed. A signing request must be rejected when any of the following is true:

- the source commit is not identified exactly;
- required source or Windows lifecycle validation failed or did not run;
- the artifact hash or size differs from the build manifest;
- the artifact was rebuilt from a different source commit without new validation;
- the artifact contains unreviewed proprietary or third-party payloads outside the project's declared dependencies;
- signing would weaken the updater's manifest, hash, publisher, or signature checks.

Signing approval does not authorize modification of scanned target code, remote deployment, publication of unrelated software, or bypass of Relic Auditor approval boundaries.

## Privacy and network behavior

Relic Auditor's deterministic scanning and reporting path uses no credentials or network access. Scanned target code remains local and is treated as evidence rather than executable input.

Optional provider reasoning is used only when a consenting host configures it. Relic sends bounded, secret-redacted context and preserves deterministic reports when the provider is unavailable or fails.

Packaged Windows builds may contact Relic Auditor's first-party HTTPS update endpoint according to the updater contract. Source checkouts do not check automatically. Update failures are non-destructive, and an update is never launched unless its signed manifest, declared size, SHA-256, Authenticode status, and pinned publisher checks pass.

Relic Auditor does not automatically upload scanned repositories or arbitrary target files to networked systems.

See also:

- [Entitlements and privacy](entitlements-and-privacy.md)
- [Windows updater contract](updater.md)
- [Build status](../BUILD-STATUS.md)

## Release-signing procedure

A future signed Windows release must follow this order:

1. Merge reviewed source through the authoritative repository workflow.
2. Run and pass `source-validation`.
3. Run and pass `windows-installer-rc` on the exact release head.
4. Freeze the exact source archive and record its SHA-256.
5. Build the Windows installer from that frozen source.
6. Submit the exact verified installer to the approved signing provider.
7. Verify Authenticode status and the expected publisher identity on the signed bytes.
8. Recompute and publish the signed installer size and SHA-256.
9. Publish the installer and verify the public bytes.
10. Publish the signed stable updater manifest last.
11. Verify that tampered, unsigned, stale, malformed, or wrong-publisher updates remain rejected.

## Current automatic-update gate

Automatic updating must remain disabled until a trusted signing provider is active and the updater's pinned publisher and stable-manifest trust requirements are satisfied. An unsigned public release is manual-install only.
