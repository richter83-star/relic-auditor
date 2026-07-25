# Relic Auditor

Relic Auditor is a local-first, deterministic appraisal CLI for messy software
estates. It reads folders and ZIP files, detects project types, maps architecture,
finds byte-identical duplicates, and produces review candidates. It never imports,
executes, installs, changes, or deletes scanned code.

## Install

Python 3.11 or newer is required.

```bash
python -m pip install -e .
```

## Run

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

The command creates:

- `estate-report.md`
- `architecture-map.json`
- `extract-candidates.json`
- `archive-candidates.json`
- `delete-candidates.json`
- `pivot-suggestions.json`

Delete candidates are advisory. The command has no delete operation.

## What v0.1 detects

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

This release makes no network calls and has no LLM dependency. The architecture
map includes a deliberately empty reasoning hook for a later semantic appraisal
layer.

## Development

```bash
python -m unittest discover -s tests -v
```
