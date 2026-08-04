from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import datetime
from pathlib import Path

from relic_auditor.cli import build_parser, main
from relic_auditor.dashboard import (
    DashboardOptions,
    automatic_report_directory,
    build_cleanup_plan,
    candidate_key,
    default_reports_root,
    export_dashboard_bundle,
    list_report_history,
    run_dashboard_audit,
    summarize_dashboard_bundle,
)


class DashboardCoreTests(unittest.TestCase):
    def _estate(self, root: Path) -> Path:
        estate = root / "estate"
        estate.mkdir()
        (estate / "package.json").write_text(
            json.dumps({"dependencies": {"next": "15.0.0", "react": "19.0.0"}}),
            encoding="utf-8",
        )
        (estate / "page.tsx").write_text(
            "export default function Page() { return <main>Relic</main> }\n",
            encoding="utf-8",
        )
        (estate / "page-copy.tsx").write_text(
            "export default function Page() { return <main>Relic</main> }\n",
            encoding="utf-8",
        )
        return estate

    def test_dashboard_parser_accepts_optional_target(self) -> None:
        args = build_parser().parse_args(["dashboard", "somewhere"])
        self.assertEqual(args.command, "dashboard")
        self.assertEqual(args.target, Path("somewhere"))

    def test_quick_dashboard_scan_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            estate = self._estate(Path(temporary))
            before = {
                path.relative_to(estate).as_posix(): path.read_bytes()
                for path in estate.rglob("*")
                if path.is_file()
            }
            events: list[tuple[int, str]] = []
            bundle = run_dashboard_audit(
                estate,
                DashboardOptions(technical_truth=False),
                lambda value, message: events.append((value, message)),
            )
            after = {
                path.relative_to(estate).as_posix(): path.read_bytes()
                for path in estate.rglob("*")
                if path.is_file()
            }
            self.assertEqual(before, after)
            self.assertIsNone(bundle.technical_truth)
            self.assertIsNone(bundle.discovery)
            self.assertEqual(events[-1][0], 100)
            self.assertFalse((estate.parent / "estate-relic-report").exists())

    def test_product_resurrection_runs_technical_truth_offline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            estate = self._estate(Path(temporary))
            bundle = run_dashboard_audit(
                estate,
                DashboardOptions(
                    technical_truth=False,
                    product_discovery=True,
                ),
            )
            self.assertIsNotNone(bundle.technical_truth)
            self.assertIsNotNone(bundle.discovery)
            self.assertEqual(
                bundle.discovery.market_validation["status"],
                "not_performed",
            )
            self.assertFalse(
                bundle.discovery.market_validation[
                    "repository_findings_are_market_validated"
                ]
            )

    def test_capability_acquisition_dashboard_mode_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            estate = self._estate(root)
            (estate / "approval.py").write_text(
                "class ApprovalQueue:\n    approval_status = 'pending_approval'\n",
                encoding="utf-8",
            )
            bundle = run_dashboard_audit(
                estate,
                DashboardOptions(
                    technical_truth=False,
                    capability_acquisition=True,
                ),
            )
            self.assertIsNotNone(bundle.acquisition)
            self.assertIsNone(bundle.technical_truth)
            output = root / "acquisition-reports"
            written = export_dashboard_bundle(bundle, output)
            self.assertIn(output / "capability_acquisition_report.md", written)
            self.assertIn(output / "capability_acquisition_inventory.json", written)

    def test_export_adds_advisory_cleanup_plan_and_preserves_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            estate = self._estate(root)
            bundle = run_dashboard_audit(
                estate,
                DashboardOptions(technical_truth=True),
            )
            candidate = bundle.audit.delete_candidates[0]
            key = candidate_key("delete-review", candidate.path)
            before = {
                path.relative_to(estate).as_posix(): path.read_bytes()
                for path in estate.rglob("*")
                if path.is_file()
            }
            output = root / "reports"
            written = export_dashboard_bundle(bundle, output, {key: "review"})
            after = {
                path.relative_to(estate).as_posix(): path.read_bytes()
                for path in estate.rglob("*")
                if path.is_file()
            }
            self.assertEqual(before, after)
            self.assertIn(output / "cleanup-plan.json", written)
            plan = json.loads((output / "cleanup-plan.json").read_text(encoding="utf-8"))
            self.assertTrue(plan["advisory_only"])
            self.assertFalse(plan["safety"]["files_deleted"])
            self.assertEqual(plan["decision_counts"]["review"], 1)

    def test_export_inside_target_is_rejected_before_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            estate = self._estate(Path(temporary))
            bundle = run_dashboard_audit(
                estate,
                DashboardOptions(technical_truth=False),
            )
            with self.assertRaisesRegex(ValueError, "outside"):
                export_dashboard_bundle(bundle, estate / "reports")
            self.assertFalse((estate / "reports").exists())

    def test_cleanup_plan_is_deterministic_and_validates_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            estate = self._estate(Path(temporary))
            bundle = run_dashboard_audit(
                estate,
                DashboardOptions(technical_truth=False),
            )
            one = build_cleanup_plan(bundle, {"extract:a.py": "keep"})
            two = build_cleanup_plan(bundle, {"extract:a.py": "keep"})
            self.assertEqual(
                json.dumps(one, sort_keys=True),
                json.dumps(two, sort_keys=True),
            )
            with self.assertRaisesRegex(ValueError, "unsupported decision"):
                build_cleanup_plan(bundle, {"extract:a.py": "delete"})

    def test_automatic_report_hierarchy_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reports = default_reports_root(root / "Documents")
            target = root / 'Powerhouse: Core'
            destination = automatic_report_directory(
                target,
                reports,
                generated_at=datetime(2026, 8, 1, 9, 30, 5),
            )
            self.assertEqual(
                destination,
                reports / "Powerhouse- Core reports" / "2026-08-01_09-30-05",
            )
            destination.mkdir(parents=True)
            report = destination / "estate-report.md"
            report.write_text("# Report\n", encoding="utf-8")
            history = list_report_history(reports)
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0].project, "Powerhouse- Core")
            self.assertEqual(history[0].full_report, report)

    def test_plain_english_summary_answers_four_questions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            estate = self._estate(Path(temporary))
            bundle = run_dashboard_audit(
                estate,
                DashboardOptions(
                    technical_truth=True,
                    product_discovery=True,
                    capability_acquisition=True,
                ),
            )
            summary = summarize_dashboard_bundle(bundle)
            self.assertEqual(set(summary), {"found", "valuable", "risky", "next"})
            self.assertIn("files", summary["found"])
            self.assertIn("review", summary["next"].lower())

    def test_complete_appraisal_exports_without_modifying_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            estate = self._estate(root)
            before = {
                path.relative_to(estate).as_posix(): path.read_bytes()
                for path in estate.rglob("*")
                if path.is_file()
            }
            bundle = run_dashboard_audit(
                estate,
                DashboardOptions(
                    technical_truth=True,
                    product_discovery=True,
                    capability_acquisition=True,
                ),
            )
            destination = automatic_report_directory(
                estate,
                root / "Documents" / "Relic Auditor" / "Reports",
                generated_at=datetime(2026, 8, 1, 10, 0, 0),
            )
            written = export_dashboard_bundle(bundle, destination)
            after = {
                path.relative_to(estate).as_posix(): path.read_bytes()
                for path in estate.rglob("*")
                if path.is_file()
            }
            self.assertEqual(before, after)
            self.assertIn(destination / "estate-report.md", written)
            self.assertTrue((destination / "technical_truth_report.md").is_file())

    def test_cli_explains_missing_gui_extra(self) -> None:
        if importlib.util.find_spec("PySide6") is not None:
            self.skipTest("PySide6 is installed in this environment")
        error = io.StringIO()
        with redirect_stderr(error):
            code = main(["dashboard"])
        self.assertEqual(code, 2)
        self.assertIn('".[gui]"', error.getvalue())


if __name__ == "__main__":
    unittest.main()
