from __future__ import annotations

import json
import hashlib
import shutil
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..product_discovery.entitlements import Entitlement
from ..supervisor import (
    ActionProposal,
    Capability,
    ExecutionPolicy,
    SupervisorError,
    SupervisorService,
    SupervisorSession,
    claude_builder_action,
    codex_builder_action,
)
from ..build_packs.exporter import validate_export
from .components import PrimaryButton, SecondaryButton, StatusBadge
from .theme import SPACING


_CAPABILITY_EXPLANATIONS = {
    Capability.PROCESS: "Launch the selected local builder as an exact argument list.",
    Capability.FILE_WRITE: "Create, edit, or delete files inside the managed workspace only.",
    Capability.NETWORK: "Use the network during this one approved builder action.",
    Capability.CREDENTIALS: "Let the local CLI use its existing signed-in session.",
    Capability.DEPENDENCY_INSTALL: "Install third-party dependencies in the workspace.",
    Capability.GIT: "Run local Git commands in the managed workspace.",
    Capability.EXTERNAL_ACTION: "Change an external system such as publishing or deployment.",
}


class _ExecutionWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        service: SupervisorService,
        session: SupervisorSession,
        action_id: str,
    ) -> None:
        super().__init__()
        self.service = service
        self.session = session
        self.action_id = action_id

    @Slot()
    def run(self) -> None:
        try:
            result = self.service.execute(self.session, self.action_id)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.finished.emit(result)


