from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit

from carnopy.app.client import WorkerClient
from carnopy.app.plot_page import PlotPage, _equivalent_plot_command
from carnopy.app.plot_request_dialog import PlotRequestDialog
from carnopy.app.protocol import WorkerEvent
from carnopy.app.source_inspection import inspect_for_app
from carnopy.provenance import sha256_file


class StubClient(QObject):
    event_received = Signal(object)
    request_succeeded = Signal(object)
    request_failed = Signal(object)
    request_finished = Signal(object)
    busy_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.is_busy = False
        self.started: list[tuple[str, dict[str, object]]] = []
        self.active_id: UUID | None = None
        self.stopped = False

    def start_request(self, kind: str, payload: dict[str, object]) -> UUID:
        self.started.append((kind, payload))
        self.active_id = uuid4()
        self.is_busy = True
        self.busy_changed.emit(True)
        return self.active_id

    def force_stop(self) -> bool:
        self.stopped = True
        return True

    def finish(
        self,
        payload: dict[str, object],
        *,
        cleanup_error: str | None = None,
    ) -> None:
        assert self.active_id is not None
        request_id = self.active_id
        self.is_busy = False
        self.busy_changed.emit(False)
        self.request_finished.emit(
            {
                "request_id": str(request_id),
                "request_type": "render_plot",
                "cleanup_error": cleanup_error,
            }
        )
        self.request_succeeded.emit(payload)

    def fail(
        self,
        payload: dict[str, object],
        *,
        cleanup_error: str | None = None,
    ) -> None:
        assert self.active_id is not None
        request_id = self.active_id
        self.is_busy = False
        self.busy_changed.emit(False)
        self.request_finished.emit(
            {
                "request_id": str(request_id),
                "request_type": "render_plot",
                "cleanup_error": cleanup_error,
            }
        )
        self.request_failed.emit(payload)


@pytest.fixture(scope="module")
def application() -> QApplication:
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    yield app


