# Relic Auditor 0.11.0 release candidate

This local RC contains the Assisted Build Supervisor, exact capability
approvals, managed workspaces, checkpoints and rollback, a hash-chained event
ledger, resource budgets, full diffs, signed entitlement verification, and the
fixed Build Pack desktop handoff.

It deliberately does not contain a production activation public key. Normal
installs therefore remain Free until the external KMS-backed licensing service
is provisioned. The Claude Code builder remains a developer preview pending
Anthropic approval for third-party Claude.ai subscription integration.

No tag or GitHub Release was created. No installer is included in this source
artifact set; the Windows workflow remains a separate validation gate.

The supervisor is an approval, accounting, and recovery boundary, not a VM,
separate Windows user, or firewall. Untrusted native builders still require an
independent operating-system sandbox.
