from __future__ import annotations

import hashlib
import json
import errno
import os
import shutil
import stat
import uuid
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping

from .canonical import canonical_bytes, digest, normalized_relative_path
from .policy import hash_file, verify_source_unchanged
from .renderers import render_build_pack_files
from .schemas import (
    ApprovalError,
    ApprovalManifest,
    ExportResult,
    ExportValidationError,
    PreparedBuildPack,
)


def validate_approval(
    pack: PreparedBuildPack, approval: ApprovalManifest
) -> list[Mapping[str, object]]:
    expected = digest(approval.content)
    if approval.approval_id != f"approval_{expected[:24]}":
        raise ApprovalError("approval manifest content hash is invalid")
    if (
        approval.content.get("pack_id") != pack.pack_id
        or approval.content.get("content_hash") != pack.content_hash
    ):
        raise ApprovalError("approval manifest is stale for this Build Pack")
    if approval.content.get("scan_fingerprint") != pack.content["scan"]["fingerprint"]:
        raise ApprovalError("approval manifest scan fingerprint is stale")
    assets = approval.content.get("approved_assets", [])
    if not isinstance(assets, list):
        raise ApprovalError("approved assets must be a list")
    available = {asset["source_path"]: asset for asset in pack.content["assets"]}
    for approved in assets:
        source = str(approved.get("source_path", ""))
        candidate = available.get(source)
        if candidate is None or candidate["classification"] == "blocked":
            raise ApprovalError("approval references an unavailable or blocked asset")
        if approved.get("source_sha256") != candidate.get("source_sha256"):
            raise ApprovalError("approval asset hash is stale")
        if approved.get("destination_path") != candidate.get("destination_path"):
            raise ApprovalError("approval asset destination is stale")
    return assets


def _copy_verified(source: Path, destination: Path, expected_hash: str) -> None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(source, flags)
    digestor = hashlib.sha256()
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ExportValidationError("approved source is not a regular file")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with (
            os.fdopen(descriptor, "rb", closefd=False) as incoming,
            destination.open("xb") as outgoing,
        ):
            for chunk in iter(lambda: incoming.read(1024 * 1024), b""):
                digestor.update(chunk)
                outgoing.write(chunk)
    finally:
        os.close(descriptor)
    if digestor.hexdigest() != expected_hash:
        destination.unlink(missing_ok=True)
        raise ExportValidationError("approved source changed during export")


def _final_directory(staging: Path, output_root: Path, pack_id: str) -> Path:
    suffix = 1
    while True:
        candidate = output_root / (pack_id if suffix == 1 else f"{pack_id}-{suffix}")
        try:
            staging.rename(candidate)
            return candidate
        except OSError as exc:
            if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                raise
            suffix += 1


def export_build_pack(
    pack: PreparedBuildPack,
    approval: ApprovalManifest,
    output_root: Path,
    *,
    cancelled: Callable[[], bool] | None = None,
    max_files: int = 1_000,
    max_bytes: int = 100 * 1024 * 1024,
) -> ExportResult:
    approved = validate_approval(pack, approval)
    if pack.source_root is None:
        raise ApprovalError("a current rescan is required before asset export")
    root = pack.source_root.resolve()
    destination_root = output_root.expanduser().resolve()
    if destination_root == root or destination_root.is_relative_to(root):
        raise ExportValidationError(
            "Build Packs must be exported outside the scanned target"
        )
    destination_root.mkdir(parents=True, exist_ok=True)
    verify_source_unchanged(root, approved)
    staging = destination_root / f".{pack.pack_id}.{uuid.uuid4().hex}.staging"
    staging.mkdir()
    try:
        for asset in approved:
            if cancelled and cancelled():
                raise ExportValidationError("export cancelled")
            relative = normalized_relative_path(str(asset["source_path"]))
            output = normalized_relative_path(str(asset["destination_path"]))
            _copy_verified(
                root / PurePosixPath(relative),
                staging / PurePosixPath(output),
                str(asset["source_sha256"]),
            )

        generated = render_build_pack_files(pack, approval)
        manifest = {
            "schema_version": "1.0",
            "pack_id": pack.pack_id,
            "content_hash": pack.content_hash,
            "approval_id": approval.approval_id,
            "approved_assets": approved,
            "complete": True,
        }
        generated["build-pack-manifest.json"] = canonical_bytes(manifest)
        for relative, data in sorted(generated.items()):
            if cancelled and cancelled():
                raise ExportValidationError("export cancelled")
            path = staging / PurePosixPath(normalized_relative_path(relative))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        files = sorted(path for path in staging.rglob("*") if path.is_file())
        if (
            len(files) + 1 > max_files
            or sum(path.stat().st_size for path in files) > max_bytes
        ):
            raise ExportValidationError(
                "export exceeds configured total resource limits"
            )
        checksums = []
        for path in files:
            relative = path.relative_to(staging).as_posix()
            checksums.append(f"{hash_file(path)}  {relative}")
        (staging / "SHA256SUMS.txt").write_text(
            "\n".join(checksums) + "\n", encoding="utf-8"
        )
        verify_source_unchanged(root, approved)
        validate_export(staging)
        final = _final_directory(staging, destination_root, pack.pack_id)
        all_files = tuple(sorted(path for path in final.rglob("*") if path.is_file()))
        return ExportResult(
            final, pack.pack_id, all_files, hash_file(final / "SHA256SUMS.txt")
        )
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def validate_export(directory: Path) -> dict[str, object]:
    root = directory.expanduser().resolve()
    if not root.is_dir():
        raise ExportValidationError("Build Pack directory is missing")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ExportValidationError(
                "Build Pack contains a symbolic-link/reparse tamper"
            )
    pack_path = root / "build-pack.json"
    sums_path = root / "SHA256SUMS.txt"
    manifest_path = root / "build-pack-manifest.json"
    if not all(path.is_file() for path in (pack_path, sums_path, manifest_path)):
        raise ExportValidationError("Build Pack is incomplete")
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    content = {
        key: value
        for key, value in pack.items()
        if key not in {"schema_version", "pack_id", "content_hash"}
    }
    if (
        digest(content) != pack.get("content_hash")
        or pack.get("pack_id") != f"bp_{pack.get('content_hash', '')[:24]}"
    ):
        raise ExportValidationError("canonical Build Pack content was tampered with")
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        expected, separator, raw = line.partition("  ")
        if not separator:
            raise ExportValidationError("checksum manifest is malformed")
        relative = normalized_relative_path(raw)
        path = root / PurePosixPath(relative)
        if path.is_symlink() or not path.is_file() or hash_file(path) != expected:
            raise ExportValidationError("checksum verification detected tampering")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("complete") or manifest.get("pack_id") != pack.get("pack_id"):
        raise ExportValidationError("Build Pack manifest is inconsistent")
    return {
        "valid": True,
        "pack_id": pack["pack_id"],
        "content_hash": pack["content_hash"],
    }
