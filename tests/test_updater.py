from __future__ import annotations

import hashlib
import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from relic_auditor.updater import (
    AuthenticodeResult,
    PreparedUpdate,
    ReleaseVersion,
    UpdateDownloadError,
    UpdateManifestError,
    UpdateVerificationError,
    download_installer,
    fetch_update_manifest,
    launch_prepared_update,
    load_update_check_state,
    parse_update_manifest,
    prepare_update,
    save_update_check_state,
    should_check_automatically,
    verify_authenticode,
)


class FakeResponse(io.BytesIO):
    def __init__(
        self,
        payload: bytes,
        *,
        url: str = "https://downloads.example.test/file",
        status: int = 200,
        content_length: int | None = None,
    ) -> None:
        super().__init__(payload)
        self.status = status
        self._url = url
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def manifest_payload(installer: bytes = b"verified installer") -> dict:
    return {
        "schema_version": 1,
        "channel": "stable",
        "version": "0.10.2",
        "published_at": "2026-08-15T02:00:00Z",
        "release_notes": [
            "Checks the stable channel automatically.",
            "Verifies every installer before it can run.",
        ],
        "release_notes_url": "https://example.test/releases/0.10.2",
        "installer": {
            "filename": "Relic-Auditor-Setup-0.10.2-x64.exe",
            "url": "https://downloads.example.test/Relic-Auditor-Setup-0.10.2-x64.exe",
            "sha256": hashlib.sha256(installer).hexdigest(),
            "size": len(installer),
        },
    }


def test_release_version_orders_stable_and_prerelease() -> None:
    assert ReleaseVersion.parse("0.10.2") > ReleaseVersion.parse("0.10.1")
    assert ReleaseVersion.parse("0.10.2") > ReleaseVersion.parse("0.10.2-rc.1")
    assert ReleaseVersion.parse("0.10.2-rc.2") > ReleaseVersion.parse("0.10.2-rc.1")
    assert str(ReleaseVersion.parse("v1.2.3-rc.1")) == "1.2.3-rc.1"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("channel", "beta"),
        ("version", "0.10"),
        ("published_at", "yesterday"),
        ("release_notes_url", "http://example.test/notes"),
    ],
)
def test_manifest_rejects_invalid_top_level_values(field: str, value: object) -> None:
    payload = manifest_payload()
    payload[field] = value
    with pytest.raises(UpdateManifestError):
        parse_update_manifest(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("filename", "../setup.exe"),
        ("filename", "setup.msi"),
        ("url", "http://downloads.example.test/setup.exe"),
        ("sha256", "not-a-digest"),
        ("size", 0),
    ],
)
def test_manifest_rejects_unsafe_installer_values(field: str, value: object) -> None:
    payload = manifest_payload()
    payload["installer"][field] = value
    with pytest.raises(UpdateManifestError):
        parse_update_manifest(payload)


def test_fetch_manifest_is_bounded_and_validates_redirect() -> None:
    encoded = json.dumps(manifest_payload()).encode()
    manifest = fetch_update_manifest(
        "https://example.test/stable.json",
        opener=lambda *_args, **_kwargs: FakeResponse(
            encoded,
            url="https://cdn.example.test/stable.json",
            content_length=len(encoded),
        ),
    )
    assert str(manifest.version) == "0.10.2"
    assert manifest.is_newer_than("0.10.1")
    assert not manifest.is_newer_than("0.10.2")

    with pytest.raises(UpdateManifestError, match="HTTPS"):
        fetch_update_manifest(
            "https://example.test/stable.json",
            opener=lambda *_args, **_kwargs: FakeResponse(
                encoded, url="http://redirect.example.test/stable.json"
            ),
        )


def test_download_is_atomic_and_hash_verified(tmp_path: Path) -> None:
    installer = b"verified installer"
    manifest = parse_update_manifest(manifest_payload(installer))
    observed: list[tuple[int, int]] = []
    result = download_installer(
        manifest,
        tmp_path,
        opener=lambda *_args, **_kwargs: FakeResponse(
            installer,
            url=manifest.installer.url,
            content_length=len(installer),
        ),
        progress=lambda received, total: observed.append((received, total)),
    )
    assert result.read_bytes() == installer
    assert observed[-1] == (len(installer), len(installer))
    assert not result.with_suffix(f"{result.suffix}.part").exists()


