# Relic Technical Truth Engine

## Purpose

Technical Truth v0.4 builds on the v0.3 evidence model to distinguish capability
language from connected implementation. It sits between deterministic inventory
and Product Resurrection and is authoritative about structural evidence. v0.4
adds conservative semantic resolution, persistent parse caching, static Git
lineage evidence, and basic data-flow mappings.

## Threat and safety model

Relic reads bounded text and parses it with trusted internal code. It never
imports scanned modules, runs package scripts, builds, installs dependencies,
starts servers, invokes migrations, executes tests, evaluates configuration, or
launches language servers. Symlink and ZIP protections remain in the v0.1
scanner. Reports contain structural references, not full proprietary source.

## Architecture

```text
Inventory → family resolution → language adapters → symbols/surfaces
→ relationship graph → reachability → workflows → capability verification
→ contradictions → Technical Truth report → Product Resurrection gate
```

## CLI and configuration

```bash
relic audit ./estate --technical-truth
relic audit ./estate --technical-truth --product-discovery
relic audit ./estate --technical-truth --technical-max-file-mb 2 \
  --max-graph-nodes 100000 --max-data-flow-edges 50000 \
  --workflow-depth 12
relic audit ./estate --technical-truth --no-technical-cache
relic audit ./estate --technical-truth \
  --technical-cache ./report-cache/technical-truth.json
```

Product discovery enables Technical Truth automatically. `--no-technical-truth`
preserves v0.2 fallback behavior with reduced confidence.

## Supported languages and adapters

- Python: standard-library AST extraction for imports, aliases, functions,
  classes, parameters, decorators, calls, caller ownership, environment reads,
  stubs, and risk indicators.
- JavaScript and TypeScript, including JSX/TSX: a trusted in-process tokenizer
  and balanced-scope structural AST for imports and aliases, exports, functions,
  classes, interfaces, types, enums, parameters, calls, caller ownership,
  environment reads, stubs, and risk indicators.
- Other recognized source languages are inventoried as unsupported and reduce
  coverage; no workflow is fabricated.

The JavaScript/TypeScript adapter is deliberately not a compiler or type
checker. It masks comments and string contents, recognizes balanced scopes, and
does not invoke a repository transpiler, language server, package manager, or
plugin. Dynamic dispatch, dependency injection, re-export chains, generated
routes, decorators, and complex type-level behavior may remain unresolved.

## Framework and surface detection

The framework layer recognizes React, Next.js, Express, Fastify, FastAPI, Flask,
Django, BullMQ, Celery, Prisma, and SQLAlchemy through imports and runtime
conventions. It also reconstructs client requests, schema/model conventions,
queue producers and consumers, worker callbacks, common external integrations,
tests/mocks and static risk indicators.

Package presence is not proof. An integration is `configuration_only` until a
production call is structurally observed.

## Symbol graph

Stable IDs derive from family, relative path, symbol kind, name and start line.
Nodes include project families, files, symbols, endpoints, UI actions, schemas,
queues, frameworks, and integrations. Edges include `defines`, `imports`,
`calls`, `passes_data`, `reads_from`, `writes_to`, `routes_to`, `triggers`,
`produces`, `consumes`, `consumed_by`, `invokes`, `persists`, and
`calls_external`. Each edge exposes confidence, observation type and extraction
method.

Relative JavaScript/TypeScript and Python module references are resolved against
observed files, including common source extensions and `index` modules. Named
import aliases are resolved to exported symbols. A unique unqualified
project-wide name can produce only a lower-confidence heuristic edge; ambiguous
matches produce no edge. `passes_data` maps simple argument identifiers to
declared parameters. These are structural mappings, not taint analysis or proof
of runtime values.

## Workflow reconstruction

Relic traverses bounded paths from UI actions and API endpoints. Queue producer
and consumer names are matched without running workers. A verified workflow
requires a connected entry, meaningful processing, persistence, an output and
no critical break. Missing links are findings, not invented steps.

## Capability statuses

Statuses are:

- `verified_end_to_end`
- `implemented_but_disconnected`
- `partially_implemented`
- `interface_only`
- `schema_only`
- `configuration_only`
- `test_or_mock_only`
- `documentation_claim_only`
- `inferred`
- `contradicted`
- `unknown`

