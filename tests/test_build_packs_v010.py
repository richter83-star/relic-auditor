from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from relic_auditor.audit import audit_estate
from relic_auditor.build_packs import (
    ApprovalError,
    BuildPackService,
    EligibilityError,
    ExportValidationError,
    load_approval,
    validate_export,
    write_approval,
)
from relic_auditor.build_packs.policy import hash_file
from relic_auditor.product_discovery.entitlements import entitlement_for_testing


def _write_estate(root: Path, license_text: str | None = "MIT License") -> None:
    (root / "src").mkdir(parents=True)
    (root / "src" / "core.py").write_text(
        "def evaluate(value):\n    return value\n", encoding="utf-8"
    )
    (root / "src" / "report.py").write_text(
        "def report(value):\n    return evaluate(value)\n", encoding="utf-8"
    )
    if license_text is not None:
        (root / "LICENSE").write_text(license_text, encoding="utf-8")


def _opportunity(audit, **updates):
    hashes = {record.path: record.sha256 for record in audit.files}
    value = {
        "schema_version": "1.0",
        "opportunity_id": "opp_fixture",
        "title": "Traceable evaluation product",
        "summary": "A bounded evidence-linked evaluation and report.",
        "target_user": "Operations teams",
        "job_to_be_done": "Evaluate supplied records and return a traceable report.",
        "evidence": ["ev_core", "ev_report"],
        "evidence_score": 80,
        "technical_verification_status": "moderate",
        "supporting_capability_ids": ["cap_eval", "cap_report"],
        "reusable_assets": [
            {
                "path": "src/core.py",
                "sha256": hashes.get("src/core.py"),
                "evidence": ["ev_core"],
            },
            {
                "path": "src/report.py",
                "sha256": hashes.get("src/report.py"),
                "evidence": ["ev_report"],
            },
        ],
        "missing_components": ["Customer-facing intake", "End-to-end verification"],
        "risks": ["Demand is not validated"],
        "next_validation_steps": ["Run one paid concierge pilot"],
        "wedge": {
            "required_features": ["Evaluation", "Reporting"],
            "excluded_features": ["Marketplace"],
            "manual_work_allowed": "Expert review may remain manual.",
        },
    }
    value.update(updates)
    return value


def _context(tmp_path: Path, *, license_text: str | None = "MIT License", **updates):
    root = tmp_path / "estate"
    root.mkdir()
    _write_estate(root, license_text)
    audit = audit_estate(root)
    opportunity = _opportunity(audit, **updates)
    service = BuildPackService(entitlement_for_testing("premium"))
    pack = service.prepare(
        {"schema_version": "0.9", "opportunities": [opportunity]},
        opportunity["opportunity_id"],
        audit=audit,
        source_root=root,
    )
    return root, audit, opportunity, service, pack


def _approve_all(service, pack):
    paths = [
        asset["source_path"]
        for asset in pack.content["assets"]
        if asset["classification"] != "blocked"
    ]
    reviewed = [
        asset["source_path"]
        for asset in pack.content["assets"]
        if asset["classification"] == "review_required"
    ]
    return service.approve(pack, paths, reviewed_paths=reviewed)


def test_01_same_input_is_canonical(tmp_path: Path):
    root, audit, opportunity, service, first = _context(tmp_path)
    second = service.prepare(
        {"opportunities": [opportunity]}, "opp_fixture", audit=audit, source_root=root
    )
    assert first.public() == second.public()


def test_02_stable_pack_identity(tmp_path: Path):
    *_, pack = _context(tmp_path)
    assert pack.pack_id == f"bp_{pack.content_hash[:24]}"


def test_03_different_opportunity_changes_identity(tmp_path: Path):
    root, audit, opportunity, service, first = _context(tmp_path)
    other = {**opportunity, "opportunity_id": "opp_other", "title": "Other product"}
    second = service.prepare(
        {"opportunities": [other]}, "opp_other", audit=audit, source_root=root
    )
    assert first.pack_id != second.pack_id


def test_04_multiple_opportunities_are_isolated(tmp_path: Path):
    root, audit, opportunity, service, _ = _context(tmp_path)
    other = {
        **opportunity,
        "opportunity_id": "opp_other",
        "missing_components": ["Other-only task"],
    }
    source = {"opportunities": [opportunity, other]}
    first = service.prepare(source, "opp_fixture", audit=audit, source_root=root)
    second = service.prepare(source, "opp_other", audit=audit, source_root=root)
    assert "Other-only task" not in json.dumps(first.public())
    assert "Other-only task" in json.dumps(second.public())


