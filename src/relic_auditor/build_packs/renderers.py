from __future__ import annotations

from typing import Any, Mapping

from .canonical import canonical_bytes
from .handoffs import RENDERERS
from .schemas import ApprovalManifest, PreparedBuildPack


def _section(title: str, value: Any) -> bytes:
    if isinstance(value, Mapping):
        body = "\n".join(
            f"- **{key.replace('_', ' ').title()}:** {item}"
            for key, item in value.items()
        )
    elif isinstance(value, list):
        body = "\n".join(f"- {item}" for item in value)
    else:
        body = str(value)
    return f"# {title}\n\n{body}\n".encode("utf-8")


def render_build_pack_files(
    pack: PreparedBuildPack, approval: ApprovalManifest
) -> dict[str, bytes]:
    content = pack.content
    files = {
        "build-pack.json": canonical_bytes(pack.public()),
        "approval-manifest.json": canonical_bytes(approval.public()),
        "BRIEF.md": _section("Product brief", content["brief"]),
        "SCOPE.md": _section("MVP scope", content["scope"]),
        "ARCHITECTURE.md": _section("Proposed architecture", content["architecture"]),
        "PLAN.md": _section("Ordered implementation plan", content["tasks"]),
        "ACCEPTANCE-CRITERIA.md": _section(
            "Acceptance criteria", content["acceptance_criteria"]
        ),
        "ASSET-MANIFEST.json": canonical_bytes(content["assets"]),
        "PROVENANCE.json": canonical_bytes(content["provenance"]),
        "RISKS.md": _section("Risks", content["risks"]),
        "RELIC-CONTEXT.json": canonical_bytes(
            {
                "pack_id": pack.pack_id,
                "content_hash": pack.content_hash,
                "opportunity": content["opportunity"],
                "scan": content["scan"],
                "safety": content["safety"],
            }
        ),
    }
    for name, renderer in RENDERERS.items():
        files[f"HANDOFF-{name.upper().replace('-', '_')}.md"] = renderer.render(
            pack
        ).encode("utf-8")
    return files
