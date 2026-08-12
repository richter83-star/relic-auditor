from __future__ import annotations

import hashlib
import re
import stat
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from ..models import AuditResult, FileRecord
from .canonical import collision_key, normalized_relative_path
from .schemas import AssetClassification, BuildPackError


_SECRET_VALUE = re.compile(
    r"(?i)(?:sk-[a-z0-9_-]{16,}|api[_-]?key\s*[:=]\s*['\"]?[a-z0-9_\-]{12,}|"
    r"authorization\s*[:=]\s*bearer\s+[a-z0-9._~+/-]{12,}|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)"
)
_SECRET_NAME = re.compile(
    r"(?i)(?:^|/)(?:\.env(?:\..*)?|id_rsa|id_ed25519|credentials\.json)$"
)
_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


def hash_file(path: Path, *, limit: int | None = None) -> str:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            if limit is not None and size > limit:
                raise BuildPackError("asset exceeds the configured byte limit")
            digest.update(chunk)
    return digest.hexdigest()


def scan_fingerprint(audit: AuditResult) -> str:
    pairs = sorted((record.path, record.sha256 or "") for record in audit.files)
    payload = "\n".join(f"{path}\0{sha}" for path, sha in pairs).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _safe_destination(source_path: str) -> str:
    path = normalized_relative_path(source_path)
    parts = []
    for part in PurePosixPath(path).parts:
        clean = unicodedata.normalize("NFC", part).rstrip(" .")
        if not clean or clean.casefold().split(".")[0] in _RESERVED:
            clean = "_" + (clean or "unnamed")
        parts.append(clean)
    output = PurePosixPath("assets", *parts).as_posix()
    if len(output) > 220:
        raise BuildPackError("asset destination exceeds the Windows-safe path budget")
    return output


def _license_status(root: Path) -> tuple[str, str | None]:
    licenses = [
        path
        for path in (root / "LICENSE", root / "LICENSE.md", root / "COPYING")
        if path.is_file()
    ]
    if not licenses:
        return "unknown", None
    texts = [
        path.read_text(encoding="utf-8", errors="replace")[:32_000].lower()
        for path in licenses
    ]
    incompatible = any(
        "gnu affero" in text or "commons clause" in text for text in texts
    )
    compatible = any(
        "mit license" in text or "apache license" in text or "bsd" in text
        for text in texts
    )
    if incompatible and compatible:
        return "conflicting", ",".join(path.name for path in licenses)
    if incompatible:
        return "incompatible", licenses[0].name
    if compatible:
        return "compatible", licenses[0].name
    return "unknown", licenses[0].name


def _record_for_path(audit: AuditResult, path: str) -> FileRecord | None:
    exact = [record for record in audit.files if record.path == path]
    if exact:
        return exact[0]
    folded = [
        record
        for record in audit.files
        if collision_key(record.path) == collision_key(path)
    ]
    return folded[0] if len(folded) == 1 else None


