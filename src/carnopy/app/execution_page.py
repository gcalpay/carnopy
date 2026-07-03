from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from carnopy.app.client import WorkerClient
from carnopy.app.config_document import SavedConfigSnapshot
from carnopy.app.protocol import RequestType, WorkerEvent
from carnopy.app.workspace import Workspace


class DatasetExecutionPage(QWidget):
    """Validate and generate one saved workspace dataset configuration."""

    run_finalized = Signal(object)
    request_started = Signal(object)
    request_terminal = Signal(object)

    def __init__(self, client: WorkerClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.client = client
        self.workspace: Workspace | None = None
        self.snapshot: SavedConfigSnapshot | None = None
        self._request_id: UUID | None = None
        self._operation: str | None = None
        self._cancellable = False

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

        self.force_timer = QTimer(self)
        self.force_timer.setSingleShot(True)
        self.force_timer.setInterval(5_000)
        self.force_timer.timeout.connect(self._show_force_stop)
        self.client.event_received.connect(self._event_received)
        self.client.request_succeeded.connect(self._request_succeeded)
        self.client.request_failed.connect(self._request_failed)
        self.client.request_finished.connect(self._request_finished)
        self.client.busy_changed.connect(self._busy_changed)
        self._update_actions()

    @property
    def owns_active_request(self) -> bool:
        return self._request_id is not None

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
        if snapshot is None or workspace is None or self.client.is_busy:
            return
        self._operation = operation
        self._cancellable = True
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
        self._request_id = self.client.start_request(request_type, payload)
        self.request_started.emit(
            {
                "request_id": str(self._request_id),
                "operation": operation,
                "snapshot": snapshot,
            }
        )
        self._update_actions()

    def cancel(self) -> bool:
        if not self._cancellable or not self.owns_active_request:
            return False
        if not self.client.request_cancel():
            return False
        self.cancel_button.setEnabled(False)
        self.phase_label.setText("Cancellation requested; waiting for a safe checkpoint…")
        self.force_timer.start()
        return True

    def force_stop(self) -> bool:
        stopped = self.client.force_stop()
        if stopped:
            self.force_stop_button.setEnabled(False)
            self.phase_label.setText("Force-stopping worker…")
        return stopped

    def _show_force_stop(self) -> None:
        if self.owns_active_request and self.client.is_busy:
            self.force_stop_button.setVisible(True)
            self.force_stop_button.setEnabled(True)

    def _event_received(self, value: object) -> None:
        event = cast(WorkerEvent, value)
        if event.request_id != self._request_id:
            return
        if event.type == "phase":
            phase = str(event.payload.get("name", "unknown"))
            self._cancellable = bool(event.payload.get("cancellable", True))
            self.phase_label.setText(f"Phase: {phase}")
            self.cancel_button.setEnabled(self._cancellable)
        elif event.type == "progress":
            completed = int(event.payload.get("completed", 0))
            total = int(event.payload.get("total", 0))
            self.progress.setRange(0, max(total, 1))
            self.progress.setValue(min(completed, max(total, 1)))
            self.progress.setFormat(f"{completed} / {total} rows")
        elif event.type in {"result", "error", "cancelled"}:
            self._cancellable = False
            self.cancel_button.setEnabled(False)
            self.force_timer.stop()
            self.force_stop_button.setVisible(False)

    def _request_finished(self, value: object) -> None:
        envelope = cast(dict[str, object], value)
        if str(envelope.get("request_id")) != str(self._request_id):
            return
        self.request_terminal.emit(envelope)

    def _request_succeeded(self, value: object) -> None:
        if self._request_id is None:
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
        if self._request_id is None:
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
        self.force_timer.stop()
        self.force_stop_button.setVisible(False)
        self._cancellable = False
        self._request_id = None
        self._operation = None
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
        available = ready and not self.client.is_busy
        self.validate_button.setEnabled(available)
        self.generate_button.setEnabled(available)
        self.cancel_button.setEnabled(
            self.owns_active_request and self.client.is_busy and self._cancellable
        )
