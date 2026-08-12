from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .audit import audit_estate
from .capability_acquisition import (
    AcquisitionConfig,
    analyze_capability_acquisition,
    run_monitor,
    write_acquisition_reports,
)
from .models import ScanLimits
from .llm import (
    LLMProfile,
    LLMReasoningConfig,
    ProfileStore,
    claude_code,
    oauth_login,
    oauth_logout,
    oauth_status,
    reason_about_acquisition,
    write_llm_reports,
)
from .reports import write_reports
from .product_discovery import DiscoveryConfig, discover_products
from .product_discovery.reports import write_product_reports
from .technical_truth import TechnicalTruthConfig, analyze_technical_truth
from .technical_truth.reports import write_technical_truth_reports


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="relic",
        description="Deterministically appraise a messy software estate without executing or modifying it.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    audit = commands.add_parser("audit", help="scan a file or folder and write appraisal reports")
    audit.add_argument("target", type=Path, help="file, folder, or ZIP archive to inspect")
    audit.add_argument(
        "-o",
        "--output",
        type=Path,
        help="report directory (default: ./relic-report)",
    )
    audit.add_argument("--product-discovery", action="store_true", help="generate offline evidence-backed product and GTM proposals")
    audit.add_argument(
        "--capability-acquisition",
        action="store_true",
        help="detect reusable bounded-autonomy building blocks and write acquisition inventories",
    )
    audit.add_argument("--offline", action="store_true", help="explicitly require no external calls (already the default)")
    audit.add_argument("--market-validation", action="store_true", help="request configured external validation; never sends source by default")
    audit.add_argument("--reasoning-provider", choices=["none", "local", "configured_external"], default="none")
    _add_llm_reasoning_args(audit)
    audit.add_argument("--max-opportunities", type=int, default=6)
    audit.add_argument("--technical-truth", action="store_true", help="run deterministic static technical verification")
    audit.add_argument("--no-technical-truth", action="store_true", help="disable automatic technical verification for product discovery")
    audit.add_argument("--technical-max-file-mb", type=int, default=2)
    audit.add_argument("--max-graph-nodes", type=int, default=100_000)
    audit.add_argument("--workflow-depth", type=int, default=12)
    audit.add_argument("--no-technical-cache", action="store_true", help="disable persistent parse-result caching")
    audit.add_argument("--technical-cache", type=Path, help="cache file path (default: report directory/.relic-cache/technical-truth.json)")
    audit.add_argument("--max-data-flow-edges", type=int, default=50_000)
    audit.add_argument(
        "--include-hidden",
        action="store_true",
        help="inspect hidden files except ignored VCS/cache/dependency directories",
    )
    audit.add_argument(
        "--max-file-mb",
        type=int,
        default=10,
        metavar="MB",
        help="maximum individual file/member size to inspect (default: 10)",
    )
    audit.add_argument(
        "--max-zip-members",
        type=int,
        default=20_000,
        metavar="N",
        help="reject ZIPs with more members (default: 20000)",
    )
    acquire = commands.add_parser(
        "acquire",
        help="run deterministic Capability Acquisition Mode on a file, folder, or ZIP",
    )
    acquire.add_argument("target", type=Path, help="file, folder, or ZIP archive to inspect")
    acquire.add_argument("-o", "--output", type=Path, help="report directory")
    acquire.add_argument("--include-hidden", action="store_true")
    acquire.add_argument("--max-file-mb", type=int, default=10, metavar="MB")
    acquire.add_argument("--max-zip-members", type=int, default=20_000, metavar="N")
    acquire.add_argument("--max-candidates", type=int, default=40, metavar="N")
    _add_llm_reasoning_args(acquire)
    monitor = commands.add_parser(
        "monitor",
        help="watch an inbox and automatically run Capability Acquisition Mode on stable drops",
    )
    monitor.add_argument("inbox", type=Path, help="inbox folder to watch")
    monitor.add_argument("-o", "--output", type=Path, help="external report root")
    monitor.add_argument("--debounce-seconds", type=float, default=2.0)
    monitor.add_argument("--poll-seconds", type=float, default=1.0)
    monitor.add_argument(
        "--once",
        action="store_true",
        help="process current stable drops once, then exit",
    )
    _add_llm_reasoning_args(monitor)
    dashboard = commands.add_parser(
        "dashboard",
        help="launch the optional local interactive dashboard",
    )
    dashboard.add_argument(
        "target",
        type=Path,
        nargs="?",
        help="folder to inspect (optional; the dashboard also has a folder picker)",
    )
    llm = commands.add_parser(
        "llm",
        help="manage optional API-key, OAuth, and Claude Code subscription reasoning profiles",
    )
    llm_actions = llm.add_subparsers(dest="llm_action", required=True)
    llm_actions.add_parser("list", help="list non-secret LLM profile metadata")
    add = llm_actions.add_parser("add", help="add or replace an LLM profile")
    add.add_argument("name")
    add.add_argument(
        "--protocol",
        required=True,
        choices=[
            "openai-responses",
            "openai-chat",
            "anthropic-messages",
            "claude-code",
        ],
    )
    add.add_argument("--model", required=True)
    add.add_argument(
        "--base-url",
        help="API base URL (defaults to the official endpoint for known protocols; unused for claude-code)",
    )
    add.add_argument(
        "--auth",
        required=True,
        choices=["api-key", "oauth", "claude-subscription"],
    )
    add.add_argument(
        "--effort",
        choices=sorted(claude_code.SUPPORTED_EFFORTS),
        help="reasoning effort for claude-code profiles (default: medium)",
    )
    add.add_argument("--api-key-env")
    add.add_argument("--authorization-url")
    add.add_argument("--token-url")
    add.add_argument("--client-id")
    add.add_argument("--scope", action="append", default=[])
    add.add_argument("--audience")
    remove = llm_actions.add_parser("remove", help="remove profile metadata")
    remove.add_argument("name")
    login = llm_actions.add_parser("login", help="authenticate an OAuth profile")
    login.add_argument("name")
    login.add_argument("--timeout-seconds", type=float, default=180.0)
    logout = llm_actions.add_parser("logout", help="delete stored OAuth tokens")
    logout.add_argument("name")
    status = llm_actions.add_parser("status", help="show credential readiness")
    status.add_argument("name")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "llm":
        return _handle_llm_command(args)
    if getattr(args, "llm_required", False) and not getattr(args, "llm_profile", None):
        parser.error("--llm-required requires --llm-profile")
    if args.command == "dashboard":
        try:
            from .dashboard.qt_app import launch_dashboard
        except ModuleNotFoundError as exc:
            if exc.name and exc.name.startswith("PySide6"):
                print(
                    'error: the dashboard requires the GUI extra; install it with '
                    'python -m pip install -e ".[gui]"',
                    file=sys.stderr,
                )
                return 2
            raise
        except ImportError as exc:
            message = str(exc)
            if "libEGL" in message or "DLL load failed" in message:
                print(
                    f"error: the Qt GUI runtime could not start on this system: {message}",
                    file=sys.stderr,
                )
                return 2
            raise
        return launch_dashboard(args.target)

    if args.command == "monitor":
        if args.debounce_seconds < 0 or args.poll_seconds <= 0:
            parser.error("monitor timing values must be non-negative and poll time must be positive")
        inbox = args.inbox.expanduser().resolve()
        output = (
            args.output or inbox.parent / f"{inbox.name}-relic-monitor"
        ).expanduser().resolve()
        try:
            print(f"Relic Monitor watching: {inbox}")
            print(f"Capability reports: {output}")
            run_monitor(
                inbox,
                output,
                debounce_seconds=args.debounce_seconds,
                poll_seconds=args.poll_seconds,
                once=args.once,
                llm_config=_llm_config(args),
                llm_required=args.llm_required,
                on_report=lambda drop, written: print(
                    f"Acquisition complete: {drop} ({len(written)} reports)"
                ),
            )
        except KeyboardInterrupt:
            print("Relic Monitor stopped.")
            return 130
        except (
            FileNotFoundError,
            NotADirectoryError,
            PermissionError,
            KeyError,
            RuntimeError,
            ValueError,
            OSError,
        ) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return 0

    if args.command == "acquire":
        if args.max_file_mb <= 0 or args.max_zip_members <= 0 or args.max_candidates <= 0:
            parser.error("scan limits must be positive")
        target = args.target.expanduser().resolve()
        output = (
            args.output or target.parent / f"{target.name}-relic-acquisition"
        ).expanduser().resolve()
        try:
            if target == output or (target.is_dir() and output.is_relative_to(target)):
                raise ValueError(
                    "output must be outside the target so the scanned estate remains read-only"
                )
            audit_result = audit_estate(
                target,
                limits=ScanLimits(
                    max_file_bytes=args.max_file_mb * 1024 * 1024,
                    max_zip_members=args.max_zip_members,
                ),
                include_hidden=args.include_hidden,
            )
            acquisition = analyze_capability_acquisition(
                audit_result,
                AcquisitionConfig(max_candidates=args.max_candidates),
            )
            written = write_acquisition_reports(acquisition, output)
            llm_result = None
            if args.llm_profile:
                llm_result = reason_about_acquisition(
                    acquisition,
                    _llm_config(args),
                )
                written.extend(write_llm_reports(llm_result, output))
        except (
            FileNotFoundError,
            NotADirectoryError,
            PermissionError,
            KeyError,
            RuntimeError,
            ValueError,
            OSError,
        ) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"Capability Acquisition complete: {target}")
        print(
            f"Matched items: {acquisition.scan_summary['items_with_capability_matches']} | "
            f"Reusable candidates: {len(acquisition.best_candidates)}"
        )
        for path in written:
            print(path)
        if llm_result is not None and llm_result.status != "complete":
            print(f"LLM reasoning unavailable: {llm_result.error}", file=sys.stderr)
            if args.llm_required:
                return 3
        return 0

    if args.max_file_mb <= 0 or args.max_zip_members <= 0 or args.max_opportunities <= 0 or args.technical_max_file_mb <= 0 or args.max_graph_nodes <= 0 or args.workflow_depth <= 0 or args.max_data_flow_edges <= 0:
        parser.error("scan limits must be positive")
    if args.offline and args.market_validation:
        parser.error("--offline and --market-validation cannot be used together")

    target = args.target.expanduser().resolve()
    default_output = target.parent / f"{target.name}-relic-report"
    output = (args.output or default_output).expanduser().resolve()
    try:
        if target == output or output.is_relative_to(target):
            print(
                "error: output must be outside the target so the scanned estate remains read-only",
                file=sys.stderr,
            )
            return 2
        result = audit_estate(
            target,
            limits=ScanLimits(
                max_file_bytes=args.max_file_mb * 1024 * 1024,
                max_zip_members=args.max_zip_members,
            ),
            include_hidden=args.include_hidden,
        )
        written = write_reports(result, output)
        acquisition = None
        if args.capability_acquisition or args.llm_profile:
            acquisition = analyze_capability_acquisition(result)
            written.extend(write_acquisition_reports(acquisition, output))
        llm_result = None
        if args.llm_profile and acquisition is not None:
            llm_result = reason_about_acquisition(
                acquisition,
                _llm_config(args),
            )
            written.extend(write_llm_reports(llm_result, output))
        truth = None
        run_truth = args.technical_truth or (args.product_discovery and not args.no_technical_truth)
        if run_truth:
            truth = analyze_technical_truth(
                result,
                TechnicalTruthConfig(
                    max_file_size=args.technical_max_file_mb * 1024 * 1024,
                    max_graph_nodes=args.max_graph_nodes,
                    workflow_depth=args.workflow_depth,
                    cache_path=str((args.technical_cache or output / ".relic-cache" / "technical-truth.json").resolve()),
                    use_persistent_cache=not args.no_technical_cache,
                    max_data_flow_edges=args.max_data_flow_edges,
                ),
            )
            written.extend(write_technical_truth_reports(truth, output))
        if args.product_discovery:
            discovery = discover_products(
                result,
                DiscoveryConfig(
                    max_opportunities=args.max_opportunities,
                    offline=args.offline or not args.market_validation,
                    market_validation=args.market_validation,
                    reasoning_provider=args.reasoning_provider,
                ),
                technical_truth=truth,
            )
            written.extend(write_product_reports(discovery, output))
    except (
        FileNotFoundError,
        NotADirectoryError,
        PermissionError,
        KeyError,
        RuntimeError,
        ValueError,
        OSError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"Relic audit complete: {result.target}")
    print(f"Projects: {len(result.projects)} | Files observed: {len(result.files)}")
    for path in written:
        print(path)
    if llm_result is not None and llm_result.status != "complete":
        print(f"LLM reasoning unavailable: {llm_result.error}", file=sys.stderr)
        if args.llm_required:
            return 3
    return 0