Tests strengthen evidence but do not prove production reachability.

## Confidence model

Capability confidence exposes parser certainty, direct relationships,
reachability, test strength and contradiction penalties. Qualitative labels
accompany numbers. Scores express deterministic evidence weights, not runtime
correctness probabilities.

## Project families

Family grouping uses normalized backup/worktree/branch names and shared file
hashes. v0.4 also reads `.git/HEAD`, branch refs, packed refs, configured remote
URLs, and worktree pointers as inert text. A worktree pointer outside the scan
boundary is recorded but never followed. Relic never invokes Git. Divergence is
preserved, and a family relationship does not imply that variants can safely be
merged.

## Product Resurrection integration

Every v0.2 opportunity now carries technical verification status, verified
workflows/capabilities, disconnected capabilities, missing paths,
contradictions, coverage and readiness confidence. If required technical
capabilities are absent or unverified, readiness and ranking are capped and
copy changes from “implements” to “contains components that could support.”

## Outputs

```text
technical_truth_summary.json
symbol_inventory.json
relationship_graph.json
project_families.json
application_surfaces.json
workflow_inventory.json
capability_verification.json
contradictions.json
reachability_report.json
technical_truth_report.md
```

All schemas are version `1.0`, deterministically ordered and secret-free.

## Performance, limits and cache

Parsing has configurable file-size, graph-node, and data-flow-edge limits.
Truncation and unsupported files are explicit. Parse results use both a bounded
in-process cache and an optional persistent content-addressed JSON cache. The
cache key includes relative path, content hash, project family, and adapter
version. The CLI writes it under
`<report>/.relic-cache/technical-truth.json` by default, never inside the scanned
target. Cache files are atomically replaced. Changing source contents or an
adapter version invalidates the corresponding entry.

The cache accelerates parsing only. Graphs, workflows, capability statuses, and
contradictions are rebuilt deterministically from cached normalized parse
results. Resumable multi-million-node graph construction remains future work.

## Complete skeptical example

Input fixture:

```text
README: “complete compliance automation”
working login and upload endpoint
partial evaluator with unit test
queue producer with no consumer
disconnected report generator
mock dashboard
Stripe configuration with no call
```

Representative conclusion:

> This is not a verified compliance SaaS. Static evidence supports an
> authenticated document-ingestion prototype and partial rule evaluation. The
> workflow stops after job creation because no matching production consumer is
> connected. Report generation is implemented but disconnected, the dashboard
> uses mock data, and subscription billing is contradicted by configuration-only
> evidence.

The corresponding Product Resurrection proposal is capped and described as a
possible document-evaluation API or productized assessment service—not an
existing launch-ready product.

## Inspecting evidence

Start with `technical_truth_report.md`, then use workflow IDs in
`workflow_inventory.json`, capability IDs in `capability_verification.json`, and
edge IDs in `relationship_graph.json`. Structural references include relative
files, stable symbols, line ranges where supported, extraction methods and
confidence.

## Extending the engine

Add a language adapter by returning the normalized parse-result shape from
`technical_truth/adapters.py`. Add framework surfaces in `_surfaces`; never
invoke project tooling. Add workflow detectors as deterministic graph rules.
Bounded reasoning providers may explain graph summaries but may not create or
delete edges.

## Known limitations

- JavaScript/TypeScript parsing is intentionally conservative and token-AST
  based, not compiler-grade; overloaded syntax, decorators, re-exports, and
  implicit framework wiring may be missed.
- Python decorators, aliases, calls, and simple environment reads are extracted,
  but deep interprocedural data flow and runtime framework magic remain
  incomplete.
- Static reachability can produce both false positives and false negatives.
- `passes_data` records direct identifier-to-parameter mappings only. It does not
  propagate values through objects, callbacks, promises, closures, or storage.
- Cross-language and package-level calls are mostly unresolved.
- Git evidence is deliberately limited to static metadata and does not inspect
  object history, merge bases, or remote state.
- Authorization-flow proof and tenant-boundary analysis are not complete.
- Structural security findings are risk indicators, not confirmed
  vulnerabilities.