def test_download_removes_only_superseded_relic_installers(tmp_path: Path) -> None:
    installer = b"verified installer"
    manifest = parse_update_manifest(manifest_payload(installer))
    old_installer = tmp_path / "Relic-Auditor-Setup-0.10.1-x64.exe"
    old_partial = tmp_path / "Relic-Auditor-Setup-0.10.1-x64.exe.part"
    unrelated = tmp_path / "another-product.exe"
    old_installer.write_bytes(b"old")
    old_partial.write_bytes(b"partial")
    unrelated.write_bytes(b"keep")

    download_installer(
        manifest,
        tmp_path,
        opener=lambda *_args, **_kwargs: FakeResponse(
            installer,
            url=manifest.installer.url,
            content_length=len(installer),
        ),
    )

    assert not old_installer.exists()
    assert not old_partial.exists()
    assert unrelated.read_bytes() == b"keep"


def test_download_removes_partial_file_when_digest_is_wrong(tmp_path: Path) -> None:
    installer = b"tampered installer"
    payload = manifest_payload(installer)
    payload["installer"]["sha256"] = "0" * 64
    manifest = parse_update_manifest(payload)
    with pytest.raises(UpdateDownloadError, match="SHA-256"):
        download_installer(
            manifest,
            tmp_path,
            opener=lambda *_args, **_kwargs: FakeResponse(
                installer,
                url=manifest.installer.url,
                content_length=len(installer),
            ),
        )
    assert list(tmp_path.iterdir()) == []


def test_prepare_update_deletes_untrusted_installer(tmp_path: Path) -> None:
    installer = b"verified installer"
    manifest = parse_update_manifest(manifest_payload(installer))
    with pytest.raises(UpdateVerificationError, match="trusted Dracanus AI"):
        prepare_update(
            manifest,
            tmp_path,
            opener=lambda *_args, **_kwargs: FakeResponse(
                installer,
                url=manifest.installer.url,
                content_length=len(installer),
            ),
            signature_verifier=lambda _path: AuthenticodeResult(
                "Valid", "CN=Someone Else", False
            ),
        )
    assert list(tmp_path.iterdir()) == []


def test_authenticode_pins_dracanus_publisher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer = tmp_path / "setup.exe"
    installer.write_bytes(b"installer")
    powershell = (
        tmp_path
        / "Windows"
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    )
    powershell.parent.mkdir(parents=True)
    powershell.write_bytes(b"")
    monkeypatch.setenv("SystemRoot", str(tmp_path / "Windows"))

    class Completed:
        returncode = 0
        stdout = json.dumps({"status": "Valid", "subject": "Dracanus AI"})
        stderr = ""

    def runner(args, **kwargs):
        assert args[0] == str(powershell)
        assert kwargs["env"]["RELIC_UPDATE_INSTALLER_PATH"] == str(installer.resolve())
        return Completed()

    result = verify_authenticode(installer, runner=runner, platform="win32")
    assert result.trusted is True

    Completed.stdout = json.dumps(
        {"status": "Valid", "subject": "Not Dracanus AI Software"}
    )
    spoofed = verify_authenticode(installer, runner=runner, platform="win32")
    assert spoofed.trusted is False


def test_launch_rechecks_hash_and_signature(tmp_path: Path) -> None:
    installer = b"verified installer"
    manifest = parse_update_manifest(manifest_payload(installer))
    path = tmp_path / manifest.installer.filename
    path.write_bytes(installer)
    signature = AuthenticodeResult("Valid", "CN=Dracanus AI", True)
    prepared = PreparedUpdate(manifest, path, signature)
    launched: list[tuple[list[str], dict]] = []
    launch_prepared_update(
        prepared,
        platform="win32",
        signature_verifier=lambda _path: signature,
        launcher=lambda args, **kwargs: launched.append((args, kwargs)),
    )
    assert launched[0][0] == [
        str(path.resolve()),
        "/SP-",
        "/CLOSEAPPLICATIONS",
        "/NORESTART",
    ]
    assert launched[0][1]["shell"] is False

    path.write_bytes(b"changed")
    with pytest.raises(UpdateVerificationError, match="changed"):
        launch_prepared_update(
            prepared,
            platform="win32",
            signature_verifier=lambda _path: signature,
            launcher=lambda *_args, **_kwargs: None,
        )


def test_automatic_check_state_uses_success_and_failure_intervals(tmp_path: Path) -> None:
    state_path = tmp_path / "update-state.json"
    start = datetime(2026, 8, 15, 2, tzinfo=UTC)
    assert should_check_automatically(state_path, now=start)

    save_update_check_state(success=True, path=state_path, now=start)
    state = load_update_check_state(state_path)
    assert state.last_success_at == start
    assert not should_check_automatically(state_path, now=start + timedelta(hours=23))
    assert should_check_automatically(state_path, now=start + timedelta(hours=24))

    failed = start + timedelta(days=1)
    save_update_check_state(success=False, path=state_path, now=failed)
    assert not should_check_automatically(state_path, now=failed + timedelta(hours=5))
    assert should_check_automatically(state_path, now=failed + timedelta(hours=6))
