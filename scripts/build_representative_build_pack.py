from __future__ import annotations

import argparse
import hashlib
import json
import stat
import tempfile
import zipfile
from pathlib import Path

from relic_auditor.audit import audit_estate
from relic_auditor.build_packs import BuildPackService
from relic_auditor.product_discovery.entitlements import entitlement_for_testing


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def deterministic_zip(source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            relative = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(relative, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(
                info,
                path.read_bytes(),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        target = base / "fixture"
        (target / "src").mkdir(parents=True)
        (target / "LICENSE").write_text("MIT License\n", encoding="utf-8")
        (target / "src" / "evaluate.py").write_text(
            "def evaluate(value):\n    return {'score': bool(value)}\n",
            encoding="utf-8",
        )
        (target / "src" / "report.py").write_text(
            "def report(result):\n    return {'result': result}\n", encoding="utf-8"
        )
        audit = audit_estate(target)
        hashes = {record.path: record.sha256 for record in audit.files}
        opportunity = {
            "opportunity_id": "opp_representative",
            "title": "Evidence-linked evaluation report",
            "summary": "A bounded evaluation workflow with a traceable result.",
            "target_user": "Operations teams",
            "job_to_be_done": "Evaluate supplied records and return a reviewable report.",
            "evidence": ["ev_evaluate", "ev_report"],
            "evidence_score": 82,
            "technical_verification_status": "moderate",
            "supporting_capability_ids": ["cap_evaluate", "cap_report"],
            "reusable_assets": [
                {
                    "path": "src/evaluate.py",
                    "sha256": hashes["src/evaluate.py"],
                    "evidence": ["ev_evaluate"],
                },
                {
                    "path": "src/report.py",
                    "sha256": hashes["src/report.py"],
                    "evidence": ["ev_report"],
                },
            ],
            "missing_components": [
                "Bounded input validation",
                "End-to-end verification",
            ],
            "risks": ["Demand remains unvalidated"],
        }
        service = BuildPackService(entitlement_for_testing("premium"))
        pack = service.prepare(
            {"schema_version": "0.9", "opportunities": [opportunity]},
            "opp_representative",
            audit=audit,
            source_root=target,
        )
        selected = [
            asset["source_path"]
            for asset in pack.content["assets"]
            if asset["classification"] == "eligible"
        ]
        approval = service.approve(pack, selected)
        before = tree_hash(target)
        exported = service.export(pack, approval, base / "exports")
        after = tree_hash(target)
        if before != after:
            raise RuntimeError("representative target changed")
        service.validate(exported.directory)
        deterministic_zip(exported.directory, args.output.resolve())
        print(
            json.dumps(
                {
                    "pack_id": pack.pack_id,
                    "content_hash": pack.content_hash,
                    "target_before": before,
                    "target_after": after,
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
