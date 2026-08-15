# Relic Auditor 0.10.1 release candidate

This focused patch corrects the first installed-build usability findings from
v0.10.0 without changing Relic's local-first, read-only, no-execution boundary.

- Claude installation/authentication now reports `CONFIGURED`; only a completed
  advisory request reports `OPERATIONAL`.
- Live advisory requests report `RUNNING`, while timeouts and failures replace
  every optimistic badge and explain that deterministic results remain complete.
- Opus with high effort carries a visible timeout warning and Sonnet with medium
  effort is identified as the recommended starting point.
- A persistent five-step guide connects Scan, Results, and Reports and the
  technical console states its recommended review order.
- Technical result rows are taller, columns retain readable widths, narrative
  columns expand, and full structured records remain visible in a persistent
  inspector.
- Unavailable Build Pack actions stay visible and explain the evidence or
  entitlement gate.

No Git tag or GitHub Release is created or authorized by this release candidate.
