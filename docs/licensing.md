# Signed plan licensing

Relic Auditor defaults to Free. Paid activation is not yet provisioned, but
owner and invited testing can use a signed, installation-bound offline license.

## Owner testing and offline activation

1. In **Settings → Plan → Manage plan**, select **Copy installation ID**.
2. Send that ID to the issuer. It is a random identifier, not a password or
   hardware serial number.
3. Import the returned file with **Import license file**. The plan badge and
   active scan update immediately. Restarting Relic preserves valid access.
4. **Remove license from this device** returns the installation to Free.

The equivalent CLI commands are:

```powershell
relic license device
relic license import .\owner.relic-license
relic license status
relic license pricing
```

Owner licenses do not use the unprovisioned online activation endpoint. Their
public issuer key is pinned separately from production purchase and updater
keys. The private owner key stays outside the repository, source archives,
installer, and CI. A public installation ID alone cannot unlock a plan.

The administrative `tools/issue_owner_license.py` issues up to 90 days of
Premium access using that separately held Ed25519 key. It requires the exact
installation ID, a subject, and a destination outside the repository. It
refuses to overwrite an existing grant. Renew an offline grant by importing a
new signed file; commercial online refresh is not used for owner testing.

[Plans and pricing](pricing.md) is the shared destination linked by the app,
CLI and README. Public checkout and paid activation remain unavailable until
prices and purchase-to-license delivery are configured.

## Trust boundary

The activation service signs an exact entitlement with Ed25519. The desktop
verifies the signature, issuer, service, plan, device ID, subscription expiry,
and bounded offline-validity window before enabling a paid capability. The
signed token is stored only in the operating-system credential vault. A random
installation identifier is stored locally; Relic does not derive it from
hardware serial numbers.

The activation request contains only:

- the entered license key;
- the random installation ID;
- the Relic version; and
- the operating-system name.

Source files, scan paths, reports, provider credentials, and Build Pack content
are never sent to the licensing service.

`relic license refresh` exchanges the cached signed token—not the original
license key—for a newly signed offline window. The replacement is verified
before it overwrites the credential-vault copy. Local deactivation deletes the
cached token and returns the installation to Free.

## Plan matrix

| Capability | Free | Pro | Premium |
|---|:---:|:---:|:---:|
| Deterministic audit and reports | Yes | Yes | Yes |
| Opportunity ranking | No | Yes | Yes |
| Build Pack preview/export | No | No | Yes |
| Assisted Build Supervisor | No | No | Yes |
| License activation client | Yes | Yes | Yes |

There is no production command-line flag, environment variable, or editable
configuration file that promotes the current plan. Test entitlement injection
exists only as an explicit code-level test boundary.

## Provisioning required before sales

The repository contains an owner-test public verification key, but no commercial
activation public key yet. New installations stay on Free until a valid signed
license is imported. Before selling Premium, Dracanus AI must:

1. create the activation service at the configured HTTPS endpoint;
2. hold the Ed25519 private key in a managed KMS/HSM;
3. pin only the public key and key ID in the desktop build;
4. implement purchase, refresh, renewal, revocation, device reset, and support flows;
5. define privacy, refund, subscription, tax, and account-recovery policies;
6. validate Windows Credential Manager behavior in the signed installer; and
7. rotate keys through an overlap window without accepting unsigned tokens.

Generating a signing key inside the repository or shipping the private key in
the desktop application would destroy the licensing boundary and is explicitly
out of scope.
