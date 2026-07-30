"""PyInstaller specification for the GUI and console distributions."""

from __future__ import annotations

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


installer_root = Path(os.environ["RELIC_INSTALLER_ROOT"]).resolve()
assets = installer_root / "assets"
entrypoints = installer_root / "entrypoints"

keyring_hidden = collect_submodules("keyring.backends")
keyring_data = collect_data_files("keyring") + copy_metadata("keyring", recursive=True)
common_hidden = sorted(set(keyring_hidden + [
    "keyring.backends.Windows",
    "keyring.backends.fail",
    "keyring.backends.null",
]))


def analysis(script: str) -> Analysis:
    return Analysis(
        [str(entrypoints / script)],
        pathex=[],
        binaries=[],
        datas=keyring_data,
        hiddenimports=common_hidden,
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        excludes=["tkinter", "unittest", "pydoc", "doctest"],
        noarchive=False,
        optimize=1,
    )


gui_analysis = analysis("dashboard.py")
gui_pyz = PYZ(gui_analysis.pure)
gui_exe = EXE(
    gui_pyz,
    gui_analysis.scripts,
    [],
    exclude_binaries=True,
    name="Relic Auditor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(assets / "relic-auditor.ico"),
    version=str(assets / "version_info.txt"),
    manifest=str(assets / "app.manifest"),
    uac_admin=False,
    uac_uiaccess=False,
)
gui_distribution = COLLECT(
    gui_exe,
    gui_analysis.binaries,
    gui_analysis.datas,
    strip=False,
    upx=False,
    name="Relic Auditor",
)

cli_analysis = analysis("relic_cli.py")
cli_pyz = PYZ(cli_analysis.pure)
cli_exe = EXE(
    cli_pyz,
    cli_analysis.scripts,
    [],
    exclude_binaries=True,
    name="relic",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=str(assets / "relic-auditor.ico"),
    version=str(assets / "version_info.txt"),
    manifest=str(assets / "app.manifest"),
    uac_admin=False,
    uac_uiaccess=False,
)
cli_distribution = COLLECT(
    cli_exe,
    cli_analysis.binaries,
    cli_analysis.datas,
    strip=False,
    upx=False,
    name="relic-cli",
)
