# Relic Auditor

Relic Auditor is a local-first, deterministic appraisal CLI for messy software
estates. It reads loose files, folders, and ZIP files, detects project types, maps architecture,
finds byte-identical duplicates, and produces review candidates. It never imports,
executes, installs, changes, or deletes scanned code.

v0.11.0 adds the approval-gated Assisted Build Supervisor. After a Premium
user reviews and exports a checksum-verified Build Pack, Relic creates a
separate managed workspace, displays one immutable builder action, requires
each capability to be approved, checkpoints before execution, and stops at an
unpublished candidate with a complete diff. It also adds the fail-closed client
for signed Free/Pro/Premium entitlements. Production activation is deliberately
not provisioned in this RC, so ordinary installs remain Free until a real
KMS-backed licensing service and pinned public key exist. See
[docs/v0.11.0-release-notes.md](docs/v0.11.0-release-notes.md).

v0.10.2 adds a fail-closed Windows update path. Installed builds check the
stable channel at a bounded cadence, the header always provides a manual
**Check updates** action, and a three-step dialog explains version selection,
download verification, and installation. Relic will not launch an update
unless its exact size and SHA-256 match the first-party manifest and Windows
validates the pinned Dracanus AI Authenticode publisher. See
[docs/v0.10.2-release-notes.md](docs/v0.10.2-release-notes.md).

v0.10.1 corrected the first installed-build usability findings: Claude setup is
now distinct from successful runtime operation, timeouts replace optimistic
status everywhere, the product shell keeps a visible five-step path, evidence
tables preserve readable columns and expose a full-record inspector, and gated
Build Pack actions explain why they are unavailable instead of disappearing.
See [docs/v0.10.1-release-notes.md](docs/v0.10.1-release-notes.md).

v0.10.0 added the Product Builder Bridge. A Premium user can choose one
evidence-supported Opportunity, review a deterministic MVP plan, approve exact
hash-verified reusable assets, and export a separate Build Pack with Codex,
Claude Code, and generic render-only handoffs. The bridge never launches a
coding agent, shell, dependency installer, Git remote, deployment, or external
action. See [docs/product-builder-bridge.md](docs/product-builder-bridge.md).

Build Pack CLI lifecycle:

```bash
relic build-pack list product_opportunities.json --json
relic build-pack prepare product_opportunities.json --opportunity opp_ID \
  --target /path/to/rescanned-estate --output preview.json
relic build-pack export preview.json --approval approval.json \
  --target /path/to/rescanned-estate --output /path/to/Relic-Build-Packs
relic build-pack validate /path/to/Relic-Build-Packs/bp_ID --json
```

Production defaults to Free and the CLI has no entitlement-promotion flag.
The lifecycle commands become available only when a signed entitlement or an
explicit test host supplies the appropriate capability.

Assisted build CLI lifecycle:

```bash
relic build start /path/to/bp_ID --sessions /path/to/Relic-Build-Sessions --json
relic build plan /path/to/session_ID --file reviewed-actions.json --json
relic build approve /path/to/session_ID --action action_ID \
  --capability file_write --actor "reviewer" --json
relic build run /path/to/session_ID --action action_ID --json
relic build diff /path/to/session_ID --json
relic build finalize /path/to/session_ID --json
```

See [docs/assisted-build-supervisor.md](docs/assisted-build-supervisor.md) for
the complete capability, checkpoint, budget, and provider model.

v0.8.3 turns the desktop dashboard into a progressive-disclosure product for
non-technical users. The default shell has only Scan, Results, and Reports;
the complete evidence console remains available behind Technical details.
Completed scans now save automatically under
`Documents/Relic Auditor/Reports/<project> reports/<timestamp>`. See
[docs/v0.8.3-release-notes.md](docs/v0.8.3-release-notes.md).

