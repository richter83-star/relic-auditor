# Product Resurrection Engine

## Purpose

The Product Resurrection Engine is a post-scan Relic subsystem that turns
repository evidence into bounded product hypotheses. It can identify a narrower
commercial workflow that is better supported than the project described by a
README, or combine complementary capabilities across related project roots.

It is not a generic idea generator. Unsupported candidates fail a quality gate.

## Architecture

```text
Deterministic scanner
  → architecture and evidence records
  → original-intent reconstruction
  → product-neutral capability inventory
  → opportunity templates
  → evidence quality gate
  → transparent scoring and ranking
  → extraction, GTM and validation reports
```

The scanner is unchanged. Product discovery consumes its `AuditResult` and
cannot traverse the filesystem independently.

## CLI usage

```bash
relic audit ./estate --product-discovery
relic audit ./estate --product-discovery --offline
relic audit ./estate --product-discovery --max-opportunities 4
relic audit ./estate --product-discovery --reasoning-provider none
```

External validation must be explicitly requested:

```bash
relic audit ./estate --product-discovery --market-validation \
  --reasoning-provider configured_external
```

No external adapter is bundled in v0.2. A request without an adapter produces a
clear `not_configured` result and transmits nothing.

## Offline versus online behavior

Offline mode is the default. It performs deterministic pattern matching,
evidence linking, quality gating, scoring, and report generation. It makes no
network calls.

Online research is an interface boundary only. A future adapter may receive a
narrow, redacted capability summary. It must never receive the full repository
by default and must keep repository facts, external facts, inferences,
assumptions, and unknowns separate.

## Privacy and security model

- Scanned code is read, never imported or executed.
- Installation scripts are never run.
- Source files are never changed, renamed, moved, or deleted.
- Reports must be written outside the scanned target.
- Secret redaction runs before evidence is serialized.
- Evidence samples are bounded.
- ZIP members retain the core scanner’s traversal and archive-bomb protections.
- A reasoning provider receives structured summaries, not filesystem access.

## Evidence model

Each evidence record contains a stable ID, relative path, symbol when detected,
safe line range, evidence type, relevance statement, confidence, and redaction
status. Opportunities reference these IDs. README statements are treated as
stated intent rather than proof of implementation.

Candidates require:

1. At least two evidence records.
2. At least one implemented or partially implemented capability.
3. A specific user, buyer, trigger, job and delivered output.
4. A credible extraction path.
5. An explicit unknown and failure reason.
6. An evidence score above the configured threshold.
7. No unresolved generic-language penalty.

## Opportunity scoring

The overall score is a deterministic weighted combination:

- Repository evidence: 35%
- Capability completeness: 25%
- Commercial-confidence hypothesis: 20%
- Extraction-effort score: 20%

The output also exposes buyer urgency, reachability, time to value, competitive
intensity, dependency risk, security burden, and market-validation confidence.
Unvalidated commercial dimensions are labeled as hypotheses.

When Technical Truth is available, a technical-evidence gate is applied after
the commercial score. A launch-ready claim requires a verified connected
workflow or multiple connected production capabilities. Disconnected,
interface-only, schema-only, configuration-only, test-only, documentation-only,
or inferred evidence caps readiness and forces speculative wording. Market
attractiveness cannot override weak implementation evidence.

## Provider configuration

`reasoning_provider` supports:

- `none`: deterministic pipeline only.
- `local`: reserved for a locally configured reasoning adapter.
- `configured_external`: reserved for an explicitly configured external adapter.

The domain layer contains no model-vendor dependency. To add a provider,
implement the `ReasoningProvider` protocol, accept only redacted structured
context, and register it in `providers.py`. Market research should be a separate
adapter and should never be folded into the deterministic scanner.

## Output schemas

All JSON artifacts contain `schema_version: "1.0"` at their document or record
level. The seven files cover opportunities, capability inventory and intent,
evidence, extraction plans, market status, a human brief, and complete GTM copy.

When research is disabled, `market_validation.json` states:

```json
{
  "status": "not_performed",
  "reason": "External market validation was not enabled.",
  "repository_findings_are_market_validated": false
}
```

## Example report

A repository containing implemented ingestion, scoring and report modules may
produce a “Bulk intake and qualification service” proposal. Its report lists
the exact supporting modules, a fixed-scope pilot, excluded features, extraction
risks, pricing hypotheses, 30-day experiments, and explicit kill criteria.

## Limitations

- Capability recognition is presently deterministic and vocabulary-driven.
- Symbol and line extraction is static and conservative rather than
  language-server or compiler based.
- Code presence does not prove runtime correctness or production readiness.
- Project-family grouping uses conservative naming, duplicate evidence, and
  boundary-safe static Git metadata; it does not execute Git or inspect remote
  state.
- Competitors, prices, regulations and purchase behavior remain unvalidated
  unless a future research adapter is explicitly configured.
- Owner-fit scoring remains neutral unless future configuration is supplied.
