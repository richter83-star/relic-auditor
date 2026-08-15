from __future__ import annotations

import hashlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WINDOWS = ROOT / "installer" / "windows"
SOURCE = ROOT / "releases" / "relic-auditor-0.10.1.zip"
EXPECTED_SOURCE_SHA256 = "d0e67e54a7315d5c2dd89746353868d5da10f37275a7f8e109554d99abca34e0"


def test_frozen_source_is_exact_release() -> None:
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == EXPECTED_SOURCE_SHA256


def test_installer_is_per_user_and_preserves_configuration() -> None:
    script = (WINDOWS / "relic-auditor.iss").read_text(encoding="utf-8")
    assert "PrivilegesRequired=lowest" in script
    assert "DefaultDirName={localappdata}\\Programs\\Relic Auditor" in script
    assert "%APPDATA%" not in script
    assert "{app}\\cli" in script
    assert "RemoveFromUserPath" in script
    assert "[UninstallDelete]" not in script


def test_application_manifest_is_non_elevated_and_dpi_aware() -> None:
    manifest = (WINDOWS / "assets" / "app.manifest").read_text(encoding="utf-8")
    assert 'requestedExecutionLevel level="asInvoker"' in manifest
    assert "PerMonitorV2" in manifest
    assert "longPathAware" in manifest


def test_build_is_pinned_and_outputs_both_frontends() -> None:
    requirements = (WINDOWS / "requirements-build.txt").read_text(encoding="utf-8")
    spec = (WINDOWS / "relic-auditor.spec").read_text(encoding="utf-8")
    assert "PyInstaller==6.21.0" in requirements
    assert 'name="Relic Auditor"' in spec
    assert 'name="relic"' in spec
    assert 'collect_submodules("keyring.backends")' in spec
    assert "console=False" in spec
    assert "console=True" in spec


def test_clean_install_and_uninstall_are_release_gates() -> None:
    build = (WINDOWS / "build-installer.ps1").read_text(encoding="utf-8")
    dashboard = (WINDOWS / "entrypoints" / "dashboard.py").read_text(
        encoding="utf-8"
    )
    installer_readme = (WINDOWS / "INSTALLER-README.md").read_text(
        encoding="utf-8"
    )
    assert EXPECTED_SOURCE_SHA256 in build
    assert "version = \"0\\.10\\.1\"" in build
    assert "version = \"0\\.10\\.0\"" not in build
    assert "Relic Auditor 0.10.1" in dashboard
    assert "Relic Auditor 0.10.0" not in dashboard
    assert "Relic-Auditor-Setup-0.10.1-x64.exe" in installer_readme
    assert "Relic-Auditor-Setup-0.10.0-x64.exe" not in installer_readme
    for required in (
        "Frozen source hash mismatch",
        "$env:TEMP = $TestTempRoot",
        "$env:TMP = $TestTempRoot",
        "bundle-smoke",
        "clean-install",
        "installer-preservation-",
        "uninstall_preserved_user_config",
        "Get-AuthenticodeSignature",
    ):
        assert required in build


def test_workflow_uses_windows_and_only_frozen_source() -> None:
    workflow = (ROOT / ".github" / "workflows" / "windows-installer.yml").read_text(
        encoding="utf-8"
    )
    assert "runs-on: windows-latest" in workflow
    assert "releases/relic-auditor-0.10.1.zip" in workflow
    assert "SkipSourceTests" not in workflow
    assert EXPECTED_SOURCE_SHA256 in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert re.search(r"WINDOWS_SIGNING_PFX_BASE64.*secrets", workflow)
