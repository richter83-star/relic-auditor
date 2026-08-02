from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from relic_auditor.audit import audit_estate
from relic_auditor.technical_truth import TechnicalTruthConfig, analyze_technical_truth
from relic_auditor.technical_truth.adapters import parse_source
from relic_auditor.technical_truth.js_ast import tokenize
from relic_auditor.technical_truth.lineage import inspect_git_lineage
from relic_auditor.technical_truth.reports import write_technical_truth_reports


class V04SemanticResolutionTests(unittest.TestCase):
    def test_token_ast_ignores_comments_and_string_contents(self):
        source = """
        // fakeCall(secret)
        const text = "otherFakeCall(password)";
        export function real(input) { return persist(input); }
        """
        result = parse_source("app.ts", source, "family")
        targets = {item["target_name"] for item in result["references"]}
        self.assertIn("persist", targets)
        self.assertNotIn("fakeCall", targets)
        self.assertNotIn("otherFakeCall", targets)
        self.assertTrue(all(token.value != "secret" for token in tokenize(source)))

    def test_token_ast_owns_calls_and_extracts_environment_reads(self):
        result = parse_source(
            "worker.ts",
            "export function run(job) { send(job); return process.env.QUEUE_NAME; }\n",
            "family",
        )
        call = next(item for item in result["references"] if item["target_name"] == "send")
        self.assertEqual(call["caller_name"], "run")
        self.assertEqual(call["argument_names"], ["job"])
        self.assertEqual(result["environment_reads"], ["QUEUE_NAME"])

    def test_import_alias_resolves_to_exported_symbol(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "package.json").write_text('{"name":"alias-flow"}', encoding="utf-8")
            (root / "service.ts").write_text(
                "export function persist(input) { return input; }\n", encoding="utf-8"
            )
            (root / "api.ts").write_text(
                'import { persist as save } from "./service";\n'
                "export function handler(payload) { return save(payload); }\n"
                'app.post("/items", handler);\n',
                encoding="utf-8",
            )
            truth = analyze_technical_truth(audit_estate(root))
        calls = [
            edge
            for edge in truth.graph["edges"]
            if edge["type"] == "calls"
            and edge["extraction_method"] == "import_binding_resolution"
        ]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["confidence"], 0.96)

    def test_ambiguous_same_name_does_not_create_project_wide_call_edge(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "package.json").write_text('{"name":"ambiguous"}', encoding="utf-8")
            (root / "one.ts").write_text("export function save(x) { return x; }\n")
            (root / "two.ts").write_text("export function save(x) { return x; }\n")
            (root / "caller.ts").write_text(
                "export function caller(x) { return save(x); }\n"
            )
            truth = analyze_technical_truth(audit_estate(root))
        caller = next(symbol for symbol in truth.symbols if symbol["name"] == "caller")
        outgoing = [
            edge
            for edge in truth.graph["edges"]
            if edge["source"] == caller["symbol_id"] and edge["type"] == "calls"
        ]
        self.assertEqual(outgoing, [])

    def test_argument_to_parameter_data_flow_is_recorded(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "package.json").write_text('{"name":"data-flow"}', encoding="utf-8")
            (root / "sink.ts").write_text(
                "export function persist(document) { return document; }\n"
            )
            (root / "source.ts").write_text(
                'import { persist } from "./sink";\n'
                "export function submit(payload) { return persist(payload); }\n"
            )
            truth = analyze_technical_truth(audit_estate(root))
        flow = next(
            edge
            for edge in truth.graph["edges"]
            if edge["type"] == "passes_data"
            and edge["extraction_method"] == "import_binding_resolution"
        )
        self.assertEqual(
            flow["mapping"], [{"argument": "payload", "parameter": "document"}]
        )

    def test_persistent_cache_reuses_parse_results(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "target"
            root.mkdir()
            (root / "main.py").write_text("def run(value):\n    return value\n")
            cache = Path(td) / "report" / "cache.json"
            audit = audit_estate(root)
            config = TechnicalTruthConfig(cache_path=str(cache))
            first = analyze_technical_truth(audit, config)
            with patch(
                "relic_auditor.technical_truth.analyzer.parse_source",
                side_effect=AssertionError("parser should not run for a cache hit"),
            ):
                second = analyze_technical_truth(audit, config)
            self.assertTrue(cache.is_file())
            self.assertEqual(first.symbols, second.symbols)

    def test_persistent_cache_invalidates_on_content_change(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "target"
            root.mkdir()
            source = root / "main.py"
            cache = Path(td) / "report" / "cache.json"
            config = TechnicalTruthConfig(cache_path=str(cache))
            source.write_text("def before():\n    return 1\n")
            analyze_technical_truth(audit_estate(root), config)
            source.write_text("def after():\n    return 2\n")
            truth = analyze_technical_truth(audit_estate(root), config)
            cache_document = json.loads(cache.read_text())
            self.assertEqual([symbol["name"] for symbol in truth.symbols], ["after"])
            self.assertEqual(len(cache_document["entries"]), 2)

    def test_static_git_lineage_reads_head_and_remote_without_git(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            git = root / ".git"
            (git / "refs" / "heads").mkdir(parents=True)
            (git / "HEAD").write_text("ref: refs/heads/main\n")
            (git / "refs" / "heads" / "main").write_text("a" * 40 + "\n")
            (git / "config").write_text(
                '[remote "origin"]\n\turl = https://example.invalid/relic.git\n'
            )
            lineage = inspect_git_lineage(root, ["."])
        self.assertEqual(lineage[0]["branch"], "main")
        self.assertEqual(lineage[0]["head"], "a" * 40)
        self.assertEqual(
            lineage[0]["remote_urls"], ["https://example.invalid/relic.git"]
        )

    def test_worktree_pointer_outside_scan_boundary_is_not_followed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "target"
            root.mkdir()
            (root / ".git").write_text("gitdir: ../../outside/git\n")
            lineage = inspect_git_lineage(root, ["."])
        self.assertTrue(lineage[0]["outside_boundary_not_followed"])
        self.assertIsNone(lineage[0]["head"])

    def test_framework_evidence_and_stub_classification(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "package.json").write_text(
                '{"name":"stub-api","dependencies":{"express":"5"}}'
            )
            (root / "api.ts").write_text(
                'import express from "express";\n'
                "export function generateReport() { throw new Error('Not implemented'); }\n"
                'app.post("/reports", generateReport);\n'
            )
            truth = analyze_technical_truth(audit_estate(root))
        self.assertIn("Express", truth.summary["coverage"]["frameworks"])
        report = next(
            capability
            for capability in truth.capabilities
            if capability["key"] == "report-generation"
        )
        self.assertEqual(report["status"], "interface_only")

    def test_mock_ui_screen_is_explicitly_contradictory(self):
        fixture = Path(__file__).parent / "fixtures" / "false_compliance"
        truth = analyze_technical_truth(audit_estate(fixture))
        screens = truth.surfaces["ui_screens"]
        self.assertEqual(screens[0]["name"], "ReportDashboard")
        self.assertTrue(screens[0]["mock_only"])
        self.assertTrue(
            any(
                item["technical_finding"] == "The surface contains mock or fixture data."
                for item in truth.contradictions
            )
        )
        with tempfile.TemporaryDirectory() as td:
            write_technical_truth_reports(truth, Path(td))
            report = (Path(td) / "technical_truth_report.md").read_text()
        self.assertIn("not verified as the complete product", report)
        self.assertIn("no matching production consumer", report)
        self.assertIn("renders mock data", report)

    def test_data_flow_limit_is_explicit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "package.json").write_text('{"name":"bounded-flow"}')
            (root / "sink.ts").write_text(
                "export function one(a) { return a; }\n"
                "export function two(b) { return b; }\n"
            )
            (root / "source.ts").write_text(
                'import { one, two } from "./sink";\n'
                "export function run(x, y) { one(x); return two(y); }\n"
            )
            truth = analyze_technical_truth(
                audit_estate(root), TechnicalTruthConfig(max_data_flow_edges=1)
            )
        self.assertTrue(truth.graph["data_flow_truncated"])
        self.assertTrue(truth.summary["data_flow_truncated"])
        self.assertEqual(
            len(
                [
                    edge
                    for edge in truth.graph["edges"]
                    if edge["type"] in {"passes_data", "reads_from", "writes_to"}
                ]
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