def classify_assets(
    audit: AuditResult,
    opportunity: Mapping[str, Any],
    source_root: Path,
    *,
    max_asset_bytes: int = 25 * 1024 * 1024,
) -> list[dict[str, Any]]:
    evidence = set(map(str, opportunity.get("evidence", [])))
    requested = opportunity.get("reusable_assets", [])
    if not isinstance(requested, list):
        raise BuildPackError("reusable assets must be a list")
    license_status, license_file = _license_status(source_root)
    by_collision: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []

    for candidate in requested:
        if not isinstance(candidate, Mapping) or not candidate.get("path"):
            continue
        raw_path = str(candidate["path"])
        reasons: list[str] = []
        secret_blocked = False
        classification = AssetClassification.ELIGIBLE
        try:
            relative = normalized_relative_path(raw_path)
            destination = _safe_destination(relative)
        except ValueError as exc:
            relative, destination = raw_path, ""
            reasons.append(str(exc))
            classification = AssetClassification.BLOCKED
        except BuildPackError as exc:
            relative, destination = raw_path, ""
            reasons.append(str(exc))
            classification = AssetClassification.BLOCKED

        record = _record_for_path(audit, raw_path)
        source_path = source_root / PurePosixPath(relative)
        refs = sorted(set(map(str, candidate.get("evidence", []))) & evidence)
        observed_hash = record.sha256 if record else None
        if record is None or not observed_hash:
            reasons.append("No hash-verified scan record resolves this asset.")
            classification = AssetClassification.BLOCKED
        elif record.source != "filesystem":
            reasons.append(
                "Virtual archive members require extraction and a rescan before reuse."
            )
            classification = AssetClassification.BLOCKED
        elif not refs:
            reasons.append("The asset is not linked to selected-Opportunity evidence.")
            classification = AssetClassification.BLOCKED
        elif not source_path.is_file() or source_path.is_symlink():
            reasons.append(
                "The source is absent, non-regular, or a symbolic link/reparse candidate."
            )
            classification = AssetClassification.BLOCKED
        else:
            stat_result = source_path.lstat()
            mode = stat_result.st_mode
            reparse = bool(
                getattr(stat_result, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
            )
            if not stat.S_ISREG(mode) or reparse:
                reasons.append("Only regular files may be reused.")
                classification = AssetClassification.BLOCKED
            elif source_path.stat().st_size > max_asset_bytes:
                reasons.append("Asset exceeds the configured byte limit.")
                classification = AssetClassification.BLOCKED
            else:
                text = (
                    record.text
                    or source_path.read_text(encoding="utf-8", errors="ignore")[
                        :256_000
                    ]
                )
                if _SECRET_NAME.search(relative) or _SECRET_VALUE.search(text):
                    reasons.append(
                        "Secret-bearing source is blocked from every Build Pack surface."
                    )
                    classification = AssetClassification.BLOCKED
                    secret_blocked = True

        if classification is not AssetClassification.BLOCKED:
            if license_status in {"incompatible", "conflicting"}:
                reasons.append("Repository license appears incompatible with reuse.")
                classification = AssetClassification.BLOCKED
            elif license_status == "unknown":
                reasons.append(
                    "License/provenance is unknown and requires explicit review."
                )
                classification = AssetClassification.REVIEW_REQUIRED

        entry: dict[str, Any] = {
            "source_path": "[secret-bearing asset withheld]"
            if secret_blocked
            else relative,
            "source_sha256": None if secret_blocked else observed_hash,
            "destination_path": "" if secret_blocked else destination,
            "classification": classification.value,
            "reasons": reasons,
            "evidence": [] if secret_blocked else refs,
            "claim": (
                "Secret-bearing asset withheld."
                if secret_blocked
                else str(candidate.get("claim") or "Observed implementation candidate.")
            ),
            "provenance": {
                "source": "scan",
                "license_status": license_status,
                "license_file": license_file,
                "ownership_proven": False,
            },
        }
        if destination:
            key = collision_key(destination)
            existing = by_collision.get(key)
            if existing:
                if existing["source_sha256"] == entry["source_sha256"]:
                    existing["evidence"] = sorted(set(existing["evidence"] + refs))
                    continue
                existing["classification"] = AssetClassification.BLOCKED.value
                existing["reasons"].append(
                    "Destination collides after case/Unicode normalization."
                )
                entry["classification"] = AssetClassification.BLOCKED.value
                entry["reasons"].append(
                    "Destination collides after case/Unicode normalization."
                )
            else:
                by_collision[key] = entry
        results.append(entry)
    return sorted(results, key=lambda item: collision_key(item["source_path"]))


def verify_source_unchanged(root: Path, assets: Iterable[Mapping[str, Any]]) -> None:
    for asset in assets:
        path = root / PurePosixPath(str(asset["source_path"]))
        if path.is_symlink() or not path.is_file():
            raise BuildPackError("approved source is no longer a regular file")
        if hash_file(path) != asset.get("source_sha256"):
            raise BuildPackError("approved source changed after approval")
