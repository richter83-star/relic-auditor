# Relic Auditor

Relic Auditor is a local-first software-estate appraisal and controlled build-preparation tool. It scans folders, loose files, and ZIP archives; reconstructs technical structure; identifies reusable assets and product opportunities; prepares deterministic Build Packs; and can supervise explicitly approved build actions inside managed workspaces.

The core safety rule has not changed: **Relic does not import, install, execute, modify, move, rename, or delete scanned target code.** Scanned repositories are evidence, not execution environments.

## Current release: v1.0.1

v1.0.1 reunifies the validated v0.12 production-foundation line with the later Resurrection and Technical Truth work that had accidentally developed on a disconnected Git history.

The unified line preserves:

- Technical Truth static analysis and evidence grounding
- Product Opportunity / Resurrection analysis
- deterministic Build Packs with asset provenance and approvals
- Free / Pro / Premium entitlement boundaries
- approval-gated Assisted Build Supervisor and audit ledger
- provider health checks and bounded optional LLM reasoning
- fail-closed updater and pinned trust-root infrastructure
- Windows GUI, CLI, installer, upgrade, cleanup, and uninstall lifecycle

It also adds the standalone Resurrection command:

```bash
relic resurrect /path/to/estate --output /path/to/resurrection-report
```

Resurrection evaluates whether a partially built codebase contains a substantive, connected product core worth salvaging. Its deterministic evidence gate can force `TOSS_IT`; optional LLM reasoning may interpret the bounded evidence but cannot override missing evidence or invent source paths. Market context is currently **offline heuristic context**, not live market research.