v0.8.2 is a Technical Truth correctness hotfix. It repairs Python plain-import
parsing, blocks negative conclusions when source coverage is incomplete, scopes
documentation contradictions to the project family that made each claim, and
surfaces substantive but unclassified capability structure instead of silently
omitting it. See
[docs/v0.8.2-release-notes.md](docs/v0.8.2-release-notes.md).
v0.8.1 rebuilds the desktop dashboard as the Evidence Console: the product's true-black/neon-yellow identity, a clearer information architecture, and font-metric-driven layout that survives 100%-200% Windows display scaling. See [docs/v0.8.1-release-notes.md](docs/v0.8.1-release-notes.md).
v0.8 adds a native Claude Code subscription provider: the optional reasoning
layer can now run through your locally installed Claude Code CLI using your
existing Claude.ai (Max/Pro) session — no separately billed Anthropic API key
required. See [docs/CLAUDE_MAX_QUICKSTART.md](docs/CLAUDE_MAX_QUICKSTART.md).
v0.7 added an optional bounded LLM reasoning layer with API-key and OAuth 2.0
Authorization Code + PKCE authentication. v0.6 added Capability Acquisition
Mode and Relic Monitor. They identify
evidence-backed building blocks for a resource-bounded autonomous
self-improvement system while preserving the same read-only contract. The
optional v0.5 native dashboard remains supported.

## Install

Python 3.11 or newer is required.

CLI only:

```bash
python -m pip install -e .
```

CLI plus the interactive desktop dashboard:

```bash
python -m pip install -e ".[gui]"
```

Dashboard plus all optional interfaces:

```bash
python -m pip install -e ".[all]"
```

On Windows PowerShell, keep the quotes around the extras.

### Windows updates

The packaged Evidence Console checks the stable update channel no more than
once every 24 hours (or six hours after a failed check). Checks never interrupt
an audit and never install silently. Select **Check updates** in the application
header to check immediately. A candidate installer must pass all of these gates
before the Install button is enabled:

1. strict stable-channel manifest validation over HTTPS;
2. declared filename, byte size, and SHA-256 verification; and
3. a valid Windows Authenticode signature from the pinned Dracanus AI publisher.

Source checkouts do not perform automatic update checks. The updater never
receives or reads a scan target; it only handles the declared application
installer in Relic's per-user Updates directory.

## Interactive dashboard

Launch the folder picker:

```bash
relic dashboard
```

Or open directly on an estate:

```bash
relic dashboard "D:\messy software"
```

The default dashboard provides:

- **Scan** — choose a folder and run the complete local appraisal
- **Results** — understand what Relic found, what is valuable, what is risky,
  and what should happen next without changing tabs
- **Reports** — reopen previous scans and their exported reports
- **Technical details** — open the preserved evidence console, System Map,
  project tables, raw evidence, provider diagnostics, and planning controls

Completed dashboard scans automatically write deterministic JSON/Markdown
reports and `cleanup-plan.json` under the per-user Reports folder. Report
output is still rejected if it is inside the scanned target. Planning
decisions are advisory metadata only. The scan and report areas deliberately
have no execute, install, extract, move, rename, or delete control. Premium
Assisted Build is a later, separately approved workflow operating only on a
managed Build Pack workspace.

Analysis modes:

- **Quick Inventory** runs the original bounded estate scan.
- **Complete appraisal** is the dashboard default and runs Technical Truth,
  Product Resurrection, and Reusable Assets analysis together.
- **Technical Truth** reconstructs static symbols, relationships, workflows,
  reachability, contradictions, and project families.
- **Product Resurrection** also ranks offline, evidence-backed product and GTM
  hypotheses. Technical Truth runs automatically as its verification gate.
- **Reusable Assets** scores reusable building blocks for orchestration,
  goals, bounded autonomy, governance, approvals, auditability, improvement
  proposals, and resource requests.

The dashboard remains offline unless **Use optional LLM reasoning** is enabled
and a configured profile name is supplied. Even then, only a bounded,
secret-redacted acquisition evidence envelope is sent.

## CLI

```bash
relic audit /path/to/messy-folder
```

By default, reports are written beside the target as
`<target-name>-relic-report`. Write them somewhere specific:

```bash
relic audit /path/to/messy-folder --output /path/to/relic-report
```

Without installation:

```bash
PYTHONPATH=src python -m relic_auditor audit /path/to/messy-folder
```

The base command creates:

- `estate-report.md`
- `architecture-map.json`
- `extract-candidates.json`
- `archive-candidates.json`
- `delete-candidates.json`
- `pivot-suggestions.json`

Delete candidates are advisory. The command has no delete operation.

## Capability Acquisition Mode

Run acquisition analysis directly:

```bash
relic acquire /path/to/estate
relic acquire /path/to/loose-file.py
relic acquire /path/to/archive.zip
```

Or append it to a standard audit:

```bash
relic audit /path/to/estate --capability-acquisition
```

It detects these capability categories:

- Orchestrator
- Goal Registry
- Autonomy Loop
- Governance Boundary
- Approval Queue
- Audit Log
- Self-Improvement Proposal
- Resource Request

