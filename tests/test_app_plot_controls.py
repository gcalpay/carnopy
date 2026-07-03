from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit

from carnopy.app.client import WorkerClient
from carnopy.app.plot_page import PlotPage
from carnopy.app.plot_request_dialog import PlotRequestDialog
from carnopy.app.source_inspection import inspect_for_app
from carnopy.provenance import sha256_file


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
