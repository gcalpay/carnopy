from __future__ import annotations

import json
import shlex
from collections.abc import Mapping
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from carnopy.app.plot_draft import PlotDraft
from carnopy.app.plot_preview import PlotPreview, PlotPreviewError
from carnopy.app.plot_request_dialog import PlotRequestDialog
from carnopy.app.session_plot_controller import SessionPlotController


class PlotPage(QWidget):
    """Temporary Widgets adapter over the authoritative session-plot controller."""

    request_changed = Signal(object)
    render_finished = Signal(object)

    def __init__(
        self,
        controller: SessionPlotController,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.coordinator = controller.coordinator

        layout = QVBoxLayout(self)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        controls = QWidget()
        controls_layout = QVBoxLayout(controls)
        layout.addWidget(self.splitter)
        heading = QLabel("Plot")
        heading.setStyleSheet("font-size: 18px; font-weight: bold;")
        controls_layout.addWidget(heading)
        self.source_label = QLabel("Inspect a dataset source first.")
        self.source_label.setWordWrap(True)
        controls_layout.addWidget(self.source_label)
        self.status = QLabel("Manual plotting is available for inspected datasets only.")
        self.status.setWordWrap(True)
        self.status.setAccessibleName("Plot source status")
        controls_layout.addWidget(self.status)
        self.reference_advisory = QLabel()
        self.reference_advisory.setWordWrap(True)
        self.reference_advisory.setAccessibleName("Plot reference-state advisory")
        controls_layout.addWidget(self.reference_advisory)

        actions = QHBoxLayout()
        self.edit_button = QPushButton("Edit Plot Request…")
        self.edit_button.clicked.connect(self.edit_request)
        actions.addWidget(self.edit_button)
        actions.addWidget(QLabel("Format"))
        self.format_selector = QComboBox()
        self.format_selector.addItems(["png", "svg", "pdf"])
        self.format_selector.setAccessibleName("Plot output format")
        self.format_selector.currentTextChanged.connect(self._format_changed)
        actions.addWidget(self.format_selector)
        self.render_button = QPushButton("Render Plot")
        self.render_button.clicked.connect(self.render_plot)
        actions.addWidget(self.render_button)
        self.force_stop_button = QPushButton("Force Stop Render")
        self.force_stop_button.clicked.connect(self.force_stop)
        actions.addWidget(self.force_stop_button)
        actions.addStretch(1)
        controls_layout.addLayout(actions)

        self.phase_label = QLabel("Idle")
        self.phase_label.setAccessibleName("Plot rendering phase")
        controls_layout.addWidget(self.phase_label)
        controls_layout.addWidget(QLabel("Session plot request"))
        self.request_summary = QPlainTextEdit()
        self.request_summary.setReadOnly(True)
        self.request_summary.setAccessibleName("Plot request summary")
        controls_layout.addWidget(self.request_summary, 1)
        controls_layout.addWidget(QLabel("Equivalent CLI command (informational only)"))
        self.command = QPlainTextEdit()
        self.command.setReadOnly(True)
        self.command.setMaximumHeight(85)
        self.command.setAccessibleName("Equivalent plot command")
        controls_layout.addWidget(self.command)
        controls_layout.addWidget(QLabel("Render result"))
        self.result_summary = QPlainTextEdit()
        self.result_summary.setReadOnly(True)
        self.result_summary.setMaximumHeight(150)
        self.result_summary.setAccessibleName("Plot render result")
        controls_layout.addWidget(self.result_summary)

        self.preview = PlotPreview()
        self.splitter.addWidget(controls)
        self.splitter.addWidget(self.preview)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)

        controller.state_changed.connect(self._refresh)
        controller.active_edit_changed.connect(self._refresh)
        controller.render_finished.connect(self.render_finished)
        self._refresh()

    @property
    def owns_active_request(self) -> bool:
        return self.controller.get_is_rendering()

    @property
    def source_path(self) -> Path | None:
        value = self.controller.get_source_path()
        return Path(value) if value else None

    @property
    def request(self) -> dict[str, object] | None:
        draft = self.controller.get_active_plot_draft()
        if isinstance(draft, PlotDraft) and draft.get_locally_valid():
            return draft.payload()
        committed = self.controller.get_committed_request()
        return committed or None

    def edit_request(self) -> None:
        if self.controller.get_active_plot_draft() is None and not self.controller.begin_edit(
            self.format_selector.currentText()
        ):
            return
        draft = self.controller.get_active_plot_draft()
        if not isinstance(draft, PlotDraft):
            return
        dialog = PlotRequestDialog(draft, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.controller.cancel_edit()
            return
        self.request_changed.emit(self.request)
        self._refresh()

    def render_plot(self) -> None:
        self.controller.render()

    def force_stop(self, *, confirm: bool = True) -> bool:
        if confirm:
            answer = QMessageBox.warning(
                self,
                "Force Stop Plot Rendering",
                "Force-stop the plot worker? The current render will be interrupted.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
        return self.controller.force_stop()

    def _format_changed(self, value: str) -> None:
        draft = self.controller.get_active_plot_draft()
        if isinstance(draft, PlotDraft):
            draft.set_output_format(value)

    def _refresh(self) -> None:
        source = self.controller.get_source_path()
        self.source_label.setText(source or "Inspect a dataset source first.")
        payload = self.controller.inspection.current_payload()
        self.reference_advisory.clear()
        if source and isinstance(payload, dict):
            summary = payload.get("summary")
            source_summary = summary.get("source") if isinstance(summary, Mapping) else None
            integrity = (
                source_summary.get("integrity")
                if isinstance(source_summary, Mapping)
                else "unknown"
            )
            context = payload.get("plot_context")
            visualization = context.get("visualization") if isinstance(context, Mapping) else None
            kinds = visualization.get("plot_kinds") if isinstance(visualization, Mapping) else None
            compatible = (
                ", ".join(str(kind) for kind in kinds) if isinstance(kinds, list) else "unreported"
            )
            self.status.setText(
                self.controller.get_issue()
                or f"Dataset inspection is ready ({integrity} integrity). "
                f"Compatible kinds: {compatible}."
            )
            if isinstance(context, Mapping):
                self._set_reference_advisory(context)
        else:
            self.status.setText(
                self.controller.get_issue()
                or "Manual plotting is available for inspected datasets only."
            )
        self.phase_label.setText(self.controller.get_phase() or "Idle")
        request = self.request
        self.request_summary.setPlainText(
            "" if request is None else json.dumps(request, indent=2, sort_keys=True)
        )
        self._refresh_result()
        self.edit_button.setEnabled(self.controller.get_can_begin_edit())
        self.format_selector.setEnabled(not self.controller.get_is_rendering())
        self.render_button.setEnabled(self.controller.get_can_render())
        self.force_stop_button.setVisible(self.controller.get_can_force_stop())
        self.force_stop_button.setEnabled(self.controller.get_can_force_stop())

    def _refresh_result(self) -> None:
        result = self.controller.committed_result_payload()
        if result is None:
            if not self.controller.get_is_rendering():
                self.preview.clear()
                self.command.clear()
                self.result_summary.clear()
            return
        lines = [
            f"Image: {result.get('image_path')}",
            f"Sidecar: {result.get('sidecar_path')}",
            f"Source integrity: {result.get('source_integrity')}",
            f"Rows plotted: {result.get('valid_rows_plotted')}",
            f"Invalid rows excluded: {result.get('invalid_rows_excluded')}",
        ]
        if self.controller.get_issue():
            lines.append(f"{self.controller.get_issue_code()}: {self.controller.get_issue()}")
        self.result_summary.setPlainText("\n".join(lines))
        workspace = self.controller.workspace
        image_path = result.get("image_path")
        image_format = result.get("format")
        image_sha256 = result.get("image_sha256")
        if (
            workspace is not None
            and isinstance(image_path, str)
            and isinstance(image_format, str)
            and isinstance(image_sha256, str)
            and self.preview.image_path != Path(image_path)
        ):
            try:
                self.preview.load_export(
                    workspace.figures,
                    Path(image_path),
                    image_format,
                    image_sha256,
                )
            except PlotPreviewError as exc:
                lines.append(f"Preview unavailable: {exc}")
                self.result_summary.setPlainText("\n".join(lines))
        normalized = result.get("normalized_request")
        source = result.get("source")
        if isinstance(normalized, dict) and isinstance(source, str) and isinstance(image_path, str):
            self.command.setPlainText(
                _equivalent_plot_command(Path(source), normalized, Path(image_path))
            )

    def _set_reference_advisory(self, context: Mapping[str, object]) -> None:
        reference = context.get("reference_state")
        if not isinstance(reference, Mapping):
            return
        properties = reference.get("reference_dependent_properties")
        if not isinstance(properties, list) or not properties:
            return
        policy = reference.get("reference_state_policy") or "unreported"
        self.reference_advisory.setText(
            "Reference-state-dependent fields are available: "
            f"{', '.join(str(value) for value in properties)}. Policy: {policy}."
        )


def _equivalent_plot_command(
    source: Path,
    request: dict[str, object],
    output: Path,
) -> str:
    kind = str(request.get("kind", "")).replace("_", "-")
    parts = ["carnopy", "plot", str(source), "--kind", kind]
    for field, option in (
        ("property_name", "--property"),
        ("x_field", "--x"),
        ("y_field", "--y"),
        ("group_by", "--group-by"),
        ("saturation_coordinate", "--saturation-coordinate"),
    ):
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
