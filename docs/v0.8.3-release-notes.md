# Relic Auditor v0.8.3 release notes

v0.8.3 redesigns the desktop experience around the answer an average user
needs, while preserving the complete deterministic evidence underneath.

## Product shell

- The default interface has exactly three sections: **Scan**, **Results**, and
  **Reports**.
- Results answers four questions on one screen: what Relic found, what is
  valuable, what is incomplete or risky, and what should happen next.
- **View full report** is the single primary result action.
- The previous nine-view analyst console remains intact behind **Technical
  details**.

## Reports

- Every completed dashboard audit exports automatically to
  `Documents/Relic Auditor/Reports/<project> reports/<timestamp>`.
- Reports lists prior scans, opens the selected full report, opens its scan
  folder, and opens the stable Reports root.
- The automatic export remains outside the scanned target and preserves the
  existing read-only safety boundary.

## Terminology

- Architecture is now **System Map**.
- Acquisition is now **Reusable Assets**.
- Candidates are now **Recommended Actions**.
- Pivot suggestions remain presented as **Opportunities**.

## Default analysis

The recommended default is a complete appraisal: Technical Truth, Product
Resurrection, and Reusable Assets analysis run together. Experts can select a
narrower mode in Technical details.

## Safety and compatibility

The v0.8.2 Python parser correctness fixes remain included. Relic still does
not execute, install, import, move, rename, or delete scanned source.