def _dataset(path: Path, *, temperature_count: int = 2) -> Path:
    temperatures = [280.0 + index for index in range(temperature_count)]
    rows = [
        (temperature, pressure)
        for pressure in (100_000.0, 200_000.0)
        for temperature in temperatures
    ]
    pd.DataFrame(
        {
            "run_id": ["run"] * len(rows),
            "case_id": list(range(len(rows))),
            "mode": ["property_table"] * len(rows),
            "fluid": ["Propane"] * len(rows),
            "backend": ["coolprop"] * len(rows),
            "backend_model": ["heos"] * len(rows),
            "backend_version": ["test"] * len(rows),
            "phase": ["gas"] * len(rows),
            "valid": [True] * len(rows),
            "temperature_K": [temperature for temperature, _pressure in rows],
            "pressure_Pa": [pressure for _temperature, pressure in rows],
            "mass_density_kg_m3": [1.0 + index / 1000 for index in range(len(rows))],
        }
    ).to_parquet(path, index=False)
    (path.parent / "metadata.json").write_text(
        json.dumps(
            {
                "original_units": {"temperature": "K", "pressure": "bar"},
                "reference_state_policy": "CoolProp DEF",
                "artifact_hashes": {path.name: sha256_file(path)},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_dataset_inspection_builds_backend_free_plot_context(tmp_path: Path) -> None:
    inspected = inspect_for_app(_dataset(tmp_path / "dataset.parquet"))
    context = inspected.plot_context

    assert context is not None
    visualization = context["visualization"]
    assert visualization["plot_kinds"] == [
        "property_curves",
        "property_heatmap",
        "xy",
        "pv",
    ]
    pressure = visualization["numeric_levels"]["pressure"]
    assert pressure["display_unit"] == "bar"
    assert pressure["choices"] == [
        {"label": "1 bar", "value": 100_000.0},
        {"label": "2 bar", "value": 200_000.0},
    ]
    assert visualization["categorical_values"]["phase"] == ["gas"]


def test_manual_plot_dialog_displays_engineering_levels_and_returns_si(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    context = inspect_for_app(_dataset(tmp_path / "dataset.parquet")).plot_context
    assert context is not None
    dialog = PlotRequestDialog(
        context,
        context,
        {
            "name": "density-curves",
            "kind": "property_curves",
            "property": "mass_density",
            "x": "temperature",
        },
        allow_format=False,
    )
    dialog.series.add_row("pressure", "1 bar, 2 bar")
    value_editor = dialog.series.table.cellWidget(0, 1)
    assert isinstance(value_editor, QLineEdit)
    assert value_editor.completer() is not None

    payload = dialog.plot_payload()

    assert payload["series"] == {"pressure": [100_000.0, 200_000.0]}
    assert "format" not in payload
    dialog.filters.add_row("pressure", "100000")
    filter_editor = dialog.filters.table.cellWidget(0, 1)
    assert isinstance(filter_editor, QComboBox)
    assert [filter_editor.itemText(index) for index in range(filter_editor.count())] == [
        "1 bar",
        "2 bar",
    ]
    assert dialog.plot_payload()["filters"] == {"pressure": 100_000.0}
    dialog.close()


def test_large_numeric_level_sets_use_exact_si_input(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    context = inspect_for_app(
        _dataset(tmp_path / "dataset.parquet", temperature_count=501)
    ).plot_context
    assert context is not None
    temperature = context["visualization"]["numeric_levels"]["temperature"]
    assert temperature["count"] == 501
    assert temperature["choices"] == []

    dialog = PlotRequestDialog(
        context,
        context,
        {
            "name": "density-curves",
            "kind": "property_curves",
            "property": "mass_density",
            "x": "pressure",
        },
        allow_format=False,
    )
    dialog.series.add_row("temperature", "300")
    editor = dialog.series.table.cellWidget(0, 1)
    assert isinstance(editor, QLineEdit)
    assert "501 emitted level" in editor.placeholderText()
    assert dialog.plot_payload()["series"] == {"temperature": [300.0]}
    editor.setText("300K")
    with pytest.raises(ValueError, match="numeric field requires a number"):
        dialog.plot_payload()
    dialog.close()


def test_plot_page_clears_session_request_when_source_changes(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    client = WorkerClient()
    page = PlotPage(client)
    first = inspect_for_app(_dataset(tmp_path / "first.parquet")).public_payload()
    second = inspect_for_app(_dataset(tmp_path / "second.parquet")).public_payload()

    page.set_inspection(first)
    page.request = {"name": "density", "kind": "pv"}
    page.request_summary.setPlainText("saved in session")
    page.set_inspection(first)
    assert page.request == {"name": "density", "kind": "pv"}

    page.set_inspection(second)
    assert page.request is None
    assert page.request_summary.toPlainText() == ""
    assert page.edit_button.isEnabled()

    page.set_inspection(
        {
            "source": str(tmp_path / "sweep"),
            "source_kind": "model_sweep",
            "revision": "a" * 64,
            "plot_context": None,
        }
    )
    assert not page.edit_button.isEnabled()
    assert "unavailable" in page.status.text()
    page.close()
    client.shutdown()


def test_plot_page_renders_owned_request_and_reports_result(
    tmp_path: Path,
    application: QApplication,
) -> None:
    from carnopy.app.workspace import initialize_workspace

    workspace = initialize_workspace(tmp_path / "workspace")
    dataset = _dataset(tmp_path / "My Dataset.parquet")
    inspection = inspect_for_app(dataset).public_payload()
    stub = StubClient()
    page = PlotPage(cast(WorkerClient, stub))
    page.set_workspace(workspace)
    page.set_inspection(inspection)
    page.request = {
        "name": "density-curves",
        "kind": "property_curves",
        "property": "mass_density",
        "x": "temperature",
    }
    page.request_summary.setPlainText(json.dumps(page.request))
    page._update_actions()

    page.render_plot()

    assert page.owns_active_request
    assert not page.force_stop_button.isHidden()
    assert stub.started == [
        (
            "render_plot",
            {
                "workspace_path": str(workspace.root),
                "source_path": str(dataset),
                "inspection_revision": inspection["revision"],
                "plot_name": "density-curves",
                "format": "png",
                "plot": page.request,
            },
        )
    ]
    page._event_received(
        WorkerEvent(
            request_id=uuid4(),
            type="phase",
            payload={"name": "foreign-request"},
        )
    )
    assert page.phase_label.text() == "Starting plot worker…"
    image = workspace.figures / "my-dataset" / "density-curves.png"
    image.parent.mkdir()
    rendered = QImage(40, 20, QImage.Format.Format_RGB32)
    rendered.fill(Qt.GlobalColor.cyan)
    assert rendered.save(str(image), "PNG")
    normalized = {
        "kind": "property_curves",
        "property_name": "mass_density",
        "x_field": "temperature",
        "filters": [],
        "series": [],
        "display_units": [],
        "fluids": ["Propane"],
        "value_scale": "linear",
        "color_scale": "linear",
        "x_scale": "linear",
        "y_scale": "linear",
    }
    stub.finish(
        {
            "source": str(dataset),
            "image_path": str(image),
            "sidecar_path": str(image.with_suffix(".plot.json")),
            "image_sha256": sha256_file(image),
            "format": "png",
            "source_integrity": "verified",
            "valid_rows_plotted": 4,
            "invalid_rows_excluded": 0,
            "advisories": [{"code": "sparse", "message": "few rows"}],
            "normalized_request": normalized,
        }
    )

    assert not page.owns_active_request
    assert page.phase_label.text() == "Completed"
    assert "Rows plotted: 4" in page.result_summary.toPlainText()
    assert "sparse: few rows" in page.result_summary.toPlainText()
    assert shlex_split(page.command.toPlainText())[-2:] == ["--output", str(image)]
    application.processEvents()
    assert page.preview.has_graphic
    page.close()


def test_plot_page_force_stop_is_immediate_confirmed_and_reports_cleanup_failure(
    tmp_path: Path,
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    from carnopy.app.workspace import initialize_workspace

    workspace = initialize_workspace(tmp_path / "workspace")
    dataset = _dataset(tmp_path / "dataset.parquet")
    stub = StubClient()
    page = PlotPage(cast(WorkerClient, stub))
    page.set_workspace(workspace)
    page.set_inspection(inspect_for_app(dataset).public_payload())
    page.request = {"name": "density", "kind": "pv"}
    page._update_actions()
    page.render_plot()
    monkeypatch.setattr(page, "_confirm_force_stop", lambda: True)

    assert page.force_stop()
    assert stub.stopped

    stub.fail(
        {
            "category": "process",
            "code": "force_stopped",
            "message": "worker process was force-stopped",
        },
        cleanup_error="plot staging cleanup failed: simulated",
    )

    assert page.phase_label.text() == "Force-stopped; cleanup failed"
    assert "simulated" in page.result_summary.toPlainText()
    page.close()


def test_equivalent_plot_command_uses_public_cli_options(tmp_path: Path) -> None:
    source = tmp_path / "dataset with spaces.parquet"
    output = tmp_path / "figure with spaces.png"
    command = _equivalent_plot_command(
        source,
        {
            "kind": "property_curves",
            "property_name": "mass_density",
            "x_field": "temperature",
            "fluids": ["n-Butane"],
            "filters": [{"field": "phase", "value": "gas"}],
            "series": [{"field": "pressure", "values": [100000.0, 200000.0]}],
            "display_units": [{"field": "pressure", "unit": "bar"}],
            "value_scale": "log",
        },
        output,
    )

    assert shlex_split(command) == [
        "carnopy",
        "plot",
        str(source),
        "--kind",
        "property-curves",
        "--property",
        "mass_density",
        "--x",
        "temperature",
        "--fluid",
        "n-Butane",
        "--filter",
        "phase=gas",
        "--series",
        "pressure=100000",
        "--series",
        "pressure=200000",
        "--display-unit",
        "pressure=bar",
        "--value-scale",
        "log",
        "--output",
        str(output),
    ]


def shlex_split(value: str) -> list[str]:
    import shlex

    return shlex.split(value)