class AssistedBuildDialog(QDialog):
    """Five-step, approval-gated build flow for an exported Build Pack.

    Nothing executes when the dialog opens. The Build Pack is verified first,
    a separate workspace is created, an immutable action is displayed, every
    requested capability must be checked, and only then is Run enabled.
    """

    STEP_TITLES = (
        "Verify the Build Pack",
        "Create a managed workspace",
        "Choose a local builder",
        "Approve exact capabilities",
        "Run and review changes",
    )

    def __init__(
        self,
        entitlement: Entitlement,
        build_pack: Path,
        sessions_root: Path,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.build_pack = build_pack.expanduser().resolve()
        self.sessions_root = sessions_root.expanduser().resolve()
        self.service = SupervisorService(entitlement)
        self.session: SupervisorSession | None = None
        self.action: ActionProposal | None = None
        self._approval_checks: list[QCheckBox] = []
        self._execution_thread: QThread | None = None
        self._execution_worker: _ExecutionWorker | None = None

        status = validate_export(self.build_pack)
        self.setWindowTitle("Assisted Build Supervisor")
        self.setAccessibleName("Approval-gated Assisted Build Supervisor")
        self.setModal(True)
        self.resize(820, 640)

        layout = QVBoxLayout(self)
        layout.setSpacing(SPACING.md)
        self.step_label = QLabel()
        self.step_label.setObjectName("panelTitle")
        self.step_label.setAccessibleName("Assisted build step")
        layout.addWidget(self.step_label)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._verified_page(status))
        self.stack.addWidget(self._workspace_page())
        self.stack.addWidget(self._builder_page())
        self.stack.addWidget(self._approval_page())
        self.stack.addWidget(self._review_page())
        layout.addWidget(self.stack, 1)

        actions = QHBoxLayout()
        self.close_button = SecondaryButton("Close")
        self.close_button.clicked.connect(self.reject)
        self.back_button = SecondaryButton("Back")
        self.back_button.clicked.connect(self.previous_step)
        self.next_button = PrimaryButton("Next")
        self.next_button.clicked.connect(self.next_step)
        actions.addWidget(self.close_button)
        actions.addStretch(1)
        actions.addWidget(self.back_button)
        actions.addWidget(self.next_button)
        layout.addLayout(actions)
        self._sync()

    def _scroll_page(self, content: QWidget) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        return scroll

    def _page(self, title: str, body: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(SPACING.md)
        heading = QLabel(title)
        heading.setObjectName("panelTitle")
        message = QLabel(body)
        message.setWordWrap(True)
        message.setTextInteractionFlags(message.textInteractionFlags())
        layout.addWidget(heading)
        layout.addWidget(message)
        return page, layout

    def _verified_page(self, status: dict[str, object]) -> QWidget:
        page, layout = self._page(
            "Step 1 — Verified input",
            "Relic will never build in the scanned source folder. It will use only "
            "this checksum-verified Build Pack and its explicitly approved assets.",
        )
        badge = StatusBadge("ready", "CHECKSUMS VERIFIED")
        layout.addWidget(badge)
        details = QLabel(
            f"Pack: {status['pack_id']}\n"
            f"Content hash: {status['content_hash']}\n"
            f"Location: {self.build_pack}"
        )
        details.setWordWrap(True)
        details.setTextInteractionFlags(details.textInteractionFlags())
        layout.addWidget(details)
        layout.addStretch(1)
        return self._scroll_page(page)

    def _workspace_page(self) -> QWidget:
        page, layout = self._page(
            "Step 2 — Separate workspace",
            "Choose Next to create a managed copy outside both the scanned source and "
            "the Build Pack. Every action is checkpointed and recorded in a tamper-evident ledger.",
        )
        self.workspace_badge = StatusBadge("idle", "NOT CREATED")
        self.workspace_location = QLabel(f"Sessions folder: {self.sessions_root}")
        self.workspace_location.setWordWrap(True)
        layout.addWidget(self.workspace_badge)
        layout.addWidget(self.workspace_location)
        layout.addStretch(1)
        return self._scroll_page(page)

    def _builder_page(self) -> QWidget:
        page, layout = self._page(
            "Step 3 — Choose the builder",
            "Relic launches one local CLI action. It does not install a provider, "
            "create an account, publish, deploy, or send messages.",
        )
        self.builder_combo = QComboBox()
        self.builder_combo.addItem("Codex CLI — recommended", "codex")
        self.builder_combo.addItem("Claude Code — developer preview", "claude")
        self.builder_combo.currentIndexChanged.connect(self._refresh_builder_status)
        self.builder_status = StatusBadge("idle", "CHECKING")
        self.builder_message = QLabel()
        self.builder_message.setWordWrap(True)
        layout.addWidget(self.builder_combo)
        layout.addWidget(self.builder_status)
        layout.addWidget(self.builder_message)
        layout.addStretch(1)
        self._refresh_builder_status()
        return self._scroll_page(page)

    def _approval_page(self) -> QWidget:
        page, layout = self._page(
            "Step 4 — Capability approval",
            "Review each requested power. Nothing is pre-approved. The approval is "
            "bound to the exact action and cannot authorize a changed command.",
        )
        self.action_identity = QLabel("No action queued.")
        self.action_identity.setWordWrap(True)
        layout.addWidget(self.action_identity)
        self.capability_host = QWidget()
        self.capability_layout = QVBoxLayout(self.capability_host)
        self.capability_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.capability_host)
        self.approval_note = QLabel(
            "Publishing, deployment, dependency installation, Git, and external actions "
            "are not part of this builder action."
        )
        self.approval_note.setWordWrap(True)
        layout.addWidget(self.approval_note)
        layout.addStretch(1)
        return self._scroll_page(page)

    def _review_page(self) -> QWidget:
        page, layout = self._page(
            "Step 5 — Run, inspect, decide",
            "Run the single approved action. When it finishes, inspect the full file "
            "diff and workspace before marking it as a candidate. Candidate means review-ready, not published.",
        )
        self.run_badge = StatusBadge("idle", "WAITING")
        self.run_button = PrimaryButton("Run approved builder action")
        self.run_button.clicked.connect(self.run_action)
        self.cancel_button = SecondaryButton("Cancel active builder")
        self.cancel_button.clicked.connect(self.cancel_execution)
        self.cancel_button.setEnabled(False)
        self.open_workspace_button = SecondaryButton("Open managed workspace")
        self.open_workspace_button.clicked.connect(self.open_workspace)
        self.finalize_button = SecondaryButton("Mark candidate ready")
        self.finalize_button.clicked.connect(self.finalize_candidate)
        self.finalize_button.setEnabled(False)
        secondary_row = QHBoxLayout()
        secondary_row.addWidget(self.cancel_button)
        secondary_row.addWidget(self.open_workspace_button)
        secondary_row.addWidget(self.finalize_button)
        secondary_row.addStretch(1)
        self.review_output = QPlainTextEdit()
        self.review_output.setReadOnly(True)
        self.review_output.setPlaceholderText("Execution result and changed files appear here.")
        layout.addWidget(self.run_badge)
        layout.addWidget(self.run_button)
        layout.addLayout(secondary_row)
        layout.addWidget(self.review_output, 1)
        return page

    @Slot()
    def _refresh_builder_status(self) -> None:
        if not hasattr(self, "builder_combo"):
            return
        provider = str(self.builder_combo.currentData())
        executable = "codex" if provider == "codex" else "claude"
        found = shutil.which(executable)
        action = codex_builder_action() if provider == "codex" else claude_builder_action()
        try:
            isolation = ExecutionPolicy.production().require(action)
            supported = True
        except SupervisorError as exc:
            isolation = None
            supported = False
            refusal = str(exc).removeprefix("production execution refused: ")
        if found and supported:
            self.builder_status.set_status("ready", "CLI FOUND")
            self.builder_message.setText(
                f"Executable: {found}\n{isolation.reason} Signed-in access is verified "
                "only when the approved action runs."
            )
        elif found:
            self.builder_status.set_status("blocked", "PREVIEW BLOCKED")
            self.builder_message.setText(
                f"Executable: {found}\n{refusal} Choose Codex for the v0.12 production "
                "path. Claude remains visible so this limitation is explicit."
            )
        else:
            self.builder_status.set_status("failed", "CLI NOT FOUND")
            self.builder_message.setText(
                f"{executable} was not found on PATH. Install and sign in to the official CLI, then reopen this flow."
            )
        if self.stack.currentIndex() == 2:
            self.next_button.setEnabled(bool(found) and supported)

    def _create_session(self) -> None:
        if self.session is not None:
            return
        self.session = self.service.create_session(self.build_pack, self.sessions_root)
        self.workspace_badge.set_status("ready", "ISOLATED WORKSPACE READY")
        self.workspace_location.setText(f"Managed workspace: {self.session.workspace}")

    def _queue_builder(self) -> None:
        if self.session is None:
            raise SupervisorError("managed workspace has not been created")
        if self.action is not None:
            return
        provider = str(self.builder_combo.currentData())
        self.action = (
            codex_builder_action()
            if provider == "codex"
            else claude_builder_action()
        )
        isolation = self.service.execution_policy.require(self.action)
        self.service.plan(self.session, _SingleActionAdapter(self.action, provider))
        argv = self.action.parameters.get("argv", [])
        prompt = str(self.action.parameters.get("stdin_text", ""))
        self.action_identity.setText(
            f"Action: {self.action.summary}\n"
            f"Immutable ID: {self.action.action_id}\n"
            f"Risk: {self.action.risk.upper()}\n"
            f"Execution boundary: {isolation.boundary.value} — {isolation.reason}\n"
            f"Exact command: {json.dumps(argv, ensure_ascii=False)}\n"
            f"Instruction SHA-256: {hashlib.sha256(prompt.encode('utf-8')).hexdigest()}"
        )
        for checkbox in self._approval_checks:
            checkbox.deleteLater()
        self._approval_checks.clear()
        for capability in self.action.capabilities:
            row = QWidget()
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(SPACING.xs)
            checkbox = QCheckBox(
                f"Approve {capability.value.replace('_', ' ')}"
            )
            checkbox.setAccessibleName(f"Approve {capability.value} for this exact action")
            checkbox.toggled.connect(self._sync)
            explanation = QLabel(_CAPABILITY_EXPLANATIONS[capability])
            explanation.setWordWrap(True)
            explanation.setObjectName("dimLabel")
            row_layout.addWidget(checkbox)
            row_layout.addWidget(explanation)
            self.capability_layout.addWidget(row)
            self._approval_checks.append(checkbox)

    def _grant_approval(self) -> None:
        if self.session is None or self.action is None:
            raise SupervisorError("no builder action is ready for approval")
        if not all(item.isChecked() for item in self._approval_checks):
            raise SupervisorError("every requested capability must be explicitly approved")
        self.service.approve(
            self.session,
            self.action.action_id,
            self.action.capabilities,
            actor="desktop-operator",
        )

    @Slot()
    def next_step(self) -> None:
        index = self.stack.currentIndex()
        try:
            if index == 1:
                self._create_session()
            elif index == 2:
                self._queue_builder()
            elif index == 3:
                self._grant_approval()
        except (PermissionError, OSError, ValueError, SupervisorError) as exc:
            QMessageBox.warning(self, "Assisted Build Supervisor", str(exc))
            return
        if index < self.stack.count() - 1:
            self.stack.setCurrentIndex(index + 1)
            self._sync()
        else:
            self.accept()

    @Slot()
    def previous_step(self) -> None:
        index = self.stack.currentIndex()
        if index <= 0 or self.action is not None:
            return
        self.stack.setCurrentIndex(index - 1)
        self._sync()

    @Slot()
    def _sync(self) -> None:
        index = self.stack.currentIndex()
        self.step_label.setText(
            f"Step {index + 1} of {self.stack.count()} · {self.STEP_TITLES[index]}"
        )
        self.back_button.setEnabled(index > 0 and self.action is None)
        labels = {
            0: "Verify and continue",
            1: "Create managed workspace",
            2: "Review builder action",
            3: "Approve and continue",
            4: "Close",
        }
        self.next_button.setText(labels[index])
        enabled = self._execution_thread is None
        if index == 2:
            executable = "codex" if self.builder_combo.currentData() == "codex" else "claude"
            action = (
                codex_builder_action()
                if self.builder_combo.currentData() == "codex"
                else claude_builder_action()
            )
            try:
                self.service.execution_policy.require(action)
                supported = True
            except SupervisorError:
                supported = False
            enabled = enabled and shutil.which(executable) is not None and supported
        if index == 3:
            enabled = enabled and bool(self._approval_checks) and all(
                item.isChecked() for item in self._approval_checks
            )
        self.next_button.setEnabled(enabled)

    @Slot()
    def run_action(self) -> None:
        if self._execution_thread is not None or self.session is None or self.action is None:
            return
        self.run_badge.set_status("running", "BUILDER RUNNING")
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.next_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.review_output.setPlainText(
            "The builder is running inside the managed workspace. Relic will checkpoint, "
            "enforce budgets, record the action, and show the changed paths here."
        )
        thread = QThread(self)
        worker = _ExecutionWorker(self.service, self.session, self.action.action_id)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._execution_complete)
        worker.failed.connect(self._execution_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(self._execution_thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._execution_thread = thread
        self._execution_worker = worker
        thread.start()

    @Slot()
    def cancel_execution(self) -> None:
        if self._execution_thread is None or self.session is None:
            return
        try:
            self.service.cancel(self.session)
        except SupervisorError as exc:
            QMessageBox.warning(self, "Cancel active builder", str(exc))
            return
        self.cancel_button.setEnabled(False)
        self.run_badge.set_status("warning", "CANCELLING — RESTORING CHECKPOINT")
        self.review_output.appendPlainText(
            "\nCancellation requested. Relic is terminating the builder process tree "
            "and restoring the pre-action checkpoint."
        )

    @Slot(object)
    def _execution_complete(self, result: dict[str, object]) -> None:
        if self.session is None:
            return
        changes = self.service.diff(self.session)
        self.run_badge.set_status("ready", "ACTION COMPLETE — REVIEW REQUIRED")
        self.review_output.setPlainText(
            json.dumps({"result": result, "workspace_diff": changes}, indent=2)
        )
        self.finalize_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    @Slot(str)
    def _execution_failed(self, message: str) -> None:
        cancelled = self.session is not None and self.session.state.value == "cancelled"
        self.run_badge.set_status(
            "warning" if cancelled else "failed",
            "CANCELLED — CHECKPOINT RESTORED" if cancelled else "ACTION FAILED",
        )
        self.cancel_button.setEnabled(False)
        self.review_output.setPlainText(
            message
            + (
                "\n\nThe builder process tree was terminated and the pre-action checkpoint was restored."
                if cancelled
                else "\n\nThe workspace remains local. Check the action log and checkpoint before deciding whether to resume."
            )
        )

    @Slot()
    def _execution_thread_finished(self) -> None:
        self._execution_thread = None
        self._execution_worker = None
        self.close_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.next_button.setEnabled(True)
        self._sync()

    @Slot()
    def open_workspace(self) -> None:
        if self.session is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.session.workspace)))

    @Slot()
    def finalize_candidate(self) -> None:
        if self.session is None:
            return
        try:
            candidate = self.service.finalize_candidate(self.session)
        except (PermissionError, OSError, ValueError, SupervisorError) as exc:
            QMessageBox.warning(self, "Candidate review", str(exc))
            return
        self.finalize_button.setEnabled(False)
        self.run_badge.set_status("ready", "CANDIDATE READY — NOT PUBLISHED")
        self.review_output.appendPlainText(f"\nCandidate record: {candidate}")

    def reject(self) -> None:
        if self._execution_thread is not None:
            QMessageBox.information(
                self,
                "Builder still running",
                "Use Cancel active builder, or wait for the bounded action to finish or time out.",
            )
            return
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt naming
        if self._execution_thread is not None:
            event.ignore()
            return
        super().closeEvent(event)


class _SingleActionAdapter:
    def __init__(self, action: ActionProposal, provider: str) -> None:
        self.action = action
        self.name = f"desktop-{provider}-supervisor"

    def plan(self, session: SupervisorSession) -> tuple[ActionProposal, ...]:
        del session
        return (self.action,)
