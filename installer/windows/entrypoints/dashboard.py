"""Windowed entry point for the Relic Auditor Evidence Console."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _smoke_test() -> int:
    """Create a real dashboard widget tree and exit without user interaction."""

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from relic_auditor.dashboard.qt_app import RelicWindow

    app = QApplication.instance() or QApplication(["relic-auditor-smoke-test"])
    app.setApplicationName("Relic Auditor")
    app.setOrganizationName("Dracanus AI")
    window = RelicWindow()
    if "Relic Auditor 1.0.1" not in window.windowTitle():
        return 9
    window.show()
    QTimer.singleShot(350, window.close)
    QTimer.singleShot(700, app.quit)
    return app.exec()


def main() -> int:
    if "--smoke-test" in sys.argv[1:]:
        return _smoke_test()

    from relic_auditor.dashboard.qt_app import launch_dashboard

    initial_target = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    return launch_dashboard(initial_target)


if __name__ == "__main__":
    raise SystemExit(main())