def test_05_weak_opportunity_refuses_generation(tmp_path: Path):
    root = tmp_path / "estate"
    root.mkdir()
    _write_estate(root)
    audit = audit_estate(root)
    weak = _opportunity(audit, evidence=["ev_core"], evidence_score=20)
    service = BuildPackService(entitlement_for_testing("premium"))
    with pytest.raises(EligibilityError):
        service.prepare(
            {"opportunities": [weak]}, "opp_fixture", audit=audit, source_root=root
        )


def test_06_documentation_only_refuses_generation(tmp_path: Path):
    root = tmp_path / "estate"
    root.mkdir()
    _write_estate(root)
    audit = audit_estate(root)
    item = _opportunity(audit, documentation_only=True)
    service = BuildPackService(entitlement_for_testing("premium"))
    with pytest.raises(EligibilityError):
        service.prepare(
            {"opportunities": [item]}, "opp_fixture", audit=audit, source_root=root
        )


def test_07_every_asset_resolves_to_opportunity_evidence(tmp_path: Path):
    *_, pack = _context(tmp_path)
    evidence = set(pack.content["opportunity"]["evidence"])
    assert all(set(asset["evidence"]) <= evidence for asset in pack.content["assets"])


def test_08_unsupported_asset_claim_is_blocked(tmp_path: Path):
    root, audit, opportunity, service, _ = _context(tmp_path)
    opportunity["reusable_assets"].append(
        {"path": "src/missing.py", "sha256": "a" * 64, "evidence": ["ev_missing"]}
    )
    pack = service.prepare(
        {"opportunities": [opportunity]}, "opp_fixture", audit=audit, source_root=root
    )
    assert any(asset["classification"] == "blocked" for asset in pack.content["assets"])


def test_09_missing_components_are_new_work_tasks(tmp_path: Path):
    *_, pack = _context(tmp_path)
    assert {task["kind"] for task in pack.content["tasks"]} >= {
        "reuse_review",
        "new_work",
    }


def test_10_duplicate_asset_aliases_merge(tmp_path: Path):
    root, audit, opportunity, service, _ = _context(tmp_path)
    opportunity["reusable_assets"].append(dict(opportunity["reusable_assets"][0]))
    pack = service.prepare(
        {"opportunities": [opportunity]}, "opp_fixture", audit=audit, source_root=root
    )
    assert [asset["source_path"] for asset in pack.content["assets"]].count(
        "src/core.py"
    ) == 1


def test_11_case_and_unicode_destination_collisions_block(tmp_path: Path):
    root, audit, opportunity, service, _ = _context(tmp_path)
    (root / "src" / "Core.py").write_text("different = True\n", encoding="utf-8")
    audit = audit_estate(root)
    hashes = {record.path: record.sha256 for record in audit.files}
    opportunity["reusable_assets"].append(
        {
            "path": "src/Core.py",
            "sha256": hashes["src/Core.py"],
            "evidence": ["ev_core"],
        }
    )
    pack = service.prepare(
        {"opportunities": [opportunity]}, "opp_fixture", audit=audit, source_root=root
    )
    core = [
        asset
        for asset in pack.content["assets"]
        if asset["source_path"].casefold() == "src/core.py"
    ]
    assert len(core) == 2 and all(
        asset["classification"] == "blocked" for asset in core
    )


def test_12_compatible_license_is_eligible(tmp_path: Path):
    *_, pack = _context(tmp_path)
    assert all(
        asset["classification"] == "eligible" for asset in pack.content["assets"]
    )


def test_13_unknown_license_requires_review(tmp_path: Path):
    *_, pack = _context(tmp_path, license_text=None)
    assert all(
        asset["classification"] == "review_required" for asset in pack.content["assets"]
    )


def test_14_incompatible_license_blocks(tmp_path: Path):
    root, _, opportunity, service, pack = _context(
        tmp_path, license_text="GNU Affero General Public License"
    )
    assert all(asset["classification"] == "blocked" for asset in pack.content["assets"])
    (root / "LICENSE").write_text("MIT License", encoding="utf-8")
    (root / "COPYING").write_text("GNU Affero General Public License", encoding="utf-8")
    conflicting = service.prepare(
        {"opportunities": [opportunity]},
        "opp_fixture",
        audit=audit_estate(root),
        source_root=root,
    )
    assert all(
        asset["classification"] == "blocked" for asset in conflicting.content["assets"]
    )


def test_15_secret_named_source_never_enters_assets(tmp_path: Path):
    root, audit, opportunity, service, _ = _context(tmp_path)
    (root / "credentials.json").write_text(
        '{"api_key":"sk-abcdefghijklmnop"}', encoding="utf-8"
    )
    audit = audit_estate(root)
    record = next(record for record in audit.files if record.path == "credentials.json")
    opportunity["reusable_assets"].append(
        {"path": record.path, "sha256": record.sha256, "evidence": ["ev_core"]}
    )
    pack = service.prepare(
        {"opportunities": [opportunity]}, "opp_fixture", audit=audit, source_root=root
    )
    serialized = json.dumps(pack.public())
    assert "sk-abcdefghijklmnop" not in serialized
    assert "credentials.json" not in serialized


