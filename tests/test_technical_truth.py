from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from relic_auditor.audit import audit_estate
from relic_auditor.product_discovery import discover_products
from relic_auditor.technical_truth import TechnicalTruthConfig, analyze_technical_truth
from relic_auditor.technical_truth.adapters import parse_cache_info, parse_source
from relic_auditor.technical_truth.reports import TECHNICAL_OUTPUTS, write_technical_truth_reports


FIXTURES = Path(__file__).parent / "fixtures"


class TechnicalTruthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.false = analyze_technical_truth(audit_estate(FIXTURES / "false_compliance"))
        cls.verified = analyze_technical_truth(audit_estate(FIXTURES / "verified_workflow"))

    def test_01_python_ast_extraction(self):
        result = parse_source("a.py", "def hello():\n return 1\n", "f")
        self.assertEqual(result["symbols"][0]["name"], "hello")

    def test_02_typescript_structural_extraction(self):
        result = parse_source("a.ts", "export function hello() { return 1; }", "f")
        self.assertEqual(result["symbols"][0]["language"], "typescript")

    def test_03_stable_symbol_ids(self):
        a = parse_source("x.py", "def f(): pass\n", "family")
        b = parse_source("x.py", "def f(): pass\n", "family")
        self.assertEqual(a["symbols"][0]["symbol_id"], b["symbols"][0]["symbol_id"])

    def test_04_import_resolution(self):
        self.assertTrue(any(e["type"] == "imports" for e in self.verified.graph["edges"]))

    def test_05_call_edges(self):
        self.assertTrue(any(e["type"] == "calls" for e in self.verified.graph["edges"]))

    def test_06_route_registration(self):
        self.assertTrue(all(e["registered"] for e in self.verified.surfaces["endpoints"]))

    def test_07_ui_to_api_link(self):
        self.assertTrue(any(e["type"] == "triggers" and e["source"].startswith("ui_") for e in self.verified.graph["edges"]))

    def test_08_api_to_service_link(self):
        workflow = next(w for w in self.verified.workflows if "policies" in w["name"])
        self.assertGreaterEqual(len(workflow["steps"]), 4)

    def test_09_service_to_database_link(self):
        workflow = next(w for w in self.verified.workflows if "policies" in w["name"])
        self.assertTrue(any("save" in str(step).lower() for step in workflow["steps"]))

    def test_10_queue_matching(self):
        self.assertTrue(any(e["type"] == "consumed_by" for e in self.verified.graph["edges"]))

    def test_11_worker_reachability(self):
        self.assertTrue(any(w["completion_status"] == "verified_end_to_end" for w in self.verified.workflows))

    def test_12_schema_detection(self):
        self.assertEqual(len(self.false.surfaces["schemas"]), 3)

    def test_13_test_only_not_production_proof(self):
        evaluator = next(r for r in self.false.reachability if r["name"] == "evaluate_policy")
        self.assertEqual(evaluator["status"], "test_only")

    def test_14_mock_detection(self):
        self.assertTrue(any(t["kind"] == "mock" for t in self.false.surfaces["tests"]))

    def test_15_unregistered_route(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "requirements.txt").write_text("fastapi")
            (root / "routes.py").write_text("from fastapi import APIRouter\nrouter=APIRouter()\n@router.post('/x')\ndef x(): return 1\n")
            result = analyze_technical_truth(audit_estate(root))
            self.assertFalse(result.surfaces["endpoints"][0]["registered"])

    def test_16_dead_symbol(self):
        report = next(r for r in self.false.reachability if r["name"] == "generate_pdf_report")
        self.assertIn(report["status"], {"unreferenced", "unknown"})

    def test_17_contradiction_detection(self):
        self.assertGreaterEqual(len(self.false.contradictions), 3)

    def test_18_broken_workflow(self):
        upload = next(w for w in self.false.workflows if "documents" in w["name"])
        self.assertIn("no matching production consumer", " ".join(upload["missing_links"]).lower())

    def test_19_capability_status(self):
        billing = next(c for c in self.false.capabilities if c["key"] == "subscription-billing")
        self.assertEqual(billing["status"], "contradicted")

    def test_20_confidence_components(self):
        self.assertTrue(all("parser_certainty" in c["score_components"] for c in self.false.capabilities))

    def test_21_project_family_fingerprint(self):
        self.assertTrue(self.false.project_families[0]["evidence"]["shared_file_hashes"])

    def test_22_backup_deduplication(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name in ("app", "app-backup", "app-worktree"):
                (root / name).mkdir()
                (root / name / "package.json").write_text('{"name":"app"}')
            result = analyze_technical_truth(audit_estate(root))
            self.assertEqual(len(result.project_families), 1)

    def test_23_divergence_preserved(self):
        self.assertTrue(self.verified.project_families[0]["divergence_preserved"])

    def test_24_unsupported_language(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "main.rs").write_text("fn main() {}")
            result = analyze_technical_truth(audit_estate(root))
            self.assertEqual(result.summary["files_unsupported"], 1)

    def test_25_parser_failure_isolated(self):
        result = parse_source("bad.py", "def broken(:\n", "f")
        self.assertEqual(result["status"], "invalid_syntax")

    def test_26_no_secret_in_outputs(self):
        self.assertNotIn("example-not-a-real-key", json.dumps(self.false.__dict__))

    def test_27_no_code_execution(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            marker = root / "EXECUTED"
            (root / "evil.py").write_text(f"import os\nos.system('touch {marker}')\n")
            analyze_technical_truth(audit_estate(root))
            self.assertFalse(marker.exists())

    def test_28_no_source_modification(self):
        target = FIXTURES / "false_compliance"
        before = {p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob("*") if p.is_file()}
        analyze_technical_truth(audit_estate(target))
        after = {p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_29_deterministic_repeated_run(self):
        other = analyze_technical_truth(audit_estate(FIXTURES / "false_compliance"))
        self.assertEqual(json.dumps(self.false.summary, sort_keys=True), json.dumps(other.summary, sort_keys=True))

    def test_30_cache_reuse(self):
        before = parse_cache_info().hits
        parse_source("cache.py", "def cached(): return 1\n", "f")
        parse_source("cache.py", "def cached(): return 1\n", "f")
        self.assertGreater(parse_cache_info().hits, before)

    def test_31_large_graph_limit(self):
        limited = analyze_technical_truth(audit_estate(FIXTURES / "verified_workflow"), TechnicalTruthConfig(max_graph_nodes=3))
        self.assertTrue(limited.graph["truncated"])

    def test_32_v02_integration(self):
        audit = audit_estate(FIXTURES / "false_compliance")
        discovery = discover_products(audit, technical_truth=self.false)
        self.assertTrue(all("technical_verification_status" in o for o in discovery.opportunities))

    def test_33_technical_gate_caps_readiness(self):
        audit = audit_estate(FIXTURES / "false_compliance")
        discovery = discover_products(audit, technical_truth=self.false)
        self.assertTrue(all(o["product_readiness_confidence"] < 90 for o in discovery.opportunities))

    def test_34_low_confidence_wording(self):
        audit = audit_estate(FIXTURES / "false_compliance")
        discovery = discover_products(audit, technical_truth=self.false)
        for opportunity in discovery.opportunities:
            if opportunity["speculative"]:
                self.assertIn("could support", opportunity["summary"])

    def test_35_report_schemas(self):
        with tempfile.TemporaryDirectory() as td:
            paths = write_technical_truth_reports(self.false, Path(td))
            self.assertEqual({p.name for p in paths}, set(TECHNICAL_OUTPUTS.values()))
            self.assertEqual(json.loads((Path(td) / "technical_truth_summary.json").read_text())["schema_version"], "1.0")

    def test_36_json_serialization_stability(self):
        first = json.dumps(self.verified.graph, sort_keys=True)
        second = json.dumps(analyze_technical_truth(audit_estate(FIXTURES / "verified_workflow")).graph, sort_keys=True)
        self.assertEqual(first, second)

    def test_37_false_claim_acceptance_conclusion(self):
        self.assertEqual(self.false.summary["verified_workflows"], 0)
        statuses = {c["key"]: c["status"] for c in self.false.capabilities}
        self.assertEqual(statuses["report-generation"], "implemented_but_disconnected")
        self.assertEqual(statuses["subscription-billing"], "contradicted")

    def test_38_required_fixture_matrix_is_safe_and_analyzable(self):
        names = {
            "false_compliance", "verified_workflow", "interface_only", "schema_only",
            "test_only", "disconnected_worker", "disconnected_producer",
            "unregistered_route", "family_estate", "malicious_repository",
            "unsupported_language", "multi_project",
        }
        for name in sorted(names):
            target = FIXTURES / name
            before = {p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob("*") if p.is_file()}
            result = analyze_technical_truth(audit_estate(target))
            after = {p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob("*") if p.is_file()}
            self.assertEqual(before, after, name)
            self.assertFalse(result.summary["safety"]["source_executed"], name)

    def test_39_plain_aliased_multiple_and_relative_imports(self):
        result = parse_source(
            "package/module.py",
            (
                "import os, stripe as st\n"
                "import package.submodule\n"
                "from .db import save as persist\n"
                "from ..core import emit\n"
            ),
            "family",
        )
        self.assertEqual(result["status"], "success")
        bindings = {item["local"]: item for item in result["import_bindings"]}
        self.assertEqual(bindings["os"]["source"], "os")
        self.assertEqual(bindings["st"]["source"], "stripe")
        self.assertEqual(bindings["package"]["source"], "package.submodule")
        self.assertEqual(bindings["persist"]["source"], ".db")
        self.assertEqual(bindings["persist"]["imported"], "save")
        self.assertEqual(bindings["emit"]["source"], "..core")
        self.assertEqual(
            result["imports"],
            ["..core", ".db", "os", "package.submodule", "stripe"],
        )

    def test_40_parser_failure_blocks_negative_conclusions(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "README.md").write_text(
                "This product provides compliance reports.",
                encoding="utf-8",
            )
            (root / "broken.py").write_text("def broken(:\n", encoding="utf-8")
            result = analyze_technical_truth(audit_estate(root))
            self.assertEqual(
                result.summary["conclusion_gate"]["status"],
                "insufficient_evidence",
            )
            self.assertFalse(
                result.summary["conclusion_gate"]["negative_conclusions_allowed"]
            )
            self.assertEqual(result.contradictions, [])
            output = root.parent / f"{root.name}-truth-output"
            write_technical_truth_reports(result, output)
            report = (output / "technical_truth_report.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("INSUFFICIENT EVIDENCE", report)

    def test_41_documentation_contradictions_are_project_scoped(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            alpha = root / "alpha"
            beta = root / "beta"
            alpha.mkdir()
            beta.mkdir()
            (alpha / "pyproject.toml").write_text(
                "[project]\nname='alpha'\nversion='1.0.0'\n",
                encoding="utf-8",
            )
            (alpha / "README.md").write_text(
                "Alpha generates a report.",
                encoding="utf-8",
            )
            (alpha / "main.py").write_text(
                "def unrelated(value):\n    return value\n",
                encoding="utf-8",
            )
            (beta / "pyproject.toml").write_text(
                "[project]\nname='beta'\nversion='1.0.0'\n",
                encoding="utf-8",
            )
            (beta / "main.py").write_text(
                (
                    "from fastapi import FastAPI\n"
                    "app = FastAPI()\n"
                    "@app.post('/run')\n"
                    "def handle(value):\n"
                    "    saved = save_result(value)\n"
                    "    return generate_report(saved)\n"
                    "def save_result(value):\n"
                    "    return {'saved': value}\n"
                    "def generate_report(value):\n"
                    "    return {'report': value}\n"
                ),
                encoding="utf-8",
            )
            result = analyze_technical_truth(audit_estate(root))
            report_findings = [
                item
                for item in result.contradictions
                if "report-related" in item["claim"]
            ]
            self.assertEqual(len(report_findings), 1)
            self.assertEqual(report_findings[0]["evidence"], ["alpha/README.md"])
            self.assertIsNone(report_findings[0]["capability_id"])

    def test_42_structural_capability_is_not_silently_omitted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "requirements.txt").write_text(
                "fastapi\n",
                encoding="utf-8",
            )
            (root / "main.py").write_text(
                (
                    "import fastapi\n"
                    "app = fastapi.FastAPI()\n"
                    "@app.post('/dossiers')\n"
                    "def receive(payload):\n"
                    "    decision = adjudicate(payload)\n"
                    "    persist_dossier(decision)\n"
                    "    return emit(decision)\n"
                    "def adjudicate(payload):\n"
                    "    return {'decision': bool(payload)}\n"
                    "def persist_dossier(decision):\n"
                    "    return {'stored': decision}\n"
                    "def emit(decision):\n"
                    "    return {'delivered': decision}\n"
                ),
                encoding="utf-8",
            )
            result = analyze_technical_truth(audit_estate(root))
            unclassified = [
                item
                for item in result.capabilities
                if item["category"] == "unclassified"
            ]
            self.assertEqual(len(unclassified), 1)
            self.assertEqual(
                unclassified[0]["status"],
                "verified_end_to_end",
            )
            self.assertTrue(unclassified[0]["supporting_symbols"])

    def test_43_fixture_source_does_not_count_as_production(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "pyproject.toml").write_text(
                "[project]\nname='fixtures-only'\nversion='1.0.0'\n",
                encoding="utf-8",
            )
            fixtures = root / "tests" / "fixtures"
            fixtures.mkdir(parents=True)
            for index in range(20):
                (fixtures / f"sample_{index}.py").write_text(
                    "def sample():\n    return 1\n",
                    encoding="utf-8",
                )
            project = audit_estate(root).projects[0]
            self.assertEqual(project.source_files, 0)
            self.assertEqual(project.test_files, 20)
            self.assertEqual(project.appraisal_category, "Fragment / needs context")

    def test_44_call_resolution_does_not_cross_project_families(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            alpha = root / "alpha"
            beta = root / "beta"
            alpha.mkdir()
            beta.mkdir()
            for project in (alpha, beta):
                (project / "pyproject.toml").write_text(
                    (
                        "[project]\n"
                        f"name='{project.name}'\n"
                        "version='1.0.0'\n"
                    ),
                    encoding="utf-8",
                )
            (alpha / "main.py").write_text(
                (
                    "from fastapi import FastAPI\n"
                    "app = FastAPI()\n"
                    "@app.post('/run')\n"
                    "def run(value):\n"
                    "    return transform(value)\n"
                ),
                encoding="utf-8",
            )
            (beta / "service.py").write_text(
                "def transform(value):\n    return value\n",
                encoding="utf-8",
            )
            result = analyze_technical_truth(audit_estate(root))
            symbols = {item["symbol_id"]: item for item in result.symbols}
            cross_family_calls = [
                edge
                for edge in result.graph["edges"]
                if edge["type"] == "calls"
                and edge["source"] in symbols
                and edge["target"] in symbols
                and symbols[edge["source"]]["project_family_id"]
                != symbols[edge["target"]]["project_family_id"]
            ]
            self.assertEqual(cross_family_calls, [])

    def test_45_working_product_outranks_stub_vaporware(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            working = root / "working"
            stubs = root / "stubs"
            working.mkdir()
            stubs.mkdir()
            shared_prefix = (
                "import os\n"
                "from fastapi import FastAPI\n"
                "app = FastAPI()\n"
                "@app.post('/evaluate')\n"
            )
            (working / "requirements.txt").write_text(
                "fastapi\n",
                encoding="utf-8",
            )
            (working / "main.py").write_text(
                shared_prefix
                + (
                    "def run(payload):\n"
                    "    finding = evaluate_rule(payload)\n"
                    "    persist_result(finding)\n"
                    "    return generate_report(finding)\n"
                    "def evaluate_rule(payload):\n"
                    "    return {'finding': bool(payload)}\n"
                    "def persist_result(finding):\n"
                    "    return {'stored': finding}\n"
                    "def generate_report(finding):\n"
                    "    return {'report': finding}\n"
                ),
                encoding="utf-8",
            )
            (stubs / "requirements.txt").write_text(
                "fastapi\n",
                encoding="utf-8",
            )
            (stubs / "main.py").write_text(
                shared_prefix
                + (
                    "def run(payload):\n"
                    "    raise NotImplementedError()\n"
                    "def evaluate_rule(payload):\n"
                    "    raise NotImplementedError()\n"
                    "def persist_result(finding):\n"
                    "    raise NotImplementedError()\n"
                    "def generate_report(finding):\n"
                    "    raise NotImplementedError()\n"
                ),
                encoding="utf-8",
            )
            real = analyze_technical_truth(audit_estate(working))
            vapor = analyze_technical_truth(audit_estate(stubs))
            real_status = {
                item["key"]: item["status"] for item in real.capabilities
            }
            vapor_status = {
                item["key"]: item["status"] for item in vapor.capabilities
            }
            for key in (
                "rule-evaluation",
                "data-persistence",
                "report-generation",
            ):
                self.assertEqual(real_status[key], "verified_end_to_end")
                self.assertEqual(vapor_status[key], "interface_only")
            self.assertGreater(
                min(
                    item["confidence"]
                    for item in real.capabilities
                    if item["key"] in real_status
                ),
                max(
                    item["confidence"]
                    for item in vapor.capabilities
                    if item["key"] in vapor_status
                ),
            )


if __name__ == "__main__":
    unittest.main()
