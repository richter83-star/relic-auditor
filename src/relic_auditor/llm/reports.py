from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from ..safety import redact_secrets, redact_structure
from .schemas import LLMReasoningResult


OUTPUT_FILENAMES = {
    "markdown": "llm_reasoning_report.md",
    "json": "llm_reasoning.json",
}


def write_llm_reports(
    result: LLMReasoningResult, output: Path
) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    markdown = output / OUTPUT_FILENAMES["markdown"]
    structured = output / OUTPUT_FILENAMES["json"]
    markdown.write_text(redact_secrets(_markdown(result)), encoding="utf-8")
    structured.write_text(
        json.dumps(
            redact_structure(
                {
                    "schema_version": "1.0",
                    "advisory_only": True,
                    "credentials_included": False,
                    "provider_metadata": _provider_metadata(result),
                    **asdict(result),
                }
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return [markdown, structured]


def _provider_metadata(result: LLMReasoningResult) -> dict[str, Any]:
    """Safe run metadata. Never includes tokens, emails, organization IDs,

    raw auth output, environment-variable values, or credential paths."""

    metadata: dict[str, Any] = {
        "provider_protocol": result.protocol,
        "authentication": result.auth_mode,
        "model": result.model,
        "effort": result.effort,
        "prompt_truncated": result.prompt_truncated,
        "evidence_record_count": result.evidence_record_count,
        "provider_succeeded": result.status == "complete",
        "sanitized_error": result.error,
        "deterministic_reports_preserved": True,
    }
    return metadata


def _markdown(result: LLMReasoningResult) -> str:
    lines = [
        "# Relic Auditor LLM Reasoning Report",
        "",
        "> Optional advisory interpretation of deterministic, secret-redacted evidence. This output is not proof and cannot modify, execute, install, delete, deploy, approve, or provision anything.",
        "",
        "## Run metadata",
        "",
        f"- Status: **{_md(result.status)}**",
        f"- Profile: `{_md(result.profile)}`",
        f"- Protocol: `{_md(result.protocol)}`",
        f"- Model: `{_md(result.model)}`",
        f"- Authentication: **{_md(result.auth_mode)}**",
        f"- Evidence prompt SHA-256: `{result.prompt_sha256}`",
        f"- Evidence envelope: **{result.input_chars:,} characters**",
        f"- Evidence records: **{result.evidence_record_count}**",
        f"- Prompt truncated: **{'yes' if result.prompt_truncated else 'no'}**",
        f"- Effort: `{_md(result.effort)}`" if result.effort else "- Effort: not applicable",
        f"- Provider succeeded: **{'yes' if result.status == 'complete' else 'no'}**",
        "- Deterministic reports preserved: **yes**",
        "- Credentials included in reports: **no**",
        "",
        "## Advisory summary",
        "",
        _md(result.narrative),
        "",
    ]
    if result.error:
        lines.extend(["## Provider error", "", f"- {_md(result.error)}", ""])
    for key in (
        "candidate_assessments",
        "missing_pieces",
        "build_path",
        "risks",
        "validation_questions",
        "reusable_capabilities",
        "missing_capabilities",
        "contradictions",
        "recommended_build_path",
        "risk_notes",
        "evidence_citations",
        "confidence_notes",
    ):
        value = result.analysis.get(key)
        if not value:
            continue
        lines.extend([f"## {_title(key)}", ""])
        if isinstance(value, list):
            lines.extend(f"- {_md(_display(item))}" for item in value)
        else:
            lines.append(_md(_display(value)))
        lines.append("")
    if result.warnings:
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {_md(item)}" for item in result.warnings)
        lines.append("")
    lines.extend(
        [
            "## Trust boundary",
            "",
            "- The model received a bounded summary of redacted static evidence, not direct filesystem access.",
            "- Repository text was delimited as untrusted data and could not authorize actions.",
            "- Deterministic reports remain authoritative for observed evidence; this report is advisory.",
            "- API keys and OAuth tokens are never written to report files.",
            "",
        ]
    )
    return "\n".join(lines)


def _display(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _md(value: str) -> str:
    return redact_secrets(value).replace("|", "\\|").replace("\n", " ")


def _title(value: str) -> str:
    return value.replace("_", " ").title()
