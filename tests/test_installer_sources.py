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
    assert build.startswith("#Requires -Version 7.2")
    assert "PowerShell 7.2 or later" in installer_readme
    assert 'Join-Path $OutputDirectory "checkout-tests.xml"' in build
    assert 'Join-Path $OutputDirectory "frozen-source-tests.xml"' in build
    assert "0.12.0" not in installer_readme.splitlines()[0]
    assert '"resurrect", $Fixture' in build
    for required in (
        "Frozen source hash mismatch",
        "SourceCommit is required",
        "source_commit = $SourceCommit.ToLowerInvariant()",
        "Invoke-PytestEvidence",
        "source_tests_passed",
        "source_tests_skipped",
        "$env:TEMP = $TestTempRoot",
        "$env:TMP = $TestTempRoot",
        "bundle-smoke",
        "Assert-ReadOnlyCliSequence",
        "Get-ReadOnlyTreeDigest",
        "bundled_read_only_target_digest",
        "installed_read_only_target_digest",
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
        "Relic-Auditor-Setup-1.0.1-x64.exe",
        "56c3e20c9cdcf8e2a6beae76b0e05d928e1af0002e92240c83d1ace773069d10",
        'StableVersion -ne "relic 1.0.1"',
        'UpgradedStableVersion -ne "relic 1.0.3"',
        'in_place_upgrade_smoke = "passed_same_version_reinstall"',
        'same_version_repair_smoke = "passed"',
        'stable_upgrade_from = "1.0.1"',
        'stable_upgrade_smoke = "passed"',
    ):
        assert required in build


def test_workflow_freezes_exact_commit_and_uploads_verified_artifacts() -> None:
    workflow = (ROOT / ".github" / "workflows" / "windows-installer.yml").read_text(
        encoding="utf-8"
    )
    assert "runs-on: windows-latest" in workflow
    assert "push:" not in workflow
    assert "git archive --format=zip --prefix=relic-auditor-1.0.3/" in workflow
    assert "Get-FileHash -LiteralPath $archive -Algorithm SHA256" in workflow
    assert "-ExpectedSourceSha256" in workflow
    assert '-SourceCommit "${{ github.sha }}"' in workflow
    assert "releases/relic-auditor-1.0.3.zip" in workflow
    assert "SkipSourceTests" not in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "Relic-Auditor-1.0.3-RC-Windows-x64" in workflow
    assert "persist-credentials: false" in workflow
    assert re.search(r"WINDOWS_SIGNING_PFX_BASE64.*secrets", workflow)


def test_signpath_workflow_is_manual_exact_head_and_fail_closed() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "windows-signpath-release.yml"
    ).read_text(encoding="utf-8")
    finalizer = (WINDOWS / "finalize-signed-release.ps1").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch:" in workflow
    assert "push:" not in workflow
    assert "pull_request:" not in workflow
    assert "if: github.ref == 'refs/heads/main'" in workflow
    assert 'ref: ${{ github.sha }}' in workflow
    assert 'WORKFLOW_REF -ne "refs/heads/main"' in workflow
    assert "WORKFLOW_SOURCE_COMMIT.ToLowerInvariant() -ne $Expected" in workflow
    assert 'git fetch --no-tags origin main' in workflow
    assert "exact current main commit" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "steps.upload-unsigned-installer.outputs.artifact-id" in workflow
    assert "signpath/github-action-submit-signing-request@v2" in workflow
    assert "project-slug: relic-auditor" in workflow
    assert "signing-policy-slug: release-signing" in workflow
    assert "artifact-configuration-slug: windows-installer" in workflow
    assert '-ExpectedPublisher "Dracanus AI"' in workflow
    assert "github release" not in workflow.lower()

    for required in (
        "ExpectedSourceCommit must be an exact 40-character commit SHA",
        'Manifest.authenticode_status -ne "NotSigned"',
        'Manifest.source_archive -ne "relic-auditor-1.0.3.zip"',
        "unsigned installer no longer matches its lifecycle-test manifest",
        "frozen source archive no longer matches the release manifest",
        "provider-returned installer is byte-identical",
        'Signature.Status.ToString() -ne "Valid"',
        "ActualPublisher -cne $ExpectedPublisher",
        "TimeStamperCertificate",
        "signed installer smoke install failed",
        'SignedVersion -ne "relic 1.0.3"',
        "signed installer GUI smoke test failed",
        "signed installer smoke uninstall failed",
        "unsigned_installer_sha256",
        "authenticode_thumbprint",
        "signing_provider",
        "signed_clean_install_smoke",
        "signed_cli_smoke",
        "signed_gui_smoke",
        "signed_uninstall_smoke",
    ):
        assert required in finalizer


def test_signpath_configuration_requires_trusted_build_and_review() -> None:
    policy = (
        ROOT
        / ".signpath"
        / "policies"
        / "relic-auditor"
        / "release-signing.yml"
    ).read_text(encoding="utf-8")
    artifact = (
        ROOT / ".signpath" / "artifact-configurations" / "windows-installer.xml"
    ).read_text(encoding="utf-8")
    codeowners = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")

    for required in (
        "require_github_hosted: true",
        "disallow_reruns: true",
        "restrict_deletions: true",
        "block_force_pushes: true",
        "min_required_approvals: 1",
        "dismiss_stale_reviews_on_push: true",
        "require_code_owner_review: true",
        "require_last_push_approval: true",
        "require_review_thread_resolution: true",
        "allow_bypass_actors: false",
    ):
        assert required in policy
    assert 'parameter name="version"' in artifact
    assert 'path="Relic-Auditor-Setup-${version}-x64.exe"' in artifact
    assert "<authenticode-sign />" in artifact
    assert "/.signpath/** @richter83-star" in codeowners


def test_validation_workflows_do_not_persist_checkout_credentials() -> None:
    workflows = (
        ROOT / ".github" / "workflows" / "windows-installer.yml",
        ROOT / ".github" / "workflows" / "reconcile-v1.yml",
        ROOT / ".github" / "workflows" / "windows-signpath-release.yml",
    )
    for path in workflows:
        workflow = path.read_text(encoding="utf-8")
        assert workflow.count("uses: actions/checkout@v4") == workflow.count(
            "persist-credentials: false"
        )