The reconciliation history and validation rules are documented in [docs/v1.0.1-reconciliation.md](docs/v1.0.1-reconciliation.md). Release changes are summarized in [docs/v1.0.1-release-notes.md](docs/v1.0.1-release-notes.md), with upgrade guidance in [docs/v1.0.1-upgrade.md](docs/v1.0.1-upgrade.md). The public release is available at [GitHub Release v1.0.1](https://github.com/richter83-star/relic-auditor/releases/tag/v1.0.1).

## Product flow

The desktop experience uses progressive disclosure:

1. **Scan** — choose a folder and run the appraisal.
2. **Results** — see what Relic found, what is valuable, what is incomplete or risky, and what should happen next.
3. **Reports** — reopen prior scans and exported reports.
4. **Technical details** — inspect System Map, raw evidence, provider diagnostics, architecture data, and expert controls when needed.

User-facing result concepts are **Opportunities**, **Reusable Assets**, **System Map**, and **Recommended Actions**.

Completed dashboard scans are stored under the per-user Relic Auditor Reports hierarchy. Report destinations are rejected when they would write inside the scanned target.

## Install from source

Python 3.11 or newer is required.

CLI only:

```bash
python -m pip install -e .
```

CLI plus desktop dashboard:

```bash
python -m pip install -e ".[gui]"
```

All optional interfaces:

```bash
python -m pip install -e ".[all]"
```

On Windows PowerShell, keep the quotes around the extras.

The Windows installer bundles Python and does not require a separate Python installation on the target machine.

## Core CLI

Run a standard audit:

```bash
relic audit /path/to/estate
relic audit /path/to/estate --output /path/to/report
```

Run Technical Truth:

```bash
relic audit /path/to/estate --technical-truth
```

Run reusable-capability acquisition:

```bash
relic acquire /path/to/estate
```

Run the product-opportunity pipeline:

```bash
relic audit /path/to/estate --product-discovery
```

Run the v1.0.1 salvageability / Resurrection analysis:

```bash
relic resurrect /path/to/estate --output /path/to/resurrection-report
```

The standalone `relic resurrect` command is the supported v1.0.1 interface. `audit --resurrection` is not part of the current compatibility contract.

## Technical Truth

Technical Truth reconstructs static symbols, imports, calls, routes, application surfaces, workflows, reachability, contradictions, and project families without executing target code.

It uses Python AST analysis and conservative JavaScript/TypeScript structure extraction. Ambiguous relationships remain unresolved instead of being presented as facts. Dynamic imports, reflection, generated code, dependency-injection behavior, and runtime-only routing can remain outside static proof and are reported as limitations.

Useful controls include:

```bash
relic audit ./estate --technical-truth \
  --technical-cache ./report-cache/technical-truth.json \
  --max-data-flow-edges 50000

relic audit ./estate --technical-truth --no-technical-cache
```

## Reusable Assets and Opportunities

Capability Acquisition Mode detects evidence for:

- Orchestrator
- Goal Registry
- Autonomy Loop
- Governance Boundary
- Approval Queue
- Audit Log
- Self-Improvement Proposal
- Resource Request

Documentation, examples, configuration, and tests are discounted so they are not misrepresented as production implementations.

Product discovery reconstructs stated intent, inventories implemented capabilities, rejects weakly supported opportunities, ranks surviving concepts, and emits evidence-linked extraction, GTM, pricing-hypothesis, and validation plans.

## Build Packs

Premium Build Packs convert an evidence-supported opportunity into a deterministic, reviewable implementation package. Reusable assets are hash-verified and governed by provenance, license, secret, path-safety, and approval rules.

Typical lifecycle:

```bash
relic build-pack list product_opportunities.json --json
relic build-pack prepare product_opportunities.json --opportunity opp_ID \
  --target /path/to/rescanned-estate --output preview.json
relic build-pack export preview.json --approval approval.json \
  --target /path/to/rescanned-estate --output /path/to/Relic-Build-Packs
relic build-pack validate /path/to/Relic-Build-Packs/bp_ID --json
```

Build Pack export does not launch a coding agent, shell, dependency installer, Git remote, deployment, or publication action.

See [docs/product-builder-bridge.md](docs/product-builder-bridge.md), [docs/build-pack-schema.md](docs/build-pack-schema.md), and [docs/build-pack-security-and-provenance.md](docs/build-pack-security-and-provenance.md).

## Assisted Build Supervisor

The Supervisor operates only on a managed Build Pack workspace and requires explicit capability approval before a supported action can run. It maintains checkpoints, path confinement, budgets, cancellation behavior, and an audit ledger.

```bash
relic build start /path/to/bp_ID --sessions /path/to/Relic-Build-Sessions --json
relic build plan /path/to/session_ID --file reviewed-actions.json --json
relic build approve /path/to/session_ID --action action_ID \
  --capability file_write --actor "reviewer" --json
relic build run /path/to/session_ID --action action_ID --json
relic build diff /path/to/session_ID --json
relic build finalize /path/to/session_ID --json
```

Production execution remains fail-closed. Only explicitly supported, isolated provider paths and Relic-confined writes are eligible; scanned targets remain read-only.

See [docs/assisted-build-supervisor.md](docs/assisted-build-supervisor.md).

## Entitlements

Production defaults to Free and there is no CLI flag that promotes an entitlement.

- **Free** — scan, core results, reusable assets, risks, reports
- **Pro** — product opportunities
- **Premium** — Build Packs and approved assisted-build capabilities

Signed entitlements and OS credential storage are documented in [docs/licensing.md](docs/licensing.md) and [docs/entitlements-and-privacy.md](docs/entitlements-and-privacy.md).

## Optional LLM reasoning

The deterministic scanner remains the source of evidence. LLM reasoning is an opt-in sidecar that receives only bounded, secret-redacted evidence. It never receives filesystem authority and never gains permission to execute, install, modify, delete, deploy, approve, or provision anything.

Relic supports configured API/OAuth profiles and a bounded Claude Code subscription host. Provider setup and runtime health are treated separately so a failed runtime check cannot be disguised as “configured.”

Profile management:

```bash
relic llm list
relic llm status PROFILE
relic llm logout PROFILE
relic llm remove PROFILE
```

Provider failure leaves deterministic reports intact unless `--llm-required` is explicitly used.

## Windows updates

Packaged Windows builds use a fail-closed update path. A candidate update must pass:

1. strict stable-channel manifest validation;
2. declared filename, size, and SHA-256 verification; and
3. a valid Authenticode signature from the pinned publisher trust policy.

The public v1.0.1 Windows installer is unsigned and therefore **not eligible for automatic updater installation**. Production signing and a trusted stable manifest remain automatic-update gates; manual installation is the supported v1.0.1 path.

See [docs/updater.md](docs/updater.md).

## ZIP safety

ZIP archives are inspected virtually and are never extracted over the target. Relic rejects traversal paths, absolute paths, symlinks, encrypted entries, excessive member counts, excessive uncompressed size, and suspicious compression ratios.

## Determinism and privacy

Reports use stable ordering and bounded evidence. Secret-like values are redacted before report or optional-LLM use. Relic does not grant repository strings instruction authority; scanned text is treated as untrusted data.

## Development

```bash
python -m pytest -q --ignore=tests/fixtures
```

The Windows release workflow additionally freezes the exact commit, hashes the source archive, reruns source tests from the frozen archive, builds both GUI and CLI executables, performs bundled and installed smoke tests, exercises clean install and in-place upgrade, verifies stale-runtime cleanup and config preservation, then verifies uninstall and PATH cleanup.

Release and publication evidence is recorded in [BUILD-STATUS.md](BUILD-STATUS.md) and [releases/v1.0.1/PUBLICATION.json](releases/v1.0.1/PUBLICATION.json). The `v1.0.1` tag and GitHub Release are tied to the exact validated release commit. The unsigned public installer remains manual-install only; the automatic updater stays fail-closed until trusted signing and stable-manifest infrastructure are provisioned.
