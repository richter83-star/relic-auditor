# SignPath Foundation release-signing setup

This is the account-side handoff for Relic Auditor's managed Windows signing
workflow. The repository is ready to request and verify a signature, but the
workflow remains intentionally unusable until SignPath approves the project,
the GitHub trust integration is installed, an independent reviewer is added,
and the certificate identity is reconciled with the updater.

## Application profile

Use these values in the SignPath Foundation open-source application:

- Project: **Relic Auditor**
- Repository: `https://github.com/richter83-star/relic-auditor`
- License: MIT
- Project slug: `relic-auditor`
- Signing-policy slug: `release-signing`
- Artifact-configuration slug: `windows-installer`
- Release branch: `main`
- Build system: SignPath's predefined **GitHub.com** trusted build system
- Artifact: 64-bit Windows Inno Setup installer
- Maintainer: `@richter83-star`
- Required attribution: `Free code signing provided by SignPath.io, certificate by SignPath Foundation`

Relic Auditor is a local-first, read-only software-repository auditor. The
deterministic scan path does not execute target code or require network access.
The Windows updater remains disabled unless both signed update metadata and a
valid installer from its pinned Authenticode publisher are present.

## SignPath configuration

1. Obtain SignPath Foundation approval and create the organization/project.
2. Add the predefined GitHub.com trusted build system to the organization and
   link it to the `relic-auditor` project.
3. Install the SignPath GitHub App with access to only this repository.
4. Create the `release-signing` signing policy and associate the approved
   certificate.
5. Create the `windows-installer` artifact configuration by importing
   `.signpath/artifact-configurations/windows-installer.xml`.
6. Configure the signing policy to use the repository policy at
   `.signpath/policies/relic-auditor/release-signing.yml`.
7. Create a submitter API token restricted to this project and signing policy.
8. Add the token as the repository secret `SIGNPATH_API_TOKEN` and add the
   SignPath organization ID as the repository variable
   `SIGNPATH_ORGANIZATION_ID`.

The artifact configuration accepts the version as a request parameter and
signs exactly `Relic-Auditor-Setup-${version}-x64.exe` inside the GitHub
artifact ZIP. Uploading only that exact installer also prevents unrelated
files from entering the signing request.

## GitHub governance prerequisite

Add an independent trusted reviewer before activating release signing, then
update `.github/CODEOWNERS` so a person other than the last pusher can approve
signing-policy and release-workflow changes.

Create an active ruleset for `main` with all of these minimum rules:

- require a pull request;
- require at least one approval;
- dismiss stale approvals after new pushes;
- require CODEOWNER review and approval of the most recent push;
- require review-thread resolution;
- require the `source-validation` and `windows-installer-rc` pull-request
  checks;
- block force pushes and branch deletion; and
- allow no bypass actor for these rules.

These settings match the source/build policy SignPath will verify. With only
the current single maintainer, the required independent approval cannot be
satisfied and signing must remain blocked.

## Certificate identity gate

The updater currently pins the exact Authenticode certificate simple name
`Dracanus AI`. Before accepting the first signed candidate, inspect its signer:

```powershell
$signature = Get-AuthenticodeSignature .\Relic-Auditor-Setup-1.0.3-x64.exe
$signature.Status
$signature.SignerCertificate.GetNameInfo('SimpleName', $false)
$signature.SignerCertificate.Subject
$signature.SignerCertificate.Thumbprint
```

The manual signing workflow requires `Valid`, a timestamp certificate whose
online-revocation-checked chain terminates at a system-trusted root and permits
time stamping, and the case-sensitive simple name `Dracanus AI`. If SignPath
Foundation issues a certificate with a different simple name, do not weaken or
bypass the check. Update the pinned updater publisher, documentation, and tests
in a separately reviewed change first; then rebuild from the new `main` head.

Every external action in the repository workflows is pinned to a reviewed
40-character commit SHA. The source test suite rejects mutable action tags so a
tag move cannot silently change code that receives signing credentials.

## Controlled first run

Dispatch `Sign Relic Auditor v1.0.3 Windows release candidate` with the exact
current 40-character `main` commit and the `SIGN-v1.0.3` authorization. The
workflow will:

1. reject any workflow ref or commit other than the exact current `main` head;
2. rebuild and lifecycle-test an unsigned candidate from a frozen source ZIP;
3. upload only that installer to GitHub's workflow-artifact store;
4. submit the GitHub artifact ID through SignPath's trusted-build action;
5. reject an invalid, untrusted-timestamp, unchanged, or wrong-publisher result;
6. clean-install, launch-smoke, and uninstall the exact signed installer;
7. recompute the signed size and SHA-256 and preserve the unsigned lineage; and
8. upload a verified signed RC artifact without creating a tag or release.

After the signed RC is independently verified, follow the publication order in
`docs/code-signing-policy.md`. Publish the signed stable update manifest last.

The initial managed configuration signs the outer installer consumed by the
updater. If SignPath's artifact analysis recognizes the Inno Setup payload for
deep signing, review and version a provider-generated configuration before
adding nested product executables; never apply the project certificate to
third-party runtime files.