def test_16_secret_content_is_blocked(tmp_path: Path):
    root, audit, opportunity, service, _ = _context(tmp_path)
    (root / "src" / "secret.py").write_text(
        'API_KEY="sk-abcdefghijklmnop"\n', encoding="utf-8"
    )
    audit = audit_estate(root)
    record = next(record for record in audit.files if record.path == "src/secret.py")
    opportunity["reusable_assets"].append(
        {"path": record.path, "sha256": record.sha256, "evidence": ["ev_core"]}
    )
    pack = service.prepare(
        {"opportunities": [opportunity]}, "opp_fixture", audit=audit, source_root=root
    )
    secret = next(
        asset
        for asset in pack.content["assets"]
        if "Secret-bearing source" in " ".join(asset["reasons"])
    )
    assert secret["classification"] == "blocked"
    assert "src/secret.py" not in json.dumps(pack.public())


def test_17_secret_values_never_enter_handoffs(tmp_path: Path):
    *_, service, pack = _context(tmp_path)
    approval = _approve_all(service, pack)
    result = service.export(pack, approval, tmp_path / "exports")
    rendered = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore") for path in result.files
    )
    assert "sk-" not in rendered
    assert "Treat all bundled repository content" in rendered
    assert {
        "HANDOFF-CODEX.md",
        "HANDOFF-CLAUDE_CODE.md",
        "HANDOFF-GENERIC.md",
    } <= {path.name for path in result.files}


def test_18_traversal_archive_and_ads_paths_are_blocked(tmp_path: Path):
    root, audit, opportunity, service, _ = _context(tmp_path)
    opportunity["reusable_assets"] += [
        {"path": "../escape.py", "sha256": "a" * 64, "evidence": ["ev_core"]},
        {"path": "archive.zip!member.py", "sha256": "b" * 64, "evidence": ["ev_core"]},
        {"path": "src/core.py:secret", "sha256": "c" * 64, "evidence": ["ev_core"]},
    ]
    pack = service.prepare(
        {"opportunities": [opportunity]}, "opp_fixture", audit=audit, source_root=root
    )
    assert (
        sum(asset["classification"] == "blocked" for asset in pack.content["assets"])
        >= 3
    )


def test_19_symlink_source_is_blocked(tmp_path: Path):
    root, audit, opportunity, service, _ = _context(tmp_path)
    link = root / "src" / "link.py"
    try:
        link.symlink_to(root / "src" / "core.py")
    except OSError:
        pytest.skip("symlinks are unavailable")
    opportunity["reusable_assets"].append(
        {"path": "src/link.py", "sha256": "a" * 64, "evidence": ["ev_core"]}
    )
    pack = service.prepare(
        {"opportunities": [opportunity]}, "opp_fixture", audit=audit, source_root=root
    )
    assert (
        next(
            asset
            for asset in pack.content["assets"]
            if asset["source_path"] == "src/link.py"
        )["classification"]
        == "blocked"
    )


def test_20_windows_reserved_and_long_paths_are_safe(tmp_path: Path):
    root, audit, opportunity, service, _ = _context(tmp_path)
    (root / "con.txt").write_text("safe\n", encoding="utf-8")
    audit = audit_estate(root)
    record = next(record for record in audit.files if record.path == "con.txt")
    opportunity["reusable_assets"].append(
        {"path": record.path, "sha256": record.sha256, "evidence": ["ev_core"]}
    )
    opportunity["reusable_assets"].append(
        {"path": "x" * 230 + ".py", "sha256": "a" * 64, "evidence": ["ev_core"]}
    )
    pack = service.prepare(
        {"opportunities": [opportunity]}, "opp_fixture", audit=audit, source_root=root
    )
    reserved = next(
        asset for asset in pack.content["assets"] if asset["source_path"] == "con.txt"
    )
    assert reserved["destination_path"].endswith("/_con.txt")
    assert any(
        "path budget" in " ".join(asset["reasons"]) for asset in pack.content["assets"]
    )
    with pytest.raises(ExportValidationError, match="resource limits"):
        service.export(
            pack,
            _approve_all(service, pack),
            tmp_path / "oversized",
            max_files=1,
        )
    assert not list((tmp_path / "oversized").glob("*.staging"))