Every observed item receives deterministic capability matches, confidence, and
bounded redacted evidence. Documentation, examples, configuration, and tests
are discounted so they are not presented as production implementations.

The mode adds:

- `capability_acquisition_report.md`
- `capability_acquisition_inventory.json`
- `capability_acquisition_candidates.json`
- `capability_acquisition_gaps.json`

The report ranks the best reusable candidates, identifies missing or weak
pieces, proposes a governance-first build path, and lists integration risks.
It does not connect components, apply improvements, provision resources, or
expand authority.

## Optional LLM reasoning

The deterministic scanner remains the source of evidence. The LLM layer is an
opt-in sidecar that interprets a bounded, secret-redacted Capability Acquisition
summary and writes:

- `llm_reasoning_report.md`
- `llm_reasoning.json`

It never receives direct filesystem access, raw credentials, or authority to
execute, install, modify, delete, deploy, approve, or provision anything.
Repository strings are delimited as untrusted data. Provider failure leaves all
deterministic reports intact.

### API-key profile

OpenAI Responses API:

```bash
relic llm add openai-api \
  --protocol openai-responses \
  --model YOUR_MODEL \
  --auth api-key \
  --api-key-env OPENAI_API_KEY

relic acquire /path/to/estate --llm-profile openai-api
```

Anthropic Messages API:

```bash
relic llm add anthropic-api \
  --protocol anthropic-messages \
  --model YOUR_MODEL \
  --auth api-key \
  --api-key-env ANTHROPIC_API_KEY
```

API keys are read from the named environment variable at request time and are
never copied into Relic's profile file.

### OAuth profile

Relic implements the desktop-safe OAuth 2.0 Authorization Code flow with PKCE,
a random state value, loopback callback, refresh-token handling, and operating
system credential-vault storage:

```bash
relic llm add company-oauth \
  --protocol openai-chat \
  --model YOUR_MODEL \
  --base-url https://llm.example.com/v1 \
  --auth oauth \
  --authorization-url https://identity.example.com/oauth/authorize \
  --token-url https://identity.example.com/oauth/token \
  --client-id YOUR_PUBLIC_DESKTOP_CLIENT_ID \
  --scope openid \
  --scope offline_access

relic llm login company-oauth
relic llm status company-oauth
relic acquire /path/to/estate --llm-profile company-oauth
```

OAuth requires provider-issued endpoints and a public desktop client ID. It
does not scrape browser sessions or repurpose consumer ChatGPT/Claude
subscriptions; a provider must explicitly authorize its access token for the
configured inference endpoint.

### Claude Code / Claude Max subscription profile

