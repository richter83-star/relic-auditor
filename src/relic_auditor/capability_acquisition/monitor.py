from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import time
from typing import Callable

from ..audit import audit_estate
from ..models import ScanLimits
from ..llm.reasoner import reason_about_acquisition
from ..llm.reports import write_llm_reports
from ..llm.schemas import LLMReasoningConfig
from ..safety import IGNORED_DIRECTORIES, JUNK_FILES
from .analyzer import analyze_capability_acquisition
from .reports import write_acquisition_reports
from .schemas import AcquisitionConfig


@dataclass(frozen=True)
class ReadyDrop:
    path: Path
    fingerprint: tuple[int, int, int]


@dataclass
class _ObservedDrop:
    fingerprint: tuple[int, int, int]
    changed_at: float
    processed_fingerprint: tuple[int, int, int] | None = None


class RelicMonitor:
    """Polling inbox monitor with deterministic stability/debounce checks."""

    def __init__(
        self,
        inbox: Path,
        *,
        debounce_seconds: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if debounce_seconds < 0:
            raise ValueError("debounce_seconds cannot be negative")
        self.inbox = inbox.expanduser().resolve()
        self.debounce_seconds = debounce_seconds
        self.clock = clock
        self._observed: dict[Path, _ObservedDrop] = {}

    def poll_once(self, now: float | None = None) -> list[ReadyDrop]:
        if not self.inbox.exists():
            raise FileNotFoundError(f"monitor inbox does not exist: {self.inbox}")
        if not self.inbox.is_dir():
            raise NotADirectoryError(f"monitor inbox is not a folder: {self.inbox}")
        current_time = self.clock() if now is None else now
        candidates = {
            path.resolve(): _fingerprint(path)
            for path in sorted(self.inbox.iterdir(), key=lambda item: item.name.lower())
            if _eligible_drop(path)
        }
        for vanished in set(self._observed) - set(candidates):
            self._observed.pop(vanished, None)
        ready = []
        for path, fingerprint in candidates.items():
            observed = self._observed.get(path)
            if observed is None:
                self._observed[path] = _ObservedDrop(fingerprint, current_time)
                continue
            if observed.fingerprint != fingerprint:
                observed.fingerprint = fingerprint
                observed.changed_at = current_time
                continue
            if (
                current_time - observed.changed_at >= self.debounce_seconds
                and observed.processed_fingerprint != fingerprint
            ):
                observed.processed_fingerprint = fingerprint
                ready.append(ReadyDrop(path, fingerprint))
        return ready


def process_drop(
    drop: ReadyDrop,
    output_root: Path,
    *,
    limits: ScanLimits | None = None,
    include_hidden: bool = False,
    config: AcquisitionConfig | None = None,
    llm_config: LLMReasoningConfig | None = None,
    llm_required: bool = False,
) -> list[Path]:
    destination = output_root.expanduser().resolve() / f"{_slug(drop.path.name)}-acquisition"
    audit = audit_estate(drop.path, limits=limits, include_hidden=include_hidden)
    result = analyze_capability_acquisition(audit, config)
    written = write_acquisition_reports(result, destination)
    if llm_config is not None:
        reasoning = reason_about_acquisition(result, llm_config)
        written.extend(write_llm_reports(reasoning, destination))
        if llm_required and reasoning.status != "complete":
            raise RuntimeError(
                f"required LLM reasoning was unavailable: {reasoning.error}"
            )
    return written


def run_monitor(
    inbox: Path,
    output_root: Path,
    *,
    debounce_seconds: float = 2.0,
    poll_seconds: float = 1.0,
    once: bool = False,
    on_report: Callable[[Path, list[Path]], None] | None = None,
    llm_config: LLMReasoningConfig | None = None,
    llm_required: bool = False,
) -> None:
    if poll_seconds <= 0:
        raise ValueError("poll_seconds must be positive")
    resolved_inbox = inbox.expanduser().resolve()
    resolved_output = output_root.expanduser().resolve()
    if resolved_output == resolved_inbox or resolved_output.is_relative_to(resolved_inbox):
        raise ValueError("monitor output must be outside the inbox")
    monitor = RelicMonitor(resolved_inbox, debounce_seconds=debounce_seconds)
    monitor.poll_once()
    if once:
        if debounce_seconds:
            time.sleep(debounce_seconds)
        ready = monitor.poll_once()
        for drop in ready:
            written = process_drop(
                drop,
                resolved_output,
                llm_config=llm_config,
                llm_required=llm_required,
            )
            if on_report is not None:
                on_report(drop.path, written)
        return
    while True:
        for drop in monitor.poll_once():
            written = process_drop(
                drop,
                resolved_output,
                llm_config=llm_config,
                llm_required=llm_required,
            )
            if on_report is not None:
                on_report(drop.path, written)
        time.sleep(poll_seconds)


def _eligible_drop(path: Path) -> bool:
    name = path.name
    if path.is_symlink() or name.startswith(".") or name in JUNK_FILES:
        return False
    return not name.lower().endswith((".partial", ".part", ".tmp", ".crdownload"))


def _fingerprint(path: Path) -> tuple[int, int, int]:
    if path.is_file():
        stat = path.stat()
        return 1, stat.st_size, stat.st_mtime_ns
    count = 0
    total = 0
    latest = path.stat().st_mtime_ns
    for root, directories, files in os.walk(path, topdown=True, followlinks=False):
        directories[:] = sorted(
            name
            for name in directories
            if name not in IGNORED_DIRECTORIES and not name.startswith(".")
        )
        root_path = Path(root)
        for name in sorted(files):
            item = root_path / name
            if item.is_symlink() or name in JUNK_FILES:
                continue
            try:
                stat = item.stat()
            except OSError:
                continue
            count += 1
            total += stat.st_size
            latest = max(latest, stat.st_mtime_ns)
    return count, total, latest


def _slug(value: str) -> str:
    cleaned = "".join(character if character.isalnum() or character in "-_." else "-" for character in value)
    return cleaned.strip(".-") or "drop"
