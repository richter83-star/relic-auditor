from __future__ import annotations

import json
import io
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from relic_auditor.audit import audit_estate
from relic_auditor.cli import main
from relic_auditor.reports import write_reports
from relic_auditor.safety import redact_secrets


class AuditTests(unittest.TestCase):
    def test_detects_next_and_fastapi_and_writes_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "estate"
            root.mkdir()
            (root / "web").mkdir()
            (root / "web" / "package.json").write_text(
                json.dumps({"dependencies": {"next": "15.0.0", "react": "19.0.0"}}),
                encoding="utf-8",
            )
            (root / "api").mkdir()
            (root / "api" / "requirements.txt").write_text("fastapi==0.115\n", encoding="utf-8")
            (root / "api" / "main.py").write_text(
                "from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8"
            )

            result = audit_estate(root)
            kinds = {kind for project in result.projects for kind in project.kinds}
            self.assertIn("Next.js", kinds)
            self.assertIn("FastAPI", kinds)
            self.assertEqual(
                result.pivot_suggestions[0]["title"], "Consolidate into a full-stack product shell"
            )

            output = Path(temporary) / "report"
            paths = write_reports(result, output)
            self.assertEqual(len(paths), 6)
            self.assertTrue((output / "estate-report.md").exists())
            architecture = json.loads((output / "architecture-map.json").read_text())
            self.assertEqual(architecture["reasoning"]["mode"], "deterministic")

    def test_skips_junk_and_detects_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "node_modules").mkdir()
            (root / "node_modules" / "ignored.js").write_text("ignored")
            (root / "one.py").write_text("same")
            (root / "two.py").write_text("same")
            result = audit_estate(root)
            self.assertEqual(len(result.duplicate_groups), 1)
            self.assertTrue(any(item["path"] == "node_modules" for item in result.ignored))
            self.assertFalse(any("ignored.js" in record.path for record in result.files))

    def test_zip_is_virtual_and_rejects_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "bundle.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("project/package.json", '{"dependencies":{"next":"15"}}')
                bundle.writestr("../escape.txt", "no")

            result = audit_estate(root)
            self.assertFalse((root.parent / "escape.txt").exists())
            self.assertEqual(result.archives[0]["safe_members"], 1)
            self.assertEqual(len(result.archives[0]["unsafe_members"]), 1)
            self.assertTrue(any(record.path.startswith("bundle.zip!") for record in result.files))
            self.assertTrue(
                any("Next.js" in project.kinds for project in result.projects),
                "project types inside ZIPs should be classified",
            )

    def test_secret_redaction(self) -> None:
        value = (
            'api_key="super secret value"\n'
            '"password": "do not expose this"\n'
            "OPENAI=sk-abcdefghijklmnopqrstuvwxyz"
        )
        redacted = redact_secrets(value)
        self.assertNotIn("super secret value", redacted)
        self.assertNotIn("do not expose this", redacted)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz", redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_cli_keeps_output_outside_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "estate"
            root.mkdir()
            (root / "app.py").write_text("print('source, never executed')\n", encoding="utf-8")
            before = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }

            external_output = Path(temporary) / "report"
            with redirect_stdout(io.StringIO()):
                code = main(["audit", str(root), "--output", str(external_output)])
            after = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(code, 0)
            self.assertEqual(before, after)

            with redirect_stderr(io.StringIO()):
                rejected = main(["audit", str(root), "--output", str(root / "report")])
            self.assertEqual(rejected, 2)
            self.assertFalse((root / "report").exists())


if __name__ == "__main__":
    unittest.main()
