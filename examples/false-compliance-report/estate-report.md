# Relic Auditor Estate Report

> Deterministic, read-only appraisal. No scanned file was executed, installed, changed, or deleted.

## Executive inventory

- Target: `false_compliance`
- Files observed: **10**
- Project roots detected: **1**
- ZIP archives inspected virtually: **0**
- Duplicate groups: **0**
- Ignored generated/junk entries: **2**

## Appraisal

- Valuable system: **1**

## Detected projects

| Root | Types | Score | Category | Evidence |
|---|---|---:|---|---|
| `.` | FastAPI, Python | 65/100 | Valuable system | substantive source tree; tests present; documentation present; application framework detected |

## Candidate summary

- Extract candidates: **0**
- Archive candidates: **0**
- Delete-review candidates: **2**

Delete candidates are recommendations for human review only. Relic Auditor never deletes them.

## Pivot suggestions

### Extract a design system or interactive prototype

Treat the interface work as a reusable component kit or validated product concept.

Evidence: UI components detected, No strong API routing signal. Confidence: **medium**.

## Safety and limitations

- ZIPs are validated for traversal paths, absolute paths, symlinks, encryption, size, member count, and suspicious compression ratios.
- ZIP contents are read as virtual members; they are not written over the target.
- Generated dependencies and caches such as `node_modules`, `.git`, virtual environments, and build outputs are skipped.
- High-signal previews are bounded and common secret formats are redacted.
- Appraisal and pivot rules are heuristic evidence, not instructions to destroy data.
- LLM reasoning is intentionally disabled in this release.

## Output files

- `estate-report.md`
- `architecture-map.json`
- `extract-candidates.json`
- `archive-candidates.json`
- `delete-candidates.json`
- `pivot-suggestions.json`
