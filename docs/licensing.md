# Signed plan licensing

Relic Auditor v0.11.0 contains the client half of a commercial entitlement
system. It fails closed to Free.

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

The repository intentionally contains no production public key yet. That means
this release candidate displays Free and reports that activation is not
provisioned. Before selling Premium, Dracanus AI must:

1. create the activation service at the configured HTTPS endpoint;
2. hold the Ed25519 private key in a managed KMS/HSM;
3. pin only the public key and key ID in the desktop build;
4. implement purchase, renewal, revocation, device reset, and support flows;
5. define privacy, refund, subscription, tax, and account-recovery policies;
6. validate Windows Credential Manager behavior in the signed installer; and
7. rotate keys through an overlap window without accepting unsigned tokens.

Generating a signing key inside the repository or shipping the private key in
the desktop application would destroy the licensing boundary and is explicitly
out of scope.
