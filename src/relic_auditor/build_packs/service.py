from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from ..models import AuditResult
from ..product_discovery.compatibility import (
    CompatibleOpportunities,
    load_opportunities,
)
from ..product_discovery.entitlements import (
    Entitlement,
    FREE_ENTITLEMENT,
    ProductCapability,
)
from .canonical import canonical_bytes, digest
from .composition import compose_build_pack
from .exporter import export_build_pack, validate_export
from .providers import BuildPackProvider
from .schemas import ApprovalError, ApprovalManifest, ExportResult, PreparedBuildPack


class BuildPackService:
    def __init__(
        self,
        entitlement: Entitlement = FREE_ENTITLEMENT,
        *,
        provider: BuildPackProvider | None = None,
        allow_provider: bool = False,
    ) -> None:
        self.entitlement = entitlement
        self.provider = provider
        self.allow_provider = allow_provider

    def list_opportunities(self, source) -> CompatibleOpportunities:
        self.entitlement.require(ProductCapability.OPPORTUNITIES)
        return load_opportunities(source)

    def prepare(
        self,
        source,
        opportunity_id: str,
        *,
        audit: AuditResult | None = None,
        source_root: Path | None = None,
    ) -> PreparedBuildPack:
        self.entitlement.require(ProductCapability.BUILD_PACK_PREVIEW)
        loaded = load_opportunities(source)
        matches = [
            item
            for item in loaded.opportunities
            if item["opportunity_id"] == opportunity_id
        ]
        if len(matches) != 1:
            raise ValueError("selected Opportunity was not found or was ambiguous")
        return compose_build_pack(
            matches[0],
            audit=audit,
            source_root=source_root,
            provider=self.provider,
            allow_provider=self.allow_provider,
        )

    def approve(
        self,
        pack: PreparedBuildPack,
        selected_paths: Iterable[str],
        *,
        reviewed_paths: Iterable[str] = (),
    ) -> ApprovalManifest:
        self.entitlement.require(ProductCapability.BUILD_PACK_EXPORT)
        selected = set(map(str, selected_paths))
        reviewed = set(map(str, reviewed_paths))
        approved = []
        by_path = {asset["source_path"]: asset for asset in pack.content["assets"]}
        if selected - set(by_path):
            raise ApprovalError("approval includes an unknown asset")
        for path in sorted(selected):
            asset = by_path[path]
            if asset["classification"] == "blocked":
                raise ApprovalError("blocked assets cannot be approved")
            if asset["classification"] == "review_required" and path not in reviewed:
                raise ApprovalError(
                    "review-required assets need an explicit review acknowledgement"
                )
            approved.append(
                {
                    "source_path": path,
                    "source_sha256": asset["source_sha256"],
                    "destination_path": asset["destination_path"],
                    "classification": asset["classification"],
                    "review_acknowledged": path in reviewed,
                }
            )
        content = {
            "pack_id": pack.pack_id,
            "content_hash": pack.content_hash,
            "opportunity_id": pack.content["opportunity"]["opportunity_id"],
            "scan_fingerprint": pack.content["scan"]["fingerprint"],
            "approved_assets": approved,
        }
        return ApprovalManifest(f"approval_{digest(content)[:24]}", content)

    def export(
        self,
        pack: PreparedBuildPack,
        approval: ApprovalManifest,
        output_root: Path,
        **kwargs,
    ) -> ExportResult:
        self.entitlement.require(ProductCapability.BUILD_PACK_EXPORT)
        return export_build_pack(pack, approval, output_root, **kwargs)

    def validate(self, directory: Path) -> dict[str, object]:
        self.entitlement.require(ProductCapability.BUILD_PACK_PREVIEW)
        return validate_export(directory)


def write_prepared_pack(pack: PreparedBuildPack, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(pack.public()))
    return path


def write_approval(approval: ApprovalManifest, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(approval.public()))
    return path


def load_approval(path: Path) -> ApprovalManifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    content = {
        key: value
        for key, value in data.items()
        if key not in {"schema_version", "approval_id"}
    }
    expected = f"approval_{digest(content)[:24]}"
    if data.get("approval_id") != expected:
        raise ApprovalError("approval manifest content hash is invalid")
    return ApprovalManifest(expected, content)
