from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from carnopy.app.config_document import SavedConfigSnapshot
from carnopy.app.protocol import RequestType, WorkerEvent
from carnopy.app.request_coordinator import (
    DesktopRequestCoordinator,
    RequestOutcome,
    RequestSession,
)
from carnopy.app.workspace import Workspace


class DatasetExecutionPage(QWidget):
    """Validate and generate one saved workspace dataset configuration."""

    run_finalized = Signal(object)
    request_started = Signal(object)
    request_event = Signal(object)
    request_terminal = Signal(object)

    def __init__(
        self,
        coordinator: DesktopRequestCoordinator,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.coordinator = coordinator
        self.workspace: Workspace | None = None
        self.snapshot: SavedConfigSnapshot | None = None
        self._session: RequestSession | None = None
        self._operation: str | None = None

        root = QVBoxLayout(self)
        heading = QLabel("Validate and Generate")
        heading.setStyleSheet("font-size: 18px; font-weight: bold;")
        root.addWidget(heading)
        self.config_label = QLabel("Open and save a dataset configuration first.")
        self.config_label.setWordWrap(True)
        root.addWidget(self.config_label)

        actions = QHBoxLayout()
        self.validate_button = QPushButton("Validate")
        self.generate_button = QPushButton("Generate")
        self.cancel_button = QPushButton("Cancel")
        self.force_stop_button = QPushButton("Force Stop")
        self.cancel_button.setEnabled(False)
        self.force_stop_button.setVisible(False)
        self.validate_button.clicked.connect(self.validate)
        self.generate_button.clicked.connect(self.generate)
        self.cancel_button.clicked.connect(self.cancel)
        self.force_stop_button.clicked.connect(self.force_stop)
        for button in (
            self.validate_button,
            self.generate_button,
            self.cancel_button,
            self.force_stop_button,
        ):
            actions.addWidget(button)
        actions.addStretch(1)
        root.addLayout(actions)

        self.phase_label = QLabel("Idle")
        self.phase_label.setAccessibleName("Execution phase")
        root.addWidget(self.phase_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat("0 / 0 rows")
        root.addWidget(self.progress)
        root.addWidget(QLabel("Equivalent CLI command (informational only)"))
        self.command = QPlainTextEdit()
        self.command.setReadOnly(True)
        self.command.setMaximumHeight(75)
        root.addWidget(self.command)
        self.result = QLabel("No validation or generation result yet.")
        self.result.setWordWrap(True)
        self.result.setAccessibleName("Execution result")
        root.addWidget(self.result)
        self.inspect_button = QPushButton("Inspect Run")
        self.inspect_button.setEnabled(False)
        self.inspect_button.setVisible(False)
        root.addWidget(self.inspect_button)
        root.addStretch(1)

        self.coordinator.busy_changed.connect(self._busy_changed)
        self._update_actions()

    @property
    def owns_active_request(self) -> bool:
        return self._session is not None

    def set_workspace(self, workspace: Workspace | None) -> None:
        self.workspace = workspace
        if workspace is None:
            self.set_snapshot(None, "Open a workspace first.")

    def set_snapshot(
        self,
        snapshot: SavedConfigSnapshot | None,
        issue: str | None = None,
    ) -> None:
        self.snapshot = snapshot
        if snapshot is None:
            self.config_label.setText(issue or "No executable configuration is open.")
            self.command.clear()
        else:
            self.config_label.setText(f"{snapshot.path}\nSHA-256: {snapshot.sha256}")
            self._update_command("generate")
        self._update_actions()

    def validate(self) -> None:
        self._start("validate")

    def generate(self) -> None:
        self._start("generate")

    def _start(self, operation: str) -> None:
        snapshot = self.snapshot
        workspace = self.workspace
        if snapshot is None or workspace is None or self.coordinator.is_busy:
            return
        self._operation = operation
        self.result.setText("Request accepted; waiting for worker progress.")
        self.phase_label.setText("Starting worker…")
        self.progress.setRange(0, 0)
        self.inspect_button.setVisible(False)
        self.inspect_button.setEnabled(False)
        self._update_command(operation)
        common: dict[str, object] = {
            "config_path": str(snapshot.path),
            "expected_config_sha256": snapshot.sha256,
        }
        if operation == "validate":
            request_type: RequestType = "validate_config"
            payload = common
        else:
            request_type = "generate_dataset"
            payload = {
                **common,
                "output_root": str(workspace.outputs),
                "figures_root": str(workspace.figures),
            }
        session = self.coordinator.start_request("execution", request_type, payload)
        self._session = session
        session.event_received.connect(self._event_received)
        session.completed.connect(self._request_completed)
        session.policy_changed.connect(self._session_policy_changed)
        self.request_started.emit(
            {
                "request_id": str(session.request_id),
                "operation": operation,
                "snapshot": snapshot,
            }
        )
        self._update_actions()

    def cancel(self) -> bool:
        session = self._session
        if session is None:
            return False
        if not session.cancel():
            return False
        self.phase_label.setText("Cancellation requested; waiting for a safe checkpoint…")
        self._update_actions()
        return True

    def force_stop(self) -> bool:
        session = self._session
        stopped = session is not None and session.force_stop()
        if stopped:
            self.force_stop_button.setEnabled(False)
            self.phase_label.setText("Force-stopping worker…")
        return stopped

    def _event_received(self, value: object) -> None:
        event = cast(WorkerEvent, value)
        self.request_event.emit(event)
        if event.type == "phase":
            phase = str(event.payload.get("name", "unknown"))
            self.phase_label.setText(f"Phase: {phase}")
        elif event.type == "progress":
            completed = int(event.payload.get("completed", 0))
            total = int(event.payload.get("total", 0))
            self.progress.setRange(0, max(total, 1))
            self.progress.setValue(min(completed, max(total, 1)))
            self.progress.setFormat(f"{completed} / {total} rows")
        elif event.type in {"result", "error", "cancelled"}:
            self.cancel_button.setEnabled(False)
            self.force_stop_button.setVisible(False)

    def _request_completed(self, value: object) -> None:
        outcome = cast(RequestOutcome, value)
        session = self._session
        if session is None or outcome.request_id != session.request_id:
            return
        self.request_terminal.emit(outcome.terminal_envelope)
        result = outcome.result_payload
        if result is not None:
            self._request_succeeded(result)
            return
        self._request_failed(outcome.failure_payload or {})

    def _request_succeeded(self, value: object) -> None:
        if self._session is None:
            return
        payload = cast(dict[str, Any], value)
        operation = self._operation
        if operation == "validate":
            self.result.setText(
                "Validation completed. "
                f"Mode: {payload.get('mode')}; projected rows: {payload.get('projected_rows')}; "
                f"model: {payload.get('backend_model')}."
            )
        else:
            output_directory = payload.get("output_directory")
            visualization = payload.get("visualization")
            visualization_text = "not configured"
            if isinstance(visualization, dict):
                visualization_text = str(visualization.get("status", "unknown"))
            self.result.setText(
                f"Generation {payload.get('run_status')}. "
                f"Rows: {payload.get('row_count')} total, {payload.get('valid_row_count')} valid, "
                f"{payload.get('invalid_row_count')} invalid.\n"
                f"Run: {output_directory}\nConfigured visualization: {visualization_text}."
            )
            if isinstance(output_directory, str):
                self.inspect_button.setProperty("source_path", output_directory)
                self.inspect_button.setVisible(True)
                self.inspect_button.setEnabled(True)
                self.run_finalized.emit(Path(output_directory))
        self.phase_label.setText("Completed")
        self._finish_local_request()

    def _request_failed(self, value: object) -> None:
        if self._session is None:
            return
        payload = cast(dict[str, Any], value)
        code = str(payload.get("code", "execution_failed"))
        message = str(payload.get("message", "worker request failed"))
        if code == "cancelled":
            self.phase_label.setText("Cancelled")
        elif code == "force_stopped":
            self.phase_label.setText("Force-stopped")
        else:
            self.phase_label.setText("Failed")
        self.result.setText(f"{code}: {message}")
        self._finish_local_request()

    def _finish_local_request(self) -> None:
        self.force_stop_button.setVisible(False)
        self._session = None
        self._operation = None
        self._update_actions()

    def _session_policy_changed(self) -> None:
        self._update_actions()

    def _busy_changed(self, _busy: bool) -> None:
        self._update_actions()

    def _update_command(self, operation: str) -> None:
        snapshot = self.snapshot
        workspace = self.workspace
        if snapshot is None:
            self.command.clear()
            return
        if operation == "validate":
            parts = ["carnopy", "validate", str(snapshot.path)]
        elif workspace is not None:
            parts = [
                "carnopy",
                "generate",
                str(snapshot.path),
                "--out",
                str(workspace.outputs),
                "--figures-out",
                str(workspace.figures),
            ]
        else:
            parts = []
        self.command.setPlainText(shlex.join(parts))

    def _update_actions(self) -> None:
        ready = self.snapshot is not None and self.workspace is not None
        available = ready and not self.coordinator.is_busy
        self.validate_button.setEnabled(available)
        self.generate_button.setEnabled(available)
        session = self._session
        self.cancel_button.setEnabled(session is not None and session.cooperative_cancel_available)
        force_available = session is not None and session.force_stop_available
        self.force_stop_button.setVisible(force_available)
        self.force_stop_button.setEnabled(force_available)
