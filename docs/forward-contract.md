# Forward release contract

## Delivered in v0.11.0 — Assisted Build Supervisor

v0.11 consumes a verified v0.10 Build Pack and launches process-capable adapters
only behind explicit capability and approval gates in a new Relic-managed
workspace. File writes, processes, dependencies, network, credentials, Git, and
external actions are separately modeled. Sessions keep a hash-chained ledger,
budgets, checkpoints, pause/resume/cancel controls, complete diffs, and
fake-adapter tests. The terminal state is a review-required, unpublished build
candidate.

The release also contains a fail-closed signed-entitlement client. Production
activation still requires the Dracanus AI licensing service and a KMS-held
Ed25519 signing key; no desktop flag or local file can promote a plan.

## v1.0.0 — Relic Revival Loop

Connect scan → Opportunity → Build Pack → assisted build → verification →
re-audit. Detect drift, unsupported claims, missing requirements, secrets,
license/provenance changes, and regressions. Permit bounded approved repair
iterations and produce a replayable Product Readiness Dossier. Deployment,
publication, payments, accounts, messages, and actions outside the isolated
workspace remain separately approved.
