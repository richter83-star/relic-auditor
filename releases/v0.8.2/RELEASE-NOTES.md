# Relic Auditor v0.8.2 release notes

v0.8.2 is a correctness hotfix for the deterministic Technical Truth engine.
Do not use v0.8.1 Technical Truth conclusions for diligence decisions.

## Release blockers fixed

- Python files containing `import x`, aliased imports, multiple imports, and
  relative imports are parsed without an internal adapter failure. The Python
  adapter version is bumped so persistent parse caches cannot reuse affected
  v0.8.1 results.
- The in-process parse cache keys source by SHA-256 instead of retaining full
  source text in every cache key.
- Technical Truth emits a machine-readable `conclusion_gate`. Negative
  conclusions are blocked when coverage is below 60% or any considered source
  remains unparsed or unsupported.
- Documentation contradictions are evaluated within the project family that
  made the claim. Evidence and verified capability from unrelated projects can
  no longer leak across an estate.
- Connected, substantive production structure that the built-in vocabulary
  cannot name is emitted as an `unclassified` capability instead of
  disappearing.
- Base appraisal no longer counts fixture/test source as production source,
  and tests cannot contribute more than eight appraisal points.

## Confidence language

Numeric confidence fields remain for schema compatibility. Reports now also
emit `evidence_strength` (`strong`, `moderate`, or `weak`) and use that language
in reader-facing capability summaries. The decimal fields are evidence-ranking
scores, not calibrated probabilities.

## Safety

The read-only contract is unchanged. Relic does not import, execute, build,
test, install, migrate, move, rename, or delete scanned source.

See [v0.8.2 validation](VALIDATION.md) for the parser self-scan,
ground-truth matrix, clean-wheel smoke test, and remaining calibration limit.