Relic can also use the locally installed [Claude Code](https://claude.com/claude-code)
CLI as its reasoning host, letting Claude Code use its own existing Claude.ai
OAuth session. Relic never reads Claude credential files, never touches the
OAuth token, and never calls the Anthropic API directly from this provider —
Claude Code is invoked in non-interactive print mode with all tools disabled,
no MCP access, no session persistence, and only the same bounded,
secret-redacted evidence package the other providers receive.

```powershell
py -m relic_auditor llm add Claude-Max `
  --protocol claude-code `
  --model sonnet `
  --auth claude-subscription

py -m relic_auditor llm status Claude-Max
py -m relic_auditor acquire "D:\estate" --llm-profile Claude-Max
```

This is subscription-only: API-billing environment variables
(`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`) are removed
from the Claude Code child process, and an obvious Console/API-key login is
rejected. Claude Max and the Anthropic API are separate products; usage
consumes your Claude Code subscription allowance and remains subject to
Anthropic's current plan limits and account settings — it is not unlimited.
Full walkthrough: [docs/CLAUDE_MAX_QUICKSTART.md](docs/CLAUDE_MAX_QUICKSTART.md).

Profile management:

```bash
relic llm list
relic llm status PROFILE
relic llm logout PROFILE
relic llm remove PROFILE
```

Use `--llm-required` when automation should return exit status 3 if advisory
reasoning is unavailable. Deterministic reports are still written first.

## Relic Monitor

Watch a local inbox and run Capability Acquisition Mode after each drop becomes
stable:

```bash
relic monitor /path/to/relic-inbox
```

Choose an external report root and timing controls:

```bash
relic monitor /path/to/relic-inbox \
  --output /path/to/relic-monitor-reports \
  --debounce-seconds 2 \
  --poll-seconds 1
```

`--once` processes the items currently in the inbox after the debounce window
and exits. Temporary download suffixes, hidden entries, symlinks, dependencies,
caches, VCS metadata, and known junk are ignored. Report output is rejected if
it is inside the watched inbox.

## What Relic detects

- Node.js and common Node frameworks, including Next.js, React, Express,
  Fastify, NestJS, and Electron
- Python and FastAPI
- Docker and Docker Compose
- Manifests, source, tests, documentation, routes, UI components, data models,
  migrations, and other assets
- Safe, virtual ZIP contents
- Known generated directories, caches, dependency trees, and junk files
- Byte-identical files
- Reusable extraction candidates and deterministic pivot patterns

## ZIP safety

ZIP files are never extracted over the target. Relic validates member names and
inspects safe members virtually. It rejects path traversal, absolute paths,
symlinks, encrypted entries, excessive member counts, excessive uncompressed
size, and suspicious compression ratios.

## Determinism and privacy

Reports omit run timestamps and machine-specific absolute target paths. File
ordering and JSON keys are stable. High-signal previews are bounded, decoded as
text only when safe, and passed through secret redaction before being written.

## Product Resurrection Engine

Run the separate, post-scan product-discovery pipeline:

```bash
relic audit /path/to/estate --product-discovery
```

It remains offline by default and adds:

- `product_opportunities.json`
- `product_resurrection_brief.md`
- `gtm_proposals.md`
- `capability_inventory.json`
- `opportunity_evidence.json`
- `extraction_plans.json`
- `market_validation.json`

The engine reconstructs stated intent, inventories implemented capabilities,
rejects weakly supported ideas, ranks surviving opportunities with exposed score
components, and creates extraction, GTM, pricing-hypothesis, and 30-day validation
plans. Every proposal references stable evidence IDs.

`--reasoning-provider` accepts `none`, `local`, or `configured_external`.
No adapter is bundled, and the pipeline remains functional with `none`.
`--market-validation` only requests a separately configured adapter; it never
silently sends repository content.

See [Product Resurrection Engine](docs/product-resurrection-engine.md) for the
architecture, schemas, scoring model, privacy boundaries, and limitations.

## Technical Truth Engine

v0.4 strengthens the v0.3 Technical Truth layer with semantic resolution that
remains deterministic and static:

```bash
relic audit /path/to/estate --technical-truth
relic audit /path/to/estate --technical-truth --product-discovery
```

Technical Truth runs automatically with `--product-discovery`. Use
`--no-technical-truth` only when a shallow v0.2-only result is intentionally
required; those opportunities are marked as unverified and readiness-capped.

It parses Python ASTs and conservatively extracts JavaScript/TypeScript
structure with a trusted in-process token AST, without importing or executing
source. Relative module imports and aliases are resolved, calls are attached to
their owning symbols, basic argument-to-parameter flow is represented, and
ambiguous project-wide name matches are left unresolved instead of being
presented as facts.

v0.4 also adds:

- A persistent content-addressed parse cache stored in the report directory
- Static, boundary-safe Git HEAD, branch, remote, and worktree evidence
- Evidence-backed React, Next.js, Express, Fastify, FastAPI, Flask, Django,
  BullMQ, Celery, Prisma, and SQLAlchemy detection
- Explicit graph and data-flow limits
- Stub-aware capability classification

Useful controls:

```bash
relic audit ./estate --technical-truth \
  --technical-cache ./report-cache/technical-truth.json \
  --max-data-flow-edges 50000

relic audit ./estate --technical-truth --no-technical-cache
```

This is not compiler-grade whole-program analysis. Dynamic imports, reflection,
dependency-injection containers, generated code, runtime routing, and complex
cross-language behavior can remain unresolved and are reported as limitations.

See [Technical Truth Engine](docs/technical-truth-engine.md) and the
[v0.4 release notes](docs/v0.4-release-notes.md).

## Dashboard packaging

The GUI is an optional dependency:

```toml
[project.optional-dependencies]
gui = ["PySide6>=6.7,<7"]
```

That keeps server, CI, and command-line installs lightweight. If the extra is
not installed, `relic dashboard` exits with an exact installation command while
`relic audit` continues to work normally.

See the [v0.5 release notes](docs/v0.5-release-notes.md) and
[v0.6 release notes](docs/v0.6-release-notes.md), plus the
[v0.7 release notes](docs/v0.7-release-notes.md).

## Development

```bash
python -m pytest -q --ignore=tests/fixtures
```
