from __future__ import annotations

import os
from pathlib import Path

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtWidgets import QApplication  # noqa: E402

from relic_auditor.dashboard.update_dialog import UpdateDialog  # noqa: E402
from relic_auditor.updater import parse_update_manifest  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_update_dialog_exposes_three_truthful_steps(app) -> None:
    manifest = parse_update_manifest(
        {
            "schema_version": 1,
            "channel": "stable",
            "version": "0.10.2",
            "published_at": "2026-08-15T03:00:00Z",
            "release_notes": ["Verified updates."],
            "installer": {
                "filename": "Relic-Auditor-Setup-0.10.2-x64.exe",
                "url": "https://example.test/Relic-Auditor-Setup-0.10.2-x64.exe",
                "sha256": "0" * 64,
                "size": 100,
            },
        }
    )
    dialog = UpdateDialog("0.10.1", manifest)
    assert dialog.step_badge.text() == "STEP 1 OF 3"
    assert dialog.action_button.text() == "Download and verify"

    dialog.set_downloading()
    assert dialog.step_badge.text() == "STEP 2 OF 3"
    assert not dialog.action_button.isEnabled()
    dialog.set_download_progress(50, 100)
    assert dialog.progress.value() == 50

    dialog.set_ready(Path(manifest.installer.filename))
    assert dialog.step_badge.text() == "STEP 3 OF 3"
    assert dialog.action_button.text() == "Install update"
    assert dialog.action_button.isEnabled()
