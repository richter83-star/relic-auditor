from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from relic_auditor.audit import audit_estate
from relic_auditor.product_discovery import DiscoveryConfig, discover_products
from relic_auditor.product_discovery.pipeline import _generic_penalty
from relic_auditor.product_discovery.reports import PRODUCT_OUTPUTS, write_product_reports


def make_estate(root: Path) -> None:
    (root / "README.md").write_text(
        "# Atlas Enterprise\nA complete production-ready all-in-one system.\n", encoding="utf-8"
    )
    (root / "package.json").write_text(
        json.dumps({"name": "atlas", "dependencies": {"next": "15", "stripe": "18"}}),
        encoding="utf-8",
    )
    (root / "src").mkdir()
    files = {
        "src/import.ts": "export function bulkImport(csv) { return ingest(csv); }\n",
        "src/import_test.ts": "test('bulk import', () => score(importCsv('x')))\n",
        "src/score.ts": "export function evaluate(record) { return score(record); }\n",
        "src/report.ts": "export function report(findings) { return exportPdf(findings); }\n",
        "src/report_test.ts": "test('report export', () => dashboard(report([])))\n",
        "src/workflow.ts": "export function workflow(job) { return queue(job); }\n",
        "src/worker.ts": "export function orchestrate(job) { return pipeline(job); }\n",
        "src/security.ts": "export function securityScan(file) { return vulnerability(file); }\n",
        "src/threat.ts": "export function threatReport(x) { return finding(x); }\n",
        "src/auth.ts": "export function login(jwt) { return authentication(jwt); }\n",
        "src/billing.ts": "export function checkout() { return stripe.subscription(); }\n",
    }
    for path, content in files.items():
        (root / path).write_text(content, encoding="utf-8")


class ProductDiscoveryTests(unittest.TestCase):
    def run_discovery(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name) / "estate"
        root.mkdir()
        make_estate(root)
        return temporary, root, discover_products(audit_estate(root))

    def test_01_monolith_extractable_subsystem(self):
        t, _, result = self.run_discovery()
        self.addCleanup(t.cleanup)
        self.assertTrue(any("security" in o["title"].lower() for o in result.opportunities))

    def test_02_readme_exaggeration_is_contradicted(self):
        t, _, result = self.run_discovery()
        self.addCleanup(t.cleanup)
        self.assertIn("claims maturity", " ".join(result.intent["stated_vs_implemented"]).lower())

    def test_03_partial_saas_capabilities(self):
        t, _, result = self.run_discovery()
        self.addCleanup(t.cleanup)
        keys = {c["key"] for c in result.capabilities}
        self.assertTrue({"authentication", "billing"} <= keys)

    def test_04_internal_cli_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "pyproject.toml").write_text("[project.scripts]\ninspect='tool:main'\n")
            (root / "tool.py").write_text("import argparse\nargparse.ArgumentParser()\n")
            result = discover_products(audit_estate(root))
            self.assertIn("developer-cli", {c["key"] for c in result.capabilities})

    def test_05_backups_are_family(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name in ("alpha", "alpha-backup"):
                (root / name).mkdir()
                (root / name / "package.json").write_text('{"name":"alpha"}')
            result = discover_products(audit_estate(root))
            self.assertTrue(any(len(f["members"]) == 2 for f in result.project_families))

    def test_06_complementary_capabilities(self):
        t, _, result = self.run_discovery()
        self.addCleanup(t.cleanup)
        self.assertGreaterEqual(len(result.opportunities), 3)

    def test_07_empty_starter_has_no_serious_opportunity(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "package.json").write_text('{"name":"starter"}')
            result = discover_products(audit_estate(root))
            self.assertEqual(result.opportunities, [])

    def test_08_secrets_redacted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            secret = "sk-abcdefghijklmnopqrstuvwxyz"
            (root / "README.md").write_text(f"# Tool\nreport token={secret}\n")
            result = discover_products(audit_estate(root))
            self.assertNotIn(secret, json.dumps(result.evidence_index))

    def test_09_malicious_script_not_executed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            marker = root / "EXECUTED"
            (root / "evil.py").write_text(f"open({str(marker)!r}, 'w').write('bad')\nreport='x'\n")
            discover_products(audit_estate(root))
            self.assertFalse(marker.exists())

    def test_10_offline_discovery(self):
        t, _, result = self.run_discovery()
        self.addCleanup(t.cleanup)
        self.assertEqual(result.market_validation["status"], "not_performed")

    def test_11_market_disabled_shape(self):
        t, _, result = self.run_discovery()
        self.addCleanup(t.cleanup)
        self.assertFalse(result.market_validation["repository_findings_are_market_validated"])

    def test_12_stable_schema(self):
        t, _, result = self.run_discovery()
        self.addCleanup(t.cleanup)
        self.assertTrue(all(o["schema_version"] == "1.0" for o in result.opportunities))

    def test_13_deterministic_repeated_run(self):
        t, root, first = self.run_discovery()
        self.addCleanup(t.cleanup)
        second = discover_products(audit_estate(root))
        self.assertEqual(json.dumps(first.opportunities, sort_keys=True), json.dumps(second.opportunities, sort_keys=True))

    def test_14_weak_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "one.py").write_text("report = True\n")
            result = discover_products(audit_estate(root))
            self.assertEqual(result.opportunities, [])

    def test_15_generic_language_penalty(self):
        self.assertGreater(_generic_penalty("An AI-powered platform for businesses of all sizes"), 0)

    def test_16_contradictions_propagate(self):
        t, _, result = self.run_discovery()
        self.addCleanup(t.cleanup)
        self.assertTrue(all(o["contradictions"] for o in result.opportunities))

    def test_17_large_sampling_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "large.py").write_text("report = True\n" + ("x" * 100_000))
            result = discover_products(audit_estate(root), DiscoveryConfig(maximum_sampled_source_size=1024))
            self.assertLess(len(json.dumps(result.evidence_index)), 10_000)

    def test_18_product_outputs_written(self):
        t, root, result = self.run_discovery()
        self.addCleanup(t.cleanup)
        output = root.parent / "report"
        paths = write_product_reports(result, output)
        self.assertEqual({p.name for p in paths}, set(PRODUCT_OUTPUTS.values()))

    def test_19_rank_components_are_exposed(self):
        t, _, result = self.run_discovery()
        self.addCleanup(t.cleanup)
        self.assertTrue(all("repository_evidence" in o["score_components"] for o in result.opportunities))

    def test_20_no_llm_configured_operates(self):
        t, root, _ = self.run_discovery()
        self.addCleanup(t.cleanup)
        result = discover_products(audit_estate(root), DiscoveryConfig(reasoning_provider="none"))
        self.assertIsInstance(result.opportunities, list)

    def test_21_market_enabled_without_adapter_is_explicit(self):
        t, root, _ = self.run_discovery()
        self.addCleanup(t.cleanup)
        result = discover_products(audit_estate(root), DiscoveryConfig(offline=False, market_validation=True))
        self.assertEqual(result.market_validation["status"], "not_configured")

    def test_22_every_proposal_has_failure_reason_and_evidence(self):
        t, _, result = self.run_discovery()
        self.addCleanup(t.cleanup)
        self.assertTrue(all(len(o["evidence"]) >= 2 and o["reject_reason"] for o in result.opportunities))


if __name__ == "__main__":
    unittest.main()
