from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
import io
from pathlib import Path

from relic_auditor.audit import audit_estate
from relic_auditor.capability_acquisition import (
    RelicMonitor,
    analyze_capability_acquisition,
    write_acquisition_reports,
)
from relic_auditor.cli import main


CAPABILITY_SOURCE = """
class Orchestrator:
    def dispatch_task(self): ...

class GoalRegistry:
    def create_goal(self): ...

def autonomy_loop(iteration_budget, stop_condition):
    observe = plan = act = True
    return evaluate_result()

class PolicyEngine:
    def check_authority(self): ...

class ApprovalQueue:
    approval_status = "pending_approval"
    def approve(self): ...
    def reject(self): ...

class AuditLog:
    event_ledger = "append-only"

def improvement_proposal():
    return evaluate_proposal()

class ResourceRequest:
    def request_budget(self): ...
"""


class CapabilityAcquisitionTests(unittest.TestCase):
    def test_matches_all_requested_capabilities_with_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "control_plane.py").write_text(CAPABILITY_SOURCE, encoding="utf-8")
            result = analyze_capability_acquisition(audit_estate(root))
            detected = {
                row["capability"]
                for row in result.capability_summary
                if row["confidence"] >= 0.18
            }
            self.assertEqual(
                detected,
                {
                    "orchestrator",
                    "goal_registry",
                    "autonomy_loop",
                    "governance_boundary",
                    "approval_queue",
                    "audit_log",
                    "self_improvement_proposal",
                    "resource_request",
                },
            )
            item = result.items[0]
            self.assertTrue(item.inspected)
            self.assertTrue(all(match.evidence for match in item.capability_matches))
            self.assertTrue(all(evidence.line >= 0 for match in item.capability_matches for evidence in match.evidence))

    def test_zip_safety_is_preserved_and_members_are_virtual(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "drop.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("safe/orchestrator.py", "class Orchestrator: pass")
                bundle.writestr("../../escape.py", CAPABILITY_SOURCE)
            audit = audit_estate(archive)
            result = analyze_capability_acquisition(audit)
            self.assertFalse((root.parent / "escape.py").exists())
            self.assertEqual(len(audit.archives[0]["unsafe_members"]), 1)
            self.assertTrue(any(item.path.startswith("drop.zip!") for item in result.items))
            self.assertEqual(result.scan_summary["unsafe_archive_members"], 1)

    def test_every_acquisition_report_redacts_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "estate"
            root.mkdir()
            secret = "sk-abcdefghijklmnopqrstuvwxyz"
            (root / "approval.py").write_text(
                f'api_key="{secret}"\nclass ApprovalQueue: pass\n',
                encoding="utf-8",
            )
            result = analyze_capability_acquisition(audit_estate(root))
            output = Path(temporary) / "reports"
            written = write_acquisition_reports(result, output)
            self.assertEqual(len(written), 4)
            for path in written:
                self.assertNotIn(secret, path.read_text(encoding="utf-8"))
            inventory = json.loads(
                (output / "capability_acquisition_inventory.json").read_text()
            )
            self.assertEqual(inventory["mode"], "deterministic-local-read-only")

    def test_monitor_debounces_and_reprocesses_only_after_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            inbox = Path(temporary) / "inbox"
            inbox.mkdir()
            drop = inbox / "candidate.py"
            drop.write_text("class AuditLog: pass\n", encoding="utf-8")
            monitor = RelicMonitor(inbox, debounce_seconds=2.0)
            self.assertEqual(monitor.poll_once(now=10.0), [])
            self.assertEqual(monitor.poll_once(now=11.9), [])
            ready = monitor.poll_once(now=12.0)
            self.assertEqual([item.path for item in ready], [drop.resolve()])
            self.assertEqual(monitor.poll_once(now=20.0), [])

            drop.write_text("class AuditLog: append_only = True\n", encoding="utf-8")
            self.assertEqual(monitor.poll_once(now=21.0), [])
            self.assertEqual(monitor.poll_once(now=22.9), [])
            self.assertEqual([item.path for item in monitor.poll_once(now=23.0)], [drop.resolve()])

    def test_standard_audit_can_add_acquisition_without_inventory_collision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            estate = root / "estate"
            estate.mkdir()
            (estate / "control.py").write_text(CAPABILITY_SOURCE, encoding="utf-8")
            output = root / "reports"
            with redirect_stdout(io.StringIO()):
                code = main(
                    [
                        "audit",
                        str(estate),
                        "--output",
                        str(output),
                        "--product-discovery",
                        "--capability-acquisition",
                    ]
                )
            self.assertEqual(code, 0)
            self.assertTrue((output / "capability_inventory.json").exists())
            self.assertTrue((output / "capability_acquisition_inventory.json").exists())


if __name__ == "__main__":
    unittest.main()
