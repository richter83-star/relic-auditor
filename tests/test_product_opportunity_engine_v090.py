from __future__ import annotations

import json
from pathlib import Path

import pytest

from relic_auditor.audit import audit_estate
from relic_auditor.product_discovery import DiscoveryConfig, discover_products
from relic_auditor.product_discovery.compatibility import (
    load_opportunities,
    normalize_opportunity,
)
from relic_auditor.product_discovery.entitlements import (
    FREE_ENTITLEMENT,
    ProductCapability,
    ProductTier,
    entitlement_for_testing,
)
from relic_auditor.product_discovery.reports import write_product_reports


def sample(**updates):
    value = {
        "title": "Traceable assessment",
        "evidence": ["ev_a", "ev_b"],
        "evidence_score": 75,
        "technical_verification_status": "moderate",
        "extraction_plan": {
            "reuse": ["src/report.py"],
            "missing_interfaces": ["bounded input"],
            "missing_tests": ["end-to-end test"],
            "deployment_work": ["package release"],
        },
    }
    value.update(updates)
    return value


def test_01_default_is_free():
    assert FREE_ENTITLEMENT.tier is ProductTier.FREE


def test_02_free_allows_audit():
    assert FREE_ENTITLEMENT.allows(ProductCapability.AUDIT)


def test_03_free_blocks_opportunities():
    with pytest.raises(PermissionError):
        FREE_ENTITLEMENT.require(ProductCapability.OPPORTUNITIES)


def test_04_pro_allows_opportunities():
    entitlement_for_testing("pro").require(ProductCapability.OPPORTUNITIES)


def test_05_pro_blocks_build_pack():
    with pytest.raises(PermissionError):
        entitlement_for_testing("pro").require(ProductCapability.BUILD_PACK_EXPORT)


def test_06_premium_allows_every_capability():
    premium = entitlement_for_testing("premium")
    assert all(premium.allows(capability) for capability in ProductCapability)


def test_07_public_entitlement_omits_subject():
    assert "subject" not in entitlement_for_testing("premium").public()


def test_08_invalid_tier_rejected():
    with pytest.raises(ValueError):
        entitlement_for_testing("enterprise")


def test_09_missing_id_is_stable():
    assert normalize_opportunity(sample())["opportunity_id"] == normalize_opportunity(sample())["opportunity_id"]


def test_10_existing_id_is_preserved():
    assert normalize_opportunity(sample(opportunity_id="opp_known"))["opportunity_id"] == "opp_known"


def test_11_legacy_reuse_becomes_asset_candidates():
    assert normalize_opportunity(sample())["reusable_assets"][0]["path"] == "src/report.py"


def test_12_missing_components_become_explicit():
    normalized = normalize_opportunity(sample())
    assert normalized["missing_components"] == ["bounded input", "end-to-end test", "package release"]


def test_13_weak_evidence_is_exploratory():
    assert normalize_opportunity(sample(evidence=["ev_a"], evidence_score=20))["evidence_strength"] == "exploratory"


def test_14_two_strong_evidence_items_are_supported():
    assert normalize_opportunity(sample())["evidence_strength"] == "supported"


def test_15_high_technical_status_is_verified():
    assert normalize_opportunity(sample(technical_verification_status="high"))["evidence_strength"] == "verified"


def test_16_supported_opportunity_is_eligible():
    assert normalize_opportunity(sample())["build_pack_readiness"] == "eligible"


def test_17_weak_opportunity_requires_review():
    assert normalize_opportunity(sample(evidence=[]))["build_pack_readiness"] == "review_required"


def test_18_legacy_list_loader():
    loaded = load_opportunities({"schema_version": "0.8", "opportunities": [sample()]})
    assert len(loaded.opportunities) == 1


def test_19_v090_envelope_loader():
    loaded = load_opportunities({"schema_version": "0.9", "opportunities": [sample()]})
    assert loaded.source_schema == "0.9"


def test_20_non_list_opportunities_rejected():
    with pytest.raises(ValueError):
        load_opportunities({"opportunities": {"wrong": "shape"}})


def test_21_old_assets_require_rescan():
    assert load_opportunities({"opportunities": [sample()]}).requires_rescan_for_assets


def test_22_hashed_assets_do_not_require_rescan():
    item = sample(reusable_assets=[{"path": "src/report.py", "sha256": "a" * 64, "evidence": ["ev_a"]}])
    assert not load_opportunities({"opportunities": [item]}).requires_rescan_for_assets


def test_23_file_loading_does_not_mutate_history(tmp_path: Path):
    report = tmp_path / "product_opportunities.json"
    original = json.dumps({"schema_version": "0.8", "opportunities": [sample()]})
    report.write_text(original, encoding="utf-8")
    load_opportunities(report)
    assert report.read_text(encoding="utf-8") == original


def _estate(root: Path) -> None:
    (root / "README.md").write_text("# Tool\nEvidence report workflow.\n", encoding="utf-8")
    (root / "report.py").write_text("def report(findings):\n    return export_pdf(findings)\n", encoding="utf-8")
    (root / "report_test.py").write_text("def test_report():\n    assert report([])\n", encoding="utf-8")
    (root / "cli.py").write_text("import argparse\nargparse.ArgumentParser()\n", encoding="utf-8")
    (root / "runner.py").write_text("import argparse\nparser = argparse.ArgumentParser()\n", encoding="utf-8")


def test_24_discovery_assets_have_observed_hashes(tmp_path: Path):
    _estate(tmp_path)
    result = discover_products(audit_estate(tmp_path), DiscoveryConfig(minimum_evidence_score=1))
    assert result.opportunities
    assert all(asset["sha256"] for asset in result.opportunities[0]["reusable_assets"])


def test_25_discovery_labels_missing_work_as_new_work(tmp_path: Path):
    _estate(tmp_path)
    result = discover_products(audit_estate(tmp_path), DiscoveryConfig(minimum_evidence_score=1))
    assert "End-to-end test for the proposed wedge" in result.opportunities[0]["missing_components"]


def test_26_report_envelope_is_v090(tmp_path: Path):
    _estate(tmp_path)
    result = discover_products(audit_estate(tmp_path), DiscoveryConfig(minimum_evidence_score=1))
    write_product_reports(result, tmp_path / "reports")
    payload = json.loads((tmp_path / "reports" / "product_opportunities.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "0.9"
