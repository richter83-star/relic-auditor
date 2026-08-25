from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WINDOWS = ROOT / "installer" / "windows"


def test_installer_is_per_user_and_preserves_configuration() -> None:
    script = (WINDOWS / "relic-auditor.iss").read_text(encoding="utf-8")
    assert "PrivilegesRequired=lowest" in script
    assert "DefaultDirName={localappdata}\\Programs\\Relic Auditor" in script
    assert "%APPDATA%" not in script
    assert "{app}\\cli" in script
    assert "RemoveFromUserPath" in script
    assert "[InstallDelete]" in script
    assert 'Name: "{app}\\_internal"' in script
    assert 'Name: "{app}\\cli\\_internal"' in script
    assert "[UninstallDelete]" not in script


def test_application_manifest_is_non_elevated_and_dpi_aware() -> None:
    manifest = (WINDOWS / "assets" / "app.manifest").read_text(encoding="utf-8")
    assert 'assemblyIdentity version="1.0.3.0"' in manifest
    assert 'requestedExecutionLevel level="asInvoker"' in manifest
    assert "PerMonitorV2" in manifest
    assert "longPathAware" in manifest


def test_build_is_pinned_and_outputs_both_frontends() -> None:
    requirements = (WINDOWS / "requirements-build.txt").read_text(encoding="utf-8")
    spec = (WINDOWS / "relic-auditor.spec").read_text(encoding="utf-8")
    version_info = (WINDOWS / "assets" / "version_info.txt").read_text(encoding="utf-8")
    assert "PyInstaller==6.21.0" in requirements
    assert 'name="Relic Auditor"' in spec
    assert 'name="relic"' in spec
    assert 'collect_submodules("keyring.backends")' in spec
    assert "console=False" in spec
    assert "console=True" in spec
    assert "filevers=(1, 0, 3, 0)" in version_info
    assert "prodvers=(1, 0, 3, 0)" in version_info
    assert "FileVersion', '1.0.3.0'" in version_info


def test_clean_install_and_uninstall_are_release_gates() -> None:
    build = (WINDOWS / "build-installer.ps1").read_text(encoding="utf-8")
    dashboard = (WINDOWS / "entrypoints" / "dashboard.py").read_text(
        encoding="utf-8"
    )
    cli_entrypoint = (WINDOWS / "entrypoints" / "relic_cli.py").read_text(
        encoding="utf-8"
    )
    installer_readme = (WINDOWS / "INSTALLER-README.md").read_text(
        encoding="utf-8"
    )
    assert "ExpectedSourceSha256 is required" in build
    assert "ProjectVersionLines" in build
    assert "-split '\\r?\\n'" in build
    assert 'version = "1.0.3"' in build
    assert "relic-auditor-1.0.3.zip" in build
    assert "Relic Auditor 1.0.3" in dashboard
    assert "relic_auditor.entrypoint" in cli_entrypoint
    assert "Relic-Auditor-Setup-1.0.3-x64.exe" in installer_readme
    assert "0.12.0" not in installer_readme.splitlines()[0]
    assert '"resurrect", $Fixture' in build
    for required in (
        "Frozen source hash mismatch",
        "$env:TEMP = $TestTempRoot",
        "$env:TMP = $TestTempRoot",
        "bundle-smoke",
        "clean-install",
        "In-place upgrade verification failed",
        "obsolete-runtime.dll",
        "installer-preservation-",
        "uninstall_preserved_user_config",
        "Get-AuthenticodeSignature",
        "updater_requires_trusted_authenticode",
        "bundled_resurrection_smoke",
        "installed_resurrection_smoke",
        "bundled_build_pack_entitlement_gate_smoke",
        "installed_build_pack_entitlement_gate_smoke",
        "bundled_assisted_build_entitlement_gate_smoke",
        "installed_assisted_build_entitlement_gate_smoke",
        "Assert-EntitlementGate",
    ):
        assert required in build


def test_workflow_freezes_exact_commit_and_uploads_verified_artifacts() -> None:
    workflow = (ROOT / ".github" / "workflows" / "windows-installer.yml").read_text(
        encoding="utf-8"
    )
    assert "runs-on: windows-latest" in workflow
    assert "build/v1.0.3-flow-corrections" in workflow
    assert "git archive --format=zip --prefix=relic-auditor-1.0.3/" in workflow
    assert "Get-FileHash -LiteralPath $archive -Algorithm SHA256" in workflow
    assert "-ExpectedSourceSha256" in workflow
    assert "releases/relic-auditor-1.0.3.zip" in workflow
    assert "SkipSourceTests" not in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "Relic-Auditor-1.0.3-RC-Windows-x64" in workflow
    assert re.search(r"WINDOWS_SIGNING_PFX_BASE64.*secrets", workflow)
