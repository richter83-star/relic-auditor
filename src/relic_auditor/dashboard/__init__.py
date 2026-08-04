"""Local interactive dashboard support for Relic Auditor.

The core module deliberately has no Qt import so dashboard scans and exports
remain testable when the optional GUI dependency is not installed.
"""

from .core import (
    DashboardBundle,
    DashboardOptions,
    ReportHistoryEntry,
    automatic_report_directory,
    build_cleanup_plan,
    candidate_key,
    default_reports_root,
    export_dashboard_bundle,
    list_report_history,
    run_dashboard_audit,
    summarize_dashboard_bundle,
    validate_report_output,
)

__all__ = [
    "DashboardBundle",
    "DashboardOptions",
    "ReportHistoryEntry",
    "automatic_report_directory",
    "build_cleanup_plan",
    "candidate_key",
    "default_reports_root",
    "export_dashboard_bundle",
    "list_report_history",
    "run_dashboard_audit",
    "summarize_dashboard_bundle",
    "validate_report_output",
]
