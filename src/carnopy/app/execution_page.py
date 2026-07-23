from __future__ import annotations

import shlex

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

from carnopy.app.execution_controller import DatasetExecutionController


class DatasetExecutionPage(QWidget):
    """Temporary Widgets view over the authoritative execution controller."""

    run_finalized = Signal(object)

    def __init__(
        self,
        controller: DatasetExecutionController,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.coordinator = controller.coordinator

        root = QVBoxLayout(self)
        heading = QLabel("Validate and Generate")
        heading.setStyleSheet("font-size: 18px; font-weight: bold;")
        root.addWidget(heading)
        self.config_label = QLabel()
        self.config_label.setWordWrap(True)
        root.addWidget(self.config_label)

        actions = QHBoxLayout()
        self.validate_button = QPushButton("Validate")
        self.generate_button = QPushButton("Generate")
        self.cancel_button = QPushButton("Cancel")
        self.force_stop_button = QPushButton("Force Stop")
        self.validate_button.clicked.connect(controller.validate)
        self.generate_button.clicked.connect(controller.generate)
        self.cancel_button.clicked.connect(controller.cancel)
        self.force_stop_button.clicked.connect(controller.force_stop)
        for button in (
            self.validate_button,
            self.generate_button,
            self.cancel_button,
            self.force_stop_button,
        ):
            actions.addWidget(button)
        actions.addStretch(1)
        root.addLayout(actions)

        self.phase_label = QLabel()
        self.phase_label.setAccessibleName("Execution phase")
        root.addWidget(self.phase_label)
        self.progress = QProgressBar()
        root.addWidget(self.progress)
        root.addWidget(QLabel("Equivalent CLI command (informational only)"))
        self.command = QPlainTextEdit()
        self.command.setReadOnly(True)
        self.command.setMaximumHeight(75)
        root.addWidget(self.command)
        self.result = QLabel()
        self.result.setWordWrap(True)
        self.result.setAccessibleName("Execution result")
        root.addWidget(self.result)
        self.inspect_button = QPushButton("Inspect Run")
        root.addWidget(self.inspect_button)
        root.addStretch(1)

        controller.state_changed.connect(self._refresh)
        controller.run_finalized.connect(self.run_finalized)
        self._refresh()

    @property
    def owns_active_request(self) -> bool:
        return self.controller.owns_active_request

    def validate(self) -> bool:
        return self.controller.validate()

    def generate(self) -> bool:
        return self.controller.generate()

    def cancel(self) -> bool:
        return self.controller.cancel()

    def force_stop(self) -> bool:
        return self.controller.force_stop()

    def _refresh(self) -> None:
        controller = self.controller
        if controller.get_snapshot_available():
            self.config_label.setText(
                f"{controller.get_snapshot_path()}\nSHA-256: {controller.get_snapshot_sha256()}"
            )
        else:
            self.config_label.setText(
                controller.get_snapshot_issue() or "No executable configuration is open."
            )
        self._update_command()
        self._update_progress()
        self._update_result()
        self.validate_button.setEnabled(controller.get_can_validate())
        self.generate_button.setEnabled(controller.get_can_generate())
        self.cancel_button.setEnabled(controller.get_can_cancel())
        self.force_stop_button.setVisible(controller.get_can_force_stop())
        self.force_stop_button.setEnabled(controller.get_can_force_stop())
        output_directory = controller.get_result_output_directory()
        self.inspect_button.setProperty("source_path", output_directory)
        inspectable = controller.get_state() == "succeeded" and bool(output_directory)
        self.inspect_button.setVisible(inspectable)
        self.inspect_button.setEnabled(inspectable)

    def _update_command(self) -> None:
        controller = self.controller
        path = controller.get_snapshot_path()
        workspace = controller.workspace
        if not path:
            self.command.clear()
            return
        operation = controller.get_operation() or "generate"
        if operation == "validate":
            parts = ["carnopy", "validate", path]
        elif workspace is not None:
            parts = [
                "carnopy",
                "generate",
                path,
                "--out",
                str(workspace.outputs),
                "--figures-out",
                str(workspace.figures),
            ]
        else:
            parts = []
        self.command.setPlainText(shlex.join(parts))

    def _update_progress(self) -> None:
        state = self.controller.get_state()
        completed = self.controller.get_completed_rows()
        total = self.controller.get_total_rows()
        if state == "starting":
            self.progress.setRange(0, 0)
            self.progress.setFormat("Starting worker…")
        else:
            self.progress.setRange(0, max(total, 1))
            self.progress.setValue(min(completed, max(total, 1)))
            self.progress.setFormat(f"{completed} / {total} rows")
        phase = self.controller.get_phase()
        self.phase_label.setText(f"Phase: {phase}" if phase else _state_label(state))

    def _update_result(self) -> None:
        controller = self.controller
        state = controller.get_state()
        if state == "succeeded" and controller.get_operation() == "validate":
            self.result.setText(
                "Validation completed. "
                f"Mode: {controller.get_result_mode()}; "
                f"projected rows: {controller.get_result_projected_rows()}; "
                f"model: {controller.get_result_backend_model()}."
            )
        elif state == "succeeded":
            visualization = controller.get_result_visualization_status() or "not configured"
            self.result.setText(
                f"Generation {controller.get_result_run_status()}. "
                f"Rows: {controller.get_result_row_count()} total, "
                f"{controller.get_result_valid_row_count()} valid, "
                f"{controller.get_result_invalid_row_count()} invalid.\n"
                f"Run: {controller.get_result_output_directory()}\n"
                f"Configured visualization: {visualization}."
            )
        elif state in {"invalid", "failed", "cancelled", "force_stopped"}:
            self.result.setText(
                f"{controller.get_failure_code()}: {controller.get_failure_message()}"
            )
        elif state in {
            "starting",
            "running",
            "cancellation_requested",
            "force_stopping",
        }:
            self.result.setText("Request accepted; waiting for worker progress.")
        else:
            self.result.setText("No validation or generation result yet.")


def _state_label(state: str) -> str:
    return {
        "unavailable": "Unavailable",
        "ready": "Idle",
        "running": "Running",
        "cancellation_requested": "Cancellation requested",
        "force_stopping": "Force-stopping worker…",
        "succeeded": "Completed",
        "invalid": "Invalid",
        "failed": "Failed",
        "cancelled": "Cancelled",
        "force_stopped": "Force-stopped",
    }.get(state, state.replace("_", " ").title())