def _add_llm_reasoning_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--llm-profile",
        help="opt in to advisory reasoning with a configured API-key or OAuth profile",
    )
    parser.add_argument(
        "--llm-required",
        action="store_true",
        help="return status 3 if optional LLM reasoning fails; deterministic reports are still written",
    )
    parser.add_argument("--llm-max-input-chars", type=int, default=40_000)
    parser.add_argument("--llm-max-output-tokens", type=int, default=2_000)
    parser.add_argument("--llm-timeout-seconds", type=float, default=90.0)


def _llm_config(args: argparse.Namespace) -> LLMReasoningConfig | None:
    if not args.llm_profile:
        return None
    config = LLMReasoningConfig(
        profile=args.llm_profile,
        max_input_chars=args.llm_max_input_chars,
        max_output_tokens=args.llm_max_output_tokens,
        timeout_seconds=args.llm_timeout_seconds,
    )
    config.validate()
    return config


def _handle_llm_command(args: argparse.Namespace) -> int:
    store = ProfileStore()
    try:
        if args.llm_action == "list":
            profiles = store.list()
            if not profiles:
                print("No LLM profiles configured.")
            for profile in profiles:
                print(
                    f"{profile.name}\t{profile.protocol}\t{profile.model}\t"
                    f"{profile.auth_mode}\t"
                    f"{profile.base_url or 'local Claude Code CLI'}"
                )
            return 0
        if args.llm_action == "add":
            base_url = args.base_url or _default_base_url(args.protocol)
            api_key_env = args.api_key_env
            if args.auth == "api-key" and not api_key_env:
                api_key_env = (
                    "ANTHROPIC_API_KEY"
                    if args.protocol == "anthropic-messages"
                    else "OPENAI_API_KEY"
                )
            effort = args.effort
            if args.protocol == "claude-code" and not effort:
                effort = claude_code.DEFAULT_EFFORT
            profile = LLMProfile(
                name=args.name,
                protocol=args.protocol,
                model=args.model,
                base_url=base_url,
                auth_mode=args.auth,
                api_key_env=api_key_env,
                authorization_url=args.authorization_url,
                token_url=args.token_url,
                client_id=args.client_id,
                scopes=tuple(args.scope),
                audience=args.audience,
                effort=effort,
            )
            store.save(profile)
            print(f"Saved LLM profile: {profile.name} ({profile.auth_mode})")
            if profile.protocol == "claude-code":
                print(
                    "Reasoning host: locally installed Claude Code CLI using your "
                    "existing Claude.ai subscription session."
                )
                print(
                    "Billing boundary: subscription-only; API-billing environment "
                    "variables are removed from the Claude Code child process. "
                    "Usage remains subject to Anthropic's current plan limits and "
                    "account settings."
                )
                print(f"Next: relic llm status {profile.name}")
                print(f"If not logged in: relic llm login {profile.name}")
            elif profile.auth_mode == "api-key":
                print(f"Credential source: environment variable {profile.api_key_env}")
            else:
                print(f"Next: relic llm login {profile.name}")
            return 0
        profile = store.get(args.name)
        if args.llm_action == "remove":
            if profile.auth_mode == "oauth":
                oauth_logout(profile)
            store.remove(profile.name)
            print(f"Removed LLM profile: {profile.name}")
            return 0
        if args.llm_action == "login":
            if profile.protocol == "claude-code":
                print(
                    "Launching the official 'claude auth login' flow. Complete "
                    "authentication in your terminal/browser; Relic never reads "
                    "or stores the OAuth token."
                )
                code = claude_code.login()
                if code == 0:
                    print(f"Claude Code login flow finished: {profile.name}")
                else:
                    print(
                        f"error: 'claude auth login' exited with status {code}",
                        file=sys.stderr,
                    )
                return 0 if code == 0 else 2
            status = oauth_login(profile, timeout_seconds=args.timeout_seconds)
            print(
                f"OAuth login complete: {profile.name} "
                f"(refreshable: {'yes' if status['refreshable'] else 'no'})"
            )
            return 0
        if args.llm_action == "logout":
            if profile.protocol == "claude-code":
                print(
                    "Claude Code credentials are managed by the claude CLI, not "
                    "Relic. To sign out, run: claude auth logout"
                )
                return 0
            removed = oauth_logout(profile)
            print(
                f"OAuth credentials {'removed' if removed else 'were not stored'}: "
                f"{profile.name}"
            )
            return 0
        if profile.protocol == "claude-code":
            status = claude_code.safe_status(profile)
        elif profile.auth_mode == "oauth":
            status = oauth_status(profile)
        else:
            import os

            status = {
                "ready": bool(os.environ.get(str(profile.api_key_env))),
                "credential_source": profile.api_key_env,
            }
        print(json.dumps(status, indent=2, sort_keys=True))
        return 0
    except (KeyError, ValueError, RuntimeError, TimeoutError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _default_base_url(protocol: str) -> str:
    if protocol == "claude-code":
        return ""
    if protocol == "anthropic-messages":
        return "https://api.anthropic.com/v1"
    return "https://api.openai.com/v1"


if __name__ == "__main__":
    raise SystemExit(main())
