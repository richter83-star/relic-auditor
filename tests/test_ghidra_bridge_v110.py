from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from relic_auditor.ghidra_bridge import GhidraEvidenceError, load_ghidra_evidence


def _bundle(target: Path) -> dict[str, object]:
    data = target.read_bytes()
    return {
        "schema": "relic.ghidra.evidence.v1",
        "producer": {"name": "Ghidra", "version": "test"},
        "target": {
            "name": target.name,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "format": "PE",
            "language": "x86:LE:64:default",
        },
        "analysis": {"mode": "static", "target_executed": False},
        "functions": [
            {"id": "140001000", "name": "FUN_140001000"},
            {"id": "140002000", "name": "FUN_140002000"},
        ],
        "imports": [{"id": "WinHttpSendRequest", "library": "winhttp.dll"}],
        "exports": [],
        "strings": [{"id": "s1", "value": "/api/update/check"}],
        "capabilities": [
            {
                "id": "binary.update_manager",
                "title": "Automatic update subsystem",
                "confidence": 0.93,
                "evidence": [
                    "string:s1",
                    "function:140001000",
                    "import:WinHttpSendRequest",
                ],
                "reuse_classification": "architectural_reference",
                "rationale": "Compiled behavior is present but source provenance is unavailable.",
                "recommendation": "Implement an independently authored equivalent.",
            }
        ],
        "limitations": ["symbols stripped"],
    }


def _write_bundle(path: Path, bundle: dict[str, object]) -> None:
    path.write_text(json.dumps(bundle), encoding="utf-8")


def test_loads_and_normalizes_deterministically(tmp_path: Path) -> None:
    target = tmp_path / "sample.exe"
    target.write_bytes(b"MZ\x00static-test-binary")
    bundle_path = tmp_path / "evidence.json"
    bundle = _bundle(target)
    bundle["functions"] = list(reversed(bundle["functions"]))  # type: ignore[arg-type]
    _write_bundle(bundle_path, bundle)

    first = load_ghidra_evidence(bundle_path, target).public()
    second = load_ghidra_evidence(bundle_path, target).public()

    assert first == second
    assert first["target"]["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
    assert first["capabilities"][0]["id"] == "binary.update_manager"
    assert first["capabilities"][0]["evidence"] == [
        "function:140001000",
        "import:WinHttpSendRequest",
        "string:s1",
    ]


def test_rejects_target_digest_mismatch(tmp_path: Path) -> None:
    target = tmp_path / "sample.exe"
    target.write_bytes(b"original")
    bundle_path = tmp_path / "evidence.json"
    bundle = _bundle(target)
    _write_bundle(bundle_path, bundle)
    target.write_bytes(b"mutated")

    with pytest.raises(GhidraEvidenceError, match="SHA-256 mismatch"):
        load_ghidra_evidence(bundle_path, target)


def test_rejects_unknown_evidence_reference(tmp_path: Path) -> None:
    target = tmp_path / "sample.exe"
    target.write_bytes(b"binary")
    bundle_path = tmp_path / "evidence.json"
    bundle = _bundle(target)
    capability = bundle["capabilities"][0]  # type: ignore[index]
    capability["evidence"] = ["function:does-not-exist"]  # type: ignore[index]
    _write_bundle(bundle_path, bundle)

    with pytest.raises(GhidraEvidenceError, match="unknown evidence"):
        load_ghidra_evidence(bundle_path, target)


def test_rejects_decompiled_source_marked_reusable_without_provenance(tmp_path: Path) -> None:
    target = tmp_path / "sample.exe"
    target.write_bytes(b"binary")
    bundle_path = tmp_path / "evidence.json"
    bundle = _bundle(target)
    capability = bundle["capabilities"][0]  # type: ignore[index]
    capability["reuse_classification"] = "reusable_source"  # type: ignore[index]
    _write_bundle(bundle_path, bundle)

    with pytest.raises(GhidraEvidenceError, match="independent_provenance"):
        load_ghidra_evidence(bundle_path, target)


def test_allows_reusable_source_only_with_independent_provenance(tmp_path: Path) -> None:
    target = tmp_path / "sample.exe"
    target.write_bytes(b"binary")
    bundle_path = tmp_path / "evidence.json"
    bundle = _bundle(target)
    capability = bundle["capabilities"][0]  # type: ignore[index]
    capability["reuse_classification"] = "reusable_source"  # type: ignore[index]
    capability["independent_provenance"] = {  # type: ignore[index]
        "source": "separate-source-tree",
        "license": "MIT",
    }
    _write_bundle(bundle_path, bundle)

    evidence = load_ghidra_evidence(bundle_path, target)
    assert evidence.capabilities[0].reuse_classification == "reusable_source"


def test_rejects_conflicting_duplicate_capability_ids(tmp_path: Path) -> None:
    target = tmp_path / "sample.exe"
    target.write_bytes(b"binary")
    bundle_path = tmp_path / "evidence.json"
    bundle = _bundle(target)
    duplicate = dict(bundle["capabilities"][0])  # type: ignore[index]
    duplicate["title"] = "Different meaning"
    bundle["capabilities"].append(duplicate)  # type: ignore[union-attr]
    _write_bundle(bundle_path, bundle)

    with pytest.raises(GhidraEvidenceError, match="conflicting duplicate"):
        load_ghidra_evidence(bundle_path, target)


def test_bridge_module_contains_no_process_execution_api() -> None:
    import relic_auditor.ghidra_bridge as bridge

    source = Path(bridge.__file__).read_text(encoding="utf-8")
    forbidden = ("subprocess", "os.system", "Popen(", "run(", "exec(")
    assert not any(token in source for token in forbidden)
