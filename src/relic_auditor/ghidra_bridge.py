from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SCHEMA_ID = "relic.ghidra.evidence.v1"
REUSE_CLASSIFICATIONS = frozenset(
    {
        "reusable_source",
        "binary_dependency",
        "interface_reusable",
        "architectural_reference",
        "restricted",
        "unknown",
    }
)


class GhidraEvidenceError(ValueError):
    """Raised when imported Ghidra evidence fails validation."""


@dataclass(frozen=True)
class BinaryCapability:
    id: str
    title: str
    confidence: float
    evidence: tuple[str, ...]
    reuse_classification: str
    rationale: str
    recommendation: str | None = None

    def public(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "reuse_classification": self.reuse_classification,
            "rationale": self.rationale,
        }
        if self.recommendation:
            data["recommendation"] = self.recommendation
        return data


@dataclass(frozen=True)
class BinaryEvidence:
    schema: str
    producer: dict[str, Any]
    target: dict[str, Any]
    analysis: dict[str, Any]
    functions: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    imports: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    exports: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    strings: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    capabilities: tuple[BinaryCapability, ...] = field(default_factory=tuple)
    limitations: tuple[str, ...] = field(default_factory=tuple)

    def public(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "producer": self.producer,
            "target": self.target,
            "analysis": self.analysis,
            "functions": list(self.functions),
            "imports": list(self.imports),
            "exports": list(self.exports),
            "strings": list(self.strings),
            "capabilities": [item.public() for item in self.capabilities],
            "limitations": list(self.limitations),
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GhidraEvidenceError(f"{label} must be an object")
    return dict(value)


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise GhidraEvidenceError(f"{label} must be an array")
    return value


def _stable_records(value: Any, label: str) -> tuple[dict[str, Any], ...]:
    records = [_require_mapping(item, f"{label} item") for item in _require_list(value, label)]
    return tuple(sorted(records, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"))))


def _reference_ids(
    functions: tuple[dict[str, Any], ...],
    imports: tuple[dict[str, Any], ...],
    strings: tuple[dict[str, Any], ...],
) -> set[str]:
    refs: set[str] = set()
    for prefix, records in (("function", functions), ("import", imports), ("string", strings)):
        for record in records:
            identifier = record.get("id")
            if identifier is not None:
                refs.add(f"{prefix}:{identifier}")
    return refs


def load_ghidra_evidence(evidence_path: Path, target_path: Path) -> BinaryEvidence:
    """Validate and normalize a Ghidra evidence bundle against local target bytes.

    This function never executes the target and never invokes Ghidra. It only reads
    the target to recompute its SHA-256 and reads the JSON evidence bundle.
    """

    raw = json.loads(evidence_path.read_text(encoding="utf-8"))
    root = _require_mapping(raw, "evidence")
    if root.get("schema") != SCHEMA_ID:
        raise GhidraEvidenceError(f"unsupported schema: {root.get('schema')!r}")

    producer = _require_mapping(root.get("producer"), "producer")
    target = _require_mapping(root.get("target"), "target")
    analysis = _require_mapping(root.get("analysis"), "analysis")
    functions = _stable_records(root.get("functions"), "functions")
    imports = _stable_records(root.get("imports"), "imports")
    exports = _stable_records(root.get("exports"), "exports")
    strings = _stable_records(root.get("strings"), "strings")
    limitations_raw = _require_list(root.get("limitations"), "limitations")
    limitations = tuple(sorted(str(item) for item in limitations_raw))

    expected_digest = str(target.get("sha256", "")).lower()
    actual_digest = _sha256(target_path)
    if not expected_digest or expected_digest != actual_digest:
        raise GhidraEvidenceError(
            f"target SHA-256 mismatch: evidence={expected_digest or '<missing>'} local={actual_digest}"
        )

    expected_size = target.get("size")
    if expected_size is not None and int(expected_size) != target_path.stat().st_size:
        raise GhidraEvidenceError(
            f"target size mismatch: evidence={expected_size} local={target_path.stat().st_size}"
        )

    known_refs = _reference_ids(functions, imports, strings)
    seen_capabilities: dict[str, BinaryCapability] = {}
    for raw_capability in _require_list(root.get("capabilities"), "capabilities"):
        capability = _require_mapping(raw_capability, "capability")
        identifier = str(capability.get("id", "")).strip()
        title = str(capability.get("title", "")).strip()
        rationale = str(capability.get("rationale", "")).strip()
        if not identifier or not title or not rationale:
            raise GhidraEvidenceError("capability requires id, title, and rationale")

        try:
            confidence = float(capability.get("confidence"))
        except (TypeError, ValueError) as exc:
            raise GhidraEvidenceError(f"capability {identifier} has invalid confidence") from exc
        if confidence < 0.0 or confidence > 1.0:
            raise GhidraEvidenceError(f"capability {identifier} confidence must be within 0..1")

        reuse_classification = str(capability.get("reuse_classification", "")).strip()
        if reuse_classification not in REUSE_CLASSIFICATIONS:
            raise GhidraEvidenceError(
                f"capability {identifier} has unsupported reuse classification {reuse_classification!r}"
            )
        if reuse_classification == "reusable_source" and not capability.get("independent_provenance"):
            raise GhidraEvidenceError(
                f"capability {identifier} cannot mark decompiled implementation reusable_source "
                "without independent_provenance"
            )

        evidence = tuple(sorted(str(item) for item in _require_list(capability.get("evidence"), "capability evidence")))
        unknown_refs = sorted(set(evidence) - known_refs)
        if unknown_refs:
            raise GhidraEvidenceError(
                f"capability {identifier} references unknown evidence: {', '.join(unknown_refs)}"
            )

        normalized = BinaryCapability(
            id=identifier,
            title=title,
            confidence=confidence,
            evidence=evidence,
            reuse_classification=reuse_classification,
            rationale=rationale,
            recommendation=(
                str(capability["recommendation"]).strip()
                if capability.get("recommendation")
                else None
            ),
        )
        previous = seen_capabilities.get(identifier)
        if previous is not None and previous != normalized:
            raise GhidraEvidenceError(f"conflicting duplicate capability id: {identifier}")
        seen_capabilities[identifier] = normalized

    normalized_target = dict(target)
    normalized_target["sha256"] = actual_digest
    normalized_target["size"] = target_path.stat().st_size

    return BinaryEvidence(
        schema=SCHEMA_ID,
        producer=producer,
        target=normalized_target,
        analysis=analysis,
        functions=functions,
        imports=imports,
        exports=exports,
        strings=strings,
        capabilities=tuple(sorted(seen_capabilities.values(), key=lambda item: item.id)),
        limitations=limitations,
    )
