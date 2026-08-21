from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from relic_auditor.audit import audit_estate
from relic_auditor.entrypoint import main
from relic_auditor.resurrection import (
    ResurrectionConfig,
    resurrect_estate,
    write_resurrection_reports,
)
from relic_auditor.resurrection.reasoner import _verify_citation_grounding
from relic_auditor.technical_truth import analyze_technical_truth


class ResurrectionTests(unittest.TestCase):
    def test_01_all_stubs_emits_deterministic_toss_it(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "service.py").write_text(
                (
                    "def parse_payload(p):\n"
                    "    raise NotImplementedError\n"
                    "def run_engine(e):\n"
                    "    pass\n"
                    "def emit_result(r):\n"
                    "    return None\n"
                ),
                encoding="utf-8",
            )
            audit = audit_estate(root)
            truth = analyze_technical_truth(audit)
            result = resurrect_estate(audit, truth)
            self.assertEqual(result.verdict, "TOSS_IT")
            self.assertTrue(result.gate.bypass_llm)
            self.assertEqual(result.gate.reason, "NO_SUBSTANTIVE_GRAPH")
            self.assertEqual(result.blueprint.salvageable_core_paths, [])

    def test_02_insufficient_nodes_emits_toss_it(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "util.py").write_text(
                "def helper(x):\n    return x + 1\n",
                encoding="utf-8",
            )
            audit = audit_estate(root)
            truth = analyze_technical_truth(audit)
            result = resurrect_estate(
                audit,
                truth,
                ResurrectionConfig(min_subgraph_nodes=3),
            )
            self.assertEqual(result.verdict, "TOSS_IT")
            self.assertTrue(result.gate.bypass_llm)
            self.assertEqual(result.gate.reason, "INSUFFICIENT_SUBSTANTIVE_NODES")

    def test_03_connected_real_core_emits_resurrect(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "app.py").write_text(
                (
                    "from fastapi import FastAPI\n"
                    "app = FastAPI()\n"
                    "@app.post('/analyze')\n"
                    "def analyze_endpoint(data):\n"
                    "    parsed = parse_ast(data)\n"
                    "    validated = validate_rules(parsed)\n"
                    "    return emit_report(validated)\n"
                    "def parse_ast(data):\n"
                    "    return {'tree': data}\n"
                    "def validate_rules(tree):\n"
                    "    return {'valid': bool(tree)}\n"
                    "def emit_report(status):\n"
                    "    return {'report': status}\n"
                ),
                encoding="utf-8",
            )
            audit = audit_estate(root)
            truth = analyze_technical_truth(audit)
            result = resurrect_estate(audit, truth)
            self.assertEqual(result.verdict, "RESURRECT")
            self.assertFalse(result.gate.bypass_llm)
            self.assertEqual(result.gate.verdict, "PROCEED_TO_REASONING")
            self.assertIsNotNone(result.blueprint)
            self.assertGreater(len(result.blueprint.salvageable_core_paths), 0)
            self.assertGreaterEqual(result.verdict_confidence, 0.60)

    def test_04_reports_written_with_secret_redaction(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out_dir = root / "report"
            (root / "engine.py").write_text(
                (
                    "from fastapi import FastAPI\n"
                    "app = FastAPI()\n"
                    "SECRET_KEY = 'sk-live-1234567890abcdef1234567890abcdef'\n"
                    "@app.get('/status')\n"
                    "def status():\n"
                    "    a = step_one()\n"
                    "    b = step_two(a)\n"
                    "    return step_three(b)\n"
                    "def step_one(): return 1\n"
                    "def step_two(x): return x + 1\n"
                    "def step_three(y): return y * 2\n"
                ),
                encoding="utf-8",
            )
            audit = audit_estate(root)
            truth = analyze_technical_truth(audit)
            result = resurrect_estate(audit, truth)
            written = write_resurrection_reports(result, out_dir)
            self.assertTrue(written["json"].exists())
            self.assertTrue(written["markdown"].exists())
            md_text = written["markdown"].read_text(encoding="utf-8")
            self.assertIn("Relic Auditor — Resurrection Plan", md_text)
            self.assertNotIn("sk-live-1234567890abcdef1234567890abcdef", md_text)

    def test_05_citation_verification_detects_hallucinations(self):
        envelope = {
            "substantive_paths": ["src/real.py"],
            "substantive_symbols": [
                {"symbol_id": "sym_real", "name": "real_fn", "file": "src/real.py"}
            ],
            "subgraph_id": "subgraph_123",
            "surface_anchors": [],
        }
        fake_llm_response = {
            "verdict": "RESURRECT",
            "salvageable_core_paths": ["src/real.py", "src/fake_magic_ai.py"],
            "citations": [
                {
                    "claim": "AI magic works",
                    "source_evidence_ids": ["sym_real", "sym_hallucinated"],
                }
            ],
        }
        verification = _verify_citation_grounding(fake_llm_response, envelope)
        self.assertFalse(verification.valid)
        self.assertEqual(len(verification.ungrounded_claims), 2)
        self.assertTrue(
            any("fake_magic_ai.py" in claim for claim in verification.ungrounded_claims)
        )
        self.assertTrue(
            any("sym_hallucinated" in claim for claim in verification.ungrounded_claims)
        )

    def test_06_entrypoint_resurrect_command(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "src_target"
            target.mkdir()
            out_dir = root / "resurrect_output"
            (target / "main.py").write_text(
                "def hello(): pass\n",
                encoding="utf-8",
            )
            exit_code = main(["resurrect", str(target), "-o", str(out_dir)])
            self.assertEqual(exit_code, 0)
            self.assertTrue((out_dir / "resurrection-plan.json").exists())
            self.assertTrue((out_dir / "resurrection-plan.md").exists())

    def test_07_market_context_is_explicitly_offline_heuristic(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "scanner.py").write_text(
                (
                    "from fastapi import FastAPI\n"
                    "app = FastAPI()\n"
                    "@app.post('/scan')\n"
                    "def run_security_scan(target):\n"
                    "    findings = check_vulnerabilities(target)\n"
                    "    return generate_security_report(findings)\n"
                    "def check_vulnerabilities(t):\n"
                    "    return [{'cve': 'CVE-2026-0001'}]\n"
                    "def generate_security_report(f):\n"
                    "    return {'audit': f}\n"
                ),
                encoding="utf-8",
            )
            audit = audit_estate(root)
            truth = analyze_technical_truth(audit)
            result = resurrect_estate(
                audit,
                truth,
                ResurrectionConfig(include_market_facts=True),
            )
            self.assertEqual(result.verdict, "RESURRECT")
            self.assertIsNotNone(result.market_context)
            self.assertEqual(result.market_context.status, "offline_heuristic")
            self.assertEqual(
                result.market_context.epistemic_rating,
                "external_market_speculation",
            )
            self.assertIn(
                "Bundled static benchmark heuristics",
                result.market_context.sources[0],
            )


if __name__ == "__main__":
    unittest.main()
