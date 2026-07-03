from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from carnopy.app.client import WorkerClient
from carnopy.app.plot_request_dialog import PlotRequestDialog
from carnopy.app.workspace import Workspace


class PlotPage(QWidget):
    request_changed = Signal(object)

    def __init__(self, client: WorkerClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.client = client
        self.workspace: Workspace | None = None
        self.inspection: dict[str, Any] | None = None
        self.context: dict[str, Any] | None = None
        self.request: dict[str, Any] | None = None
        self._source_identity: tuple[str, str] | None = None

        layout = QVBoxLayout(self)
        heading = QLabel("Plot")
        heading.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(heading)
        self.source_label = QLabel("Inspect a dataset source first.")
        self.source_label.setWordWrap(True)
        layout.addWidget(self.source_label)
        self.status = QLabel("Manual plotting is available for inspected datasets only.")
        self.status.setWordWrap(True)
        self.status.setAccessibleName("Plot status")
        layout.addWidget(self.status)
        self.reference_advisory = QLabel()
        self.reference_advisory.setWordWrap(True)
        self.reference_advisory.setAccessibleName("Plot reference-state advisory")
        layout.addWidget(self.reference_advisory)
        self.edit_button = QPushButton("Edit Plot Request…")
        self.edit_button.clicked.connect(self.edit_request)
        self.edit_button.setEnabled(False)
        layout.addWidget(self.edit_button)
        layout.addWidget(QLabel("Session plot request"))
        self.request_summary = QPlainTextEdit()
        self.request_summary.setReadOnly(True)
        self.request_summary.setAccessibleName("Plot request summary")
        layout.addWidget(self.request_summary, 1)
        layout.addWidget(QLabel("Plot rendering and image preview are added in the next stage."))

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
            self.request_changed.emit(None)
        self._source_identity = identity
        self.inspection = inspection
        self.context = None
        self.edit_button.setEnabled(False)
        self.reference_advisory.clear()
        if inspection is None:
            self.source_label.setText("Inspect a dataset source first.")
            self.status.setText("Manual plotting is available for inspected datasets only.")
            return

        self.source_label.setText(str(inspection.get("source", "Unknown source")))
        source_kind = str(inspection.get("source_kind", "unknown"))
        if source_kind != "dataset":
            self.status.setText(
                f"Manual plotting is unavailable for {source_kind} bundles in GUI-1. "
                "Inspect a dataset run, CSV, or Parquet source instead."
            )
            return
        context = inspection.get("plot_context")
        if not isinstance(context, dict):
            self.status.setText("The dataset inspection did not provide plot controls.")
            return
        visualization = context.get("visualization")
        kinds = visualization.get("plot_kinds") if isinstance(visualization, dict) else None
        if not isinstance(kinds, list) or not kinds:
            self.status.setText("This dataset has no compatible plot kinds.")
            return
        self.context = context
        self.edit_button.setEnabled(True)
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

    def edit_request(self) -> None:
        context = self.context
        if context is None:
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
        self.request_changed.emit(copy.deepcopy(self.request))

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
