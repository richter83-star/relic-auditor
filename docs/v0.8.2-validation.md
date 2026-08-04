# Relic Auditor v0.8.2 validation

Validation was performed against the complete v0.8.1 source archive committed
on the public `installer/v0.8.1` branch, with the supplied parser/report patch
used as the starting point.

## Automated suite

- 178 tests passed.
- 2 GUI suites skipped because PySide6 was not installed in the clean build
  environment.
- Source and tests compile successfully with Python 3.12.
- The built wheel installs into a clean target and reports `relic 0.8.2`.

## Parser regression

The patched project was scanned by its own Technical Truth engine:

| Measure | Result |
| --- | ---: |
| Python files considered | 66 |
| Parsed successfully | 66 |
| Internal parser failures | 0 |
| Invalid Python syntax | 0 |

Regression coverage includes plain imports, multiple imports, aliased imports,
dotted imports, relative imports, and cache reuse.

## Ground-truth matrix

| Project | Known truth | v0.8.2 result |
| --- | --- | --- |
| Working endpoint → evaluation → persistence → report | Implemented | All three named capabilities verified end-to-end |
| Same surface with `NotImplementedError` bodies | Stubs | All three capabilities classified interface-only |
| Endpoint → `adjudicate()` → `persist_dossier()` → `emit()` | Implemented, domain vocabulary | Connected workflow verified and surfaced as an unclassified substantive capability |

## Evidence safety

- An internal parser failure or unsupported/unparsed considered source blocks
  negative conclusions.
- Documentation contradictions are evaluated only against capability evidence
  from the same project family.
- Cross-project call, UI/API, router, and queue resolution is family-scoped.
- Fixture/test source does not count as production source in base appraisal.

This validation is a release regression set, not a calibrated precision/recall
benchmark. A larger labeled repository corpus remains required before decimal
confidence scores can be represented as probabilities.
