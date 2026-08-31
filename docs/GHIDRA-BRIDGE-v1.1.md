# Relic Auditor v1.1 — Ghidra Bridge

## Purpose

Relic Auditor v1.1 adds optional deep binary evidence without weakening the product's core safety contract.

Relic Auditor itself does **not** execute scanned targets, invoke scanned binaries, import target code, install target dependencies, or run Ghidra as a subprocess in phase 1.

Instead, Ghidra operates as an external static-analysis producer. Relic consumes a deterministic evidence bundle exported by Ghidra and treats all decompiler output as evidence, never as automatically reusable source.

## Phase 1 architecture

```text
Target binary
   |
   v
Ghidra (external static analysis)
   |
   v
relic-ghidra-evidence.json
   |
   v
Relic Ghidra Bridge validator
   |
   v
Normalized BinaryEvidence
   |
   +--> Scan / Technical Evidence
   +--> Answer
   +--> Prepare
   +--> Build Pack provenance + rebuild decisions
```

## Hard safety boundary

The Relic process must not:

- execute a scanned target;
- invoke a scanned target as a subprocess;
- import or dynamically load scanned code;
- install target dependencies;
- invoke Ghidra automatically in phase 1;
- trust paths or hashes supplied by an evidence bundle without local verification;
- treat decompiled code as reusable source by default.

The external Ghidra step is opt-in and separately initiated by the user.

## Evidence bundle

Schema ID: `relic.ghidra.evidence.v1`

Required top-level fields:

- `schema`
- `producer`
- `target`
- `analysis`
- `functions`
- `imports`
- `exports`
- `strings`
- `capabilities`
- `limitations`

The target section includes:

- file name
- byte length
- SHA-256 of the analyzed binary
- detected executable format
- processor/language identifier when available

Relic must recompute the target digest from the local binary before accepting evidence as bound to that target.

## Reuse classifications

Binary evidence uses one of these classifications:

1. `reusable_source` — source exists separately and reuse is supported by provenance/license evidence.
2. `binary_dependency` — the compiled component may be integrated or redistributed subject to license review.
3. `interface_reusable` — a documented/public interface or protocol can be used without copying implementation.
4. `architectural_reference` — behavior/design may guide an independent implementation.
5. `restricted` — copyright/license/provenance blocks reuse.
6. `unknown` — human review required.

Decompiler output defaults to `architectural_reference` or `unknown`, never `reusable_source` solely because Ghidra produced pseudocode.

## Capability evidence

A normalized capability should include:

- stable identifier
- title
- confidence
- evidence references
- reuse classification
- rationale
- optional rebuild recommendation

Example:

```json
{
  "id": "binary.update_manager",
  "title": "Automatic update subsystem",
  "confidence": 0.93,
  "evidence": [
    "function:140032820",
    "import:WinHttpSendRequest",
    "string:/api/update/check"
  ],
  "reuse_classification": "architectural_reference",
  "rationale": "Behavior is present in compiled code; source provenance is unavailable.",
  "recommendation": "Implement a clean-room equivalent from behavior and interface evidence."
}
```

## Validation requirements

Relic must fail closed when:

- schema ID is unsupported;
- the evidence file is malformed;
- target SHA-256 does not match the selected binary;
- evidence references nonexistent function/import/string IDs;
- duplicate capability IDs conflict;
- confidence values are outside 0..1;
- the bundle attempts to mark decompiled implementation as reusable source without independent provenance.

## Determinism

Normalized output must be deterministic for the same evidence bundle and local target bytes. Lists are sorted by stable keys before serialization.

## Build Pack behavior

Binary findings may appear in Build Packs as technical evidence, architectural references, dependencies, risks, exclusions, or implementation tasks.

Binary findings must not cause target bytes to be copied into a Build Pack unless existing asset/provenance policy separately authorizes that copy.

## Phase 2, explicitly deferred

A future release may provide a user-configured Ghidra headless adapter. That adapter must live behind a separate execution boundary and cannot silently replace the phase-1 import contract.

Deferred items include:

- WSL discovery;
- `analyzeHeadless` orchestration;
- sandbox/work directory lifecycle;
- Java/Ghidra version pinning;
- timeout/resource controls;
- cancellation;
- headless script packaging;
- installer decisions.

These are intentionally not part of the first bridge implementation.