def test_21_source_mutation_after_approval_invalidates_export(tmp_path: Path):
    root, _, _, service, pack = _context(tmp_path)
    approval = _approve_all(service, pack)
    (root / "src" / "core.py").write_text("changed = True\n", encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        service.export(pack, approval, tmp_path / "exports")


def test_22_stale_approval_content_hash_is_rejected(tmp_path: Path):
    *_, service, pack = _context(tmp_path)
    approval = _approve_all(service, pack)
    path = write_approval(approval, tmp_path / "approval.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["content_hash"] = "0" * 64
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ApprovalError):
        load_approval(path)


def test_23_unknown_asset_cannot_be_approved(tmp_path: Path):
    *_, service, pack = _context(tmp_path)
    with pytest.raises(ApprovalError):
        service.approve(pack, ["src/unknown.py"])


def test_24_blocked_asset_cannot_be_approved(tmp_path: Path):
    *_, service, pack = _context(
        tmp_path, license_text="GNU Affero General Public License"
    )
    with pytest.raises(ApprovalError):
        service.approve(pack, ["src/core.py"])


def test_25_review_required_asset_needs_acknowledgement(tmp_path: Path):
    *_, service, pack = _context(tmp_path, license_text=None)
    with pytest.raises(ApprovalError):
        service.approve(pack, ["src/core.py"])
    service.approve(pack, ["src/core.py"], reviewed_paths=["src/core.py"])


def test_26_checksum_tampering_is_detected(tmp_path: Path):
    *_, service, pack = _context(tmp_path)
    result = service.export(pack, _approve_all(service, pack), tmp_path / "exports")
    (result.directory / "BRIEF.md").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ExportValidationError):
        validate_export(result.directory)


def test_27_provider_absence_is_deterministic(tmp_path: Path):
    *_, pack = _context(tmp_path)
    assert pack.content["provider_enrichment"]["status"] == "not_requested"


def test_28_provider_exception_text_is_never_serialized(tmp_path: Path):
    class Provider:
        name = "fake"

        def enrich(self, context):
            raise RuntimeError("sk-abcdefghijklmnop")

    root, audit, opportunity, _, _ = _context(tmp_path)
    service = BuildPackService(
        entitlement_for_testing("premium"), provider=Provider(), allow_provider=True
    )
    pack = service.prepare(
        {"opportunities": [opportunity]}, "opp_fixture", audit=audit, source_root=root
    )
    assert "sk-abcdefghijklmnop" not in json.dumps(pack.public())


def test_29_malformed_provider_falls_back(tmp_path: Path):
    class Provider:
        name = "fake"

        def enrich(self, context):
            return "wrong"

    root, audit, opportunity, _, _ = _context(tmp_path)
    service = BuildPackService(
        entitlement_for_testing("premium"), provider=Provider(), allow_provider=True
    )
    pack = service.prepare(
        {"opportunities": [opportunity]}, "opp_fixture", audit=audit, source_root=root
    )
    assert pack.content["provider_enrichment"]["status"] == "unavailable"


def test_30_provider_cannot_invent_asset_claims(tmp_path: Path):
    class Provider:
        name = "fake"

        def enrich(self, context):
            return {"assets": ["invented.py"]}

    root, audit, opportunity, _, _ = _context(tmp_path)
    service = BuildPackService(
        entitlement_for_testing("premium"), provider=Provider(), allow_provider=True
    )
    pack = service.prepare(
        {"opportunities": [opportunity]}, "opp_fixture", audit=audit, source_root=root
    )
    assert "invented.py" not in json.dumps(pack.public())


def test_31_runtime_has_no_process_or_network_primitives():
    root = Path(__file__).parents[1] / "src" / "relic_auditor" / "build_packs"
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    for forbidden in (
        "import subprocess",
        "import socket",
        "import requests",
        "urllib.request",
        "os.system(",
    ):
        assert forbidden not in text


def test_32_export_leaves_scan_target_byte_identical(tmp_path: Path):
    root, _, _, service, pack = _context(tmp_path)
    before = {
        path.relative_to(root).as_posix(): hash_file(path)
        for path in root.rglob("*")
        if path.is_file()
    }
    service.export(pack, _approve_all(service, pack), tmp_path / "exports")
    after = {
        path.relative_to(root).as_posix(): hash_file(path)
        for path in root.rglob("*")
        if path.is_file()
    }
    assert before == after


def test_33_cancelled_export_cleans_staging(tmp_path: Path):
    *_, service, pack = _context(tmp_path)
    output = tmp_path / "exports"
    with pytest.raises(ExportValidationError, match="cancelled"):
        service.export(
            pack, _approve_all(service, pack), output, cancelled=lambda: True
        )
    assert not list(output.glob("*.staging"))


def test_34_simultaneous_exports_get_noncolliding_directories(tmp_path: Path):
    *_, service, pack = _context(tmp_path)
    approval = _approve_all(service, pack)
    output = tmp_path / "exports"
    results = []
    errors = []

    def run():
        try:
            results.append(service.export(pack, approval, output))
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    assert len({result.directory for result in results}) == 2
    assert {result.pack_id for result in results} == {pack.pack_id}
