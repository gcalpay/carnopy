from __future__ import annotations

import copy
import json
import shlex
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from carnopy.app.client import WorkerClient
from carnopy.app.plot_request_dialog import PlotRequestDialog
from carnopy.app.protocol import WorkerEvent
from carnopy.app.workspace import Workspace


class PlotPage(QWidget):
    request_changed = Signal(object)
    render_finished = Signal(object)

    def __init__(self, client: WorkerClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.client = client
        self.workspace: Workspace | None = None
        self.inspection: dict[str, Any] | None = None
        self.context: dict[str, Any] | None = None
        self.request: dict[str, Any] | None = None
        self._source_identity: tuple[str, str] | None = None
        self._request_id: UUID | None = None
        self._cleanup_error: str | None = None

        layout = QVBoxLayout(self)
        heading = QLabel("Plot")
        heading.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(heading)
        self.source_label = QLabel("Inspect a dataset source first.")
        self.source_label.setWordWrap(True)
        layout.addWidget(self.source_label)
        self.status = QLabel("Manual plotting is available for inspected datasets only.")
        self.status.setWordWrap(True)
        self.status.setAccessibleName("Plot source status")
        layout.addWidget(self.status)
        self.reference_advisory = QLabel()
        self.reference_advisory.setWordWrap(True)
        self.reference_advisory.setAccessibleName("Plot reference-state advisory")
        layout.addWidget(self.reference_advisory)

        actions = QHBoxLayout()
        self.edit_button = QPushButton("Edit Plot Request…")
        self.edit_button.clicked.connect(self.edit_request)
        self.edit_button.setEnabled(False)
        actions.addWidget(self.edit_button)
        actions.addWidget(QLabel("Format"))
        self.format_selector = QComboBox()
        self.format_selector.addItems(["png", "svg", "pdf"])
        self.format_selector.setAccessibleName("Plot output format")
        self.format_selector.currentTextChanged.connect(self._render_inputs_changed)
        actions.addWidget(self.format_selector)
        self.render_button = QPushButton("Render Plot")
        self.render_button.clicked.connect(self.render_plot)
        self.render_button.setEnabled(False)
        actions.addWidget(self.render_button)
        self.force_stop_button = QPushButton("Force Stop Render")
        self.force_stop_button.clicked.connect(self.force_stop)
        self.force_stop_button.setVisible(False)
        self.force_stop_button.setEnabled(False)
        actions.addWidget(self.force_stop_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.phase_label = QLabel("Idle")
        self.phase_label.setAccessibleName("Plot rendering phase")
        layout.addWidget(self.phase_label)
        layout.addWidget(QLabel("Session plot request"))
        self.request_summary = QPlainTextEdit()
        self.request_summary.setReadOnly(True)
        self.request_summary.setAccessibleName("Plot request summary")
        layout.addWidget(self.request_summary, 1)
        layout.addWidget(QLabel("Equivalent CLI command (informational only)"))
        self.command = QPlainTextEdit()
        self.command.setReadOnly(True)
        self.command.setMaximumHeight(85)
        self.command.setAccessibleName("Equivalent plot command")
        layout.addWidget(self.command)
        layout.addWidget(QLabel("Render result"))
        self.result_summary = QPlainTextEdit()
        self.result_summary.setReadOnly(True)
        self.result_summary.setMaximumHeight(150)
        self.result_summary.setAccessibleName("Plot render result")
        layout.addWidget(self.result_summary)

        self.client.event_received.connect(self._event_received)
        self.client.request_succeeded.connect(self._request_succeeded)
        self.client.request_failed.connect(self._request_failed)
        self.client.request_finished.connect(self._request_finished)
        self.client.busy_changed.connect(self._busy_changed)

    @property
    def owns_active_request(self) -> bool:
        return self._request_id is not None

    @property
    def source_path(self) -> Path | None:
        if self.inspection is None:
            return None
        value = self.inspection.get("source")
        return Path(value) if isinstance(value, str) else None

    def set_workspace(self, workspace: Workspace | None) -> None:
        if self.workspace != workspace:
            self.workspace = workspace
            self.set_inspection(None)

    def set_inspection(self, value: object) -> None:
        inspection = value if isinstance(value, dict) else None
        identity = (
            (str(inspection.get("source")), str(inspection.get("revision")))
            if inspection is not None
            else None
        )
        if identity != self._source_identity:
            self.request = None
            self.request_summary.clear()
            self._clear_render_result()
            self.request_changed.emit(None)
        self._source_identity = identity
        self.inspection = inspection
        self.context = None
        self.reference_advisory.clear()
        if inspection is None:
            self.source_label.setText("Inspect a dataset source first.")
            self.status.setText("Manual plotting is available for inspected datasets only.")
            self._update_actions()
            return

        self.source_label.setText(str(inspection.get("source", "Unknown source")))
        source_kind = str(inspection.get("source_kind", "unknown"))
        if source_kind != "dataset":
            self.status.setText(
                f"Manual plotting is unavailable for {source_kind} bundles in GUI-1. "
                "Inspect a dataset run, CSV, or Parquet source instead."
            )
            self._update_actions()
            return
        context = inspection.get("plot_context")
        if not isinstance(context, dict):
            self.status.setText("The dataset inspection did not provide plot controls.")
            self._update_actions()
            return
        visualization = context.get("visualization")
        kinds = visualization.get("plot_kinds") if isinstance(visualization, dict) else None
        if not isinstance(kinds, list) or not kinds:
            self.status.setText("This dataset has no compatible plot kinds.")
            self._update_actions()
            return
        self.context = context
        summary = inspection.get("summary")
        source_summary = summary.get("source") if isinstance(summary, dict) else None
        integrity = (
            source_summary.get("integrity") if isinstance(source_summary, dict) else "unknown"
        )
        self.status.setText(
            f"Dataset inspection is ready ({integrity} integrity). "
            f"Compatible kinds: {', '.join(str(kind) for kind in kinds)}."
        )
        self._set_reference_advisory(context)
        self._update_actions()

    def edit_request(self) -> None:
        context = self.context
        if context is None or self.client.is_busy:
            return
        dialog = PlotRequestDialog(
            context,
            context,
            copy.deepcopy(self.request),
            self,
            allow_format=False,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.request = dialog.plot_payload()
        self.request_summary.setPlainText(
            json.dumps(self.request, indent=2, sort_keys=True, ensure_ascii=False)
        )
        self._clear_render_result()
        self.request_changed.emit(copy.deepcopy(self.request))
        self._update_actions()

    def render_plot(self) -> None:
        workspace = self.workspace
        source = self.source_path
        inspection = self.inspection
        request = self.request
        if (
            workspace is None
            or source is None
            or inspection is None
            or request is None
            or self.client.is_busy
        ):
            return
        revision = inspection.get("revision")
        plot_name = request.get("name")
        if not isinstance(revision, str) or not isinstance(plot_name, str):
            self.phase_label.setText("Render unavailable: inspection or plot name is invalid.")
            return

        self._clear_render_result()
        self.phase_label.setText("Starting plot worker…")
        payload: dict[str, object] = {
            "workspace_path": str(workspace.root),
            "source_path": str(source),
            "inspection_revision": revision,
            "plot_name": plot_name,
            "format": self.format_selector.currentText(),
            "plot": copy.deepcopy(request),
        }
        try:
            self._request_id = self.client.start_request("render_plot", payload)
        except Exception as exc:  # pragma: no cover - defensive Qt process boundary
            self.phase_label.setText("Failed to start plot render")
            self.result_summary.setPlainText(str(exc))
            self._update_actions()
            return
        self.force_stop_button.setVisible(True)
        self.force_stop_button.setEnabled(True)
        self._update_actions()

    def force_stop(self, *, confirm: bool = True) -> bool:
        if not self.owns_active_request or not self.client.is_busy:
            return False
        if confirm and not self._confirm_force_stop():
            return False
        stopped = self.client.force_stop()
        if stopped:
            self.force_stop_button.setEnabled(False)
            self.phase_label.setText("Force-stopping plot worker…")
        return stopped

    def _confirm_force_stop(self) -> bool:
        answer = QMessageBox.warning(
            self,
            "Force Stop Plot Rendering",
            "Force-stop the plot worker? The current render will be interrupted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _event_received(self, value: object) -> None:
        event = cast(WorkerEvent, value)
        if event.request_id != self._request_id:
            return
        if event.type == "phase":
            self.phase_label.setText(f"Phase: {event.payload.get('name', 'unknown')}")
        elif event.type in {"result", "error", "cancelled"}:
            self.force_stop_button.setEnabled(False)

    def _request_finished(self, value: object) -> None:
        envelope = cast(dict[str, object], value)
        if str(envelope.get("request_id")) != str(self._request_id):
            return
        cleanup_error = envelope.get("cleanup_error")
        self._cleanup_error = cleanup_error if isinstance(cleanup_error, str) else None
        self.render_finished.emit(envelope)

    def _request_succeeded(self, value: object) -> None:
        if self._request_id is None:
            return
        payload = cast(dict[str, Any], value)
        advisories = payload.get("advisories")
        advisory_lines = _advisory_lines(advisories)
        cleanup = self._cleanup_error
        status = "Completed with cleanup warning" if cleanup else "Completed"
        self.phase_label.setText(status)
        lines = [
            f"Image: {payload.get('image_path')}",
            f"Sidecar: {payload.get('sidecar_path')}",
            f"Source integrity: {payload.get('source_integrity')}",
            f"Rows plotted: {payload.get('valid_rows_plotted')}",
            f"Invalid rows excluded: {payload.get('invalid_rows_excluded')}",
        ]
        if advisory_lines:
            lines.extend(["Advisories:", *advisory_lines])
        if cleanup:
            lines.append(f"Cleanup warning: {cleanup}")
        self.result_summary.setPlainText("\n".join(lines))
        normalized = payload.get("normalized_request")
        image_path = payload.get("image_path")
        source = payload.get("source")
        if isinstance(normalized, dict) and isinstance(image_path, str) and isinstance(source, str):
            self.command.setPlainText(
                _equivalent_plot_command(Path(source), normalized, Path(image_path))
            )
        self._finish_request()

    def _request_failed(self, value: object) -> None:
        if self._request_id is None:
            return
        payload = cast(dict[str, Any], value)
        code = str(payload.get("code", "execution_failed"))
        message = str(payload.get("message", "plot rendering failed"))
        cleanup = self._cleanup_error
        if code == "force_stopped" and cleanup:
            self.phase_label.setText("Force-stopped; cleanup failed")
        elif code == "force_stopped":
            self.phase_label.setText("Force-stopped")
        else:
            self.phase_label.setText("Render failed")
        details = f"{code}: {message}"
        if cleanup:
            details += f"\nCleanup error: {cleanup}"
        self.result_summary.setPlainText(details)
        self._finish_request()

    def _finish_request(self) -> None:
        self._request_id = None
        self.force_stop_button.setVisible(False)
        self.force_stop_button.setEnabled(False)
        self._update_actions()

    def _busy_changed(self, _busy: bool) -> None:
        self._update_actions()

    def _render_inputs_changed(self, _value: str) -> None:
        if not self.owns_active_request:
            self._clear_render_result()
        self._update_actions()

    def _clear_render_result(self) -> None:
        self._cleanup_error = None
        self.command.clear()
        self.result_summary.clear()
        if not self.owns_active_request:
            self.phase_label.setText("Idle")

    def _update_actions(self) -> None:
        editable = self.context is not None
        renderable = self.workspace is not None and editable
        idle = not self.client.is_busy
        self.edit_button.setEnabled(editable and idle)
        self.format_selector.setEnabled(idle)
        self.render_button.setEnabled(renderable and self.request is not None and idle)

    def _set_reference_advisory(self, context: dict[str, Any]) -> None:
        reference = context.get("reference_state")
        if not isinstance(reference, dict):
            return
        properties = reference.get("reference_dependent_properties")
        if not isinstance(properties, list) or not properties:
            return
        policy = reference.get("reference_state_policy") or "unreported"
        self.reference_advisory.setText(
            "Reference-state-dependent fields are available: "
            f"{', '.join(str(value) for value in properties)}. Policy: {policy}."
        )


def _advisory_lines(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    lines: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", "advisory"))
        message = str(item.get("message", ""))
        lines.append(f"- {code}: {message}" if message else f"- {code}")
    return lines


def _equivalent_plot_command(
    source: Path,
    request: dict[str, object],
    output: Path,
) -> str:
    kind = str(request.get("kind", "")).replace("_", "-")
    parts = ["carnopy", "plot", str(source), "--kind", kind]
    scalar_options = (
        ("property_name", "--property"),
        ("x_field", "--x"),
        ("y_field", "--y"),
        ("group_by", "--group-by"),
        ("saturation_coordinate", "--saturation-coordinate"),
    )
    for field, option in scalar_options:
        value = request.get(field)
        if value is not None:
            parts.extend([option, str(value)])
    fluids = request.get("fluids")
    if isinstance(fluids, list):
        for fluid in fluids:
            parts.extend(["--fluid", str(fluid)])
    filters = request.get("filters")
    if isinstance(filters, list):
        for item in filters:
            if isinstance(item, dict) and "field" in item and "value" in item:
                parts.extend(["--filter", f"{item['field']}={_cli_scalar(item['value'])}"])
    series = request.get("series")
    if isinstance(series, list):
        for item in series:
            values = item.get("values") if isinstance(item, dict) else None
            if not isinstance(values, list) or "field" not in item:
                continue
            for value in values:
                parts.extend(["--series", f"{item['field']}={_cli_scalar(value)}"])
    display_units = request.get("display_units")
    if isinstance(display_units, list):
        for item in display_units:
            if isinstance(item, dict) and "field" in item and "unit" in item:
                parts.extend(["--display-unit", f"{item['field']}={item['unit']}"])
    for field, option in (
        ("value_scale", "--value-scale"),
        ("color_scale", "--color-scale"),
        ("x_scale", "--x-scale"),
        ("y_scale", "--y-scale"),
    ):
        value = request.get(field)
        if value not in {None, "linear"}:
            parts.extend([option, str(value)])
    parts.extend(["--output", str(output)])
    return shlex.join(parts)


def _cli_scalar(value: object) -> str:
    return format(value, ".15g") if isinstance(value, float) else str(value)
