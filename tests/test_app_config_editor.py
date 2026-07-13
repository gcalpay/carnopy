from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QLineEdit,
    QListView,
    QMessageBox,
)

from carnopy.app.config_document import ConfigDocumentError, new_document
from carnopy.app.config_editor import DatasetConfigEditor
from carnopy.app.config_widgets import SamplerEditor
from carnopy.app.draft_models import DISPLAY_ROLE
from carnopy.app.plot_draft import PlotDraft
from carnopy.app.sampler_draft import SamplerDraft
from carnopy.app.visualization_editor import PlotRequestDialog, VisualizationEditor
from carnopy.app.workspace import initialize_workspace
from carnopy.domain.properties import PROPERTY_REGISTRY
from carnopy.templates import template_text


@pytest.fixture(scope="module")
def application() -> QApplication:
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    yield app


def capabilities() -> dict[str, Any]:
    cubic_unsupported = {
        "dynamic_viscosity",
        "kinematic_viscosity",
        "thermal_conductivity",
        "prandtl_number",
        "surface_tension",
        "triple_point_temperature",
    }
    properties = []
    for name, definition in PROPERTY_REGISTRY.items():
        metadata = definition.metadata()
        metadata["supported_models"] = ["heos"]
        if name not in cubic_unsupported:
            metadata["supported_models"].extend(["pr", "srk"])
        properties.append(metadata)
    field_definitions = [
        {
            "name": "temperature",
            "kind": "numeric",
            "axis_allowed": True,
            "group_allowed": True,
            "filter_allowed": True,
        },
        {
            "name": "pressure",
            "kind": "numeric",
            "axis_allowed": True,
            "group_allowed": True,
            "filter_allowed": True,
        },
        {
            "name": "vapor_mass_fraction",
            "kind": "numeric",
            "axis_allowed": True,
            "group_allowed": True,
            "filter_allowed": True,
        },
        {
            "name": "phase",
            "kind": "categorical",
            "axis_allowed": False,
            "group_allowed": True,
            "filter_allowed": True,
        },
        {
            "name": "saturation_endpoint",
            "kind": "categorical",
            "axis_allowed": False,
            "group_allowed": True,
            "filter_allowed": True,
        },
        {
            "name": "fluid",
            "kind": "categorical",
            "axis_allowed": False,
            "group_allowed": False,
            "filter_allowed": False,
        },
        {
            "name": "specific_volume",
            "kind": "numeric",
            "axis_allowed": True,
            "group_allowed": False,
            "filter_allowed": False,
        },
        *[
            {
                "name": name,
                "kind": "numeric",
                "axis_allowed": True,
                "group_allowed": False,
                "filter_allowed": False,
            }
            for name in PROPERTY_REGISTRY
        ],
    ]
    return {
        "model": "heos",
        "models": ["heos", "pr", "srk"],
        "modes": [
            "property_table",
            "saturation_table",
            "vapor_mass_fraction_table",
        ],
        "units_by_axis": {
            "temperature": ["K", "degC"],
            "pressure": ["Pa", "kPa", "MPa", "bar"],
            "vapor_mass_fraction": ["1"],
        },
        "dataset_formats": ["csv", "parquet"],
        "fluids": [
            {"name": "Propane", "aliases": ["R290", "n-Propane"]},
            {"name": "Cyclopentane", "aliases": []},
            {"name": "Isopentane", "aliases": ["IsoPentane"]},
        ],
        "property_catalog": properties,
        "reference_dependent_fields": [
            "specific_enthalpy",
            "specific_entropy",
            "specific_internal_energy",
        ],
        "visualization": {
            "plot_kinds": ["property_curves", "property_heatmap", "xy", "pv", "ts"],
            "formats": ["png", "pdf", "svg"],
            "scales": ["linear", "log"],
            "kind_contracts": {
                "property_curves": {
                    "required": ["property"],
                    "applicable": [
                        "property",
                        "x",
                        "filters",
                        "series",
                        "display_units",
                        "fluids",
                        "value_scale",
                        "format",
                    ],
                },
                "property_heatmap": {
                    "required": ["property"],
                    "applicable": [
                        "property",
                        "filters",
                        "display_units",
                        "fluids",
                        "color_scale",
                        "format",
                    ],
                },
                "xy": {
                    "required": ["x", "y"],
                    "applicable": [
                        "x",
                        "y",
                        "group_by",
                        "filters",
                        "series",
                        "display_units",
                        "fluids",
                        "x_scale",
                        "y_scale",
                        "format",
                    ],
                },
                "pv": {
                    "required": [],
                    "applicable": [
                        "filters",
                        "series",
                        "display_units",
                        "fluids",
                        "x_scale",
                        "y_scale",
                        "format",
                    ],
                },
                "ts": {
                    "required": [],
                    "applicable": [
                        "filters",
                        "series",
                        "display_units",
                        "fluids",
                        "x_scale",
                        "y_scale",
                        "format",
                    ],
                },
            },
            "fields": field_definitions,
            "display_units": {
                "temperature": ["K", "degC"],
                "pressure": ["Pa", "kPa", "MPa", "bar"],
                "specific_enthalpy": ["J/kg", "kJ/kg"],
                "specific_entropy": ["J/(kg*K)", "kJ/(kg*K)"],
            },
            "categorical_values": {
                "phase": ["gas", "liquid", "two_phase"],
                "saturation_endpoint": ["saturated_liquid", "saturated_vapor"],
            },
        },
    }


def configured_editor(tmp_path: Path) -> DatasetConfigEditor:
    editor = DatasetConfigEditor()
    editor.controller.workspace = initialize_workspace(tmp_path / "workspace")
    editor._apply_capabilities(capabilities())
    return editor


@pytest.mark.parametrize(
    "sampler",
    [
        {"kind": "explicit", "values": [2.0, 1.0], "unit": "bar"},
        {"kind": "linspace", "start": 1.0, "stop": 5.0, "num": 5, "unit": "bar"},
        {"kind": "stepspace", "start": 1.0, "stop": 5.0, "step": 1.0, "unit": "bar"},
        {"kind": "geomspace", "start": 1.0, "stop": 5.0, "num": 5, "unit": "bar"},
        {
            "kind": "logspace",
            "start_exp": 0.0,
            "stop_exp": 2.0,
            "num": 5,
            "base": 10.0,
            "unit": "bar",
        },
    ],
)
def test_sampler_editor_round_trips_every_public_sampler(
    sampler: dict[str, object],
    application: QApplication,
) -> None:
    del application
    draft = SamplerDraft("pressure")
    draft.load_payload(sampler, available_units=["Pa", "bar"])
    editor = SamplerEditor(draft)

    assert editor.sampler_payload() == sampler


@pytest.mark.parametrize(
    "mode",
    ["property_table", "saturation_table", "vapor_mass_fraction_table"],
)
def test_all_dataset_templates_populate_deterministic_valid_previews(
    tmp_path: Path,
    application: QApplication,
    mode: str,
) -> None:
    del application
    editor = configured_editor(tmp_path)
    payload = yaml.safe_load(template_text(mode))

    editor._open_document(new_document(payload))

    assert editor._form_valid
    assert yaml.safe_load(editor.preview.toPlainText())["mode"] == mode
    assert yaml.safe_load(editor.preview.toPlainText())["fluids"] == payload["fluids"]
    assert editor.save_button.isEnabled()
    editor.shutdown()


def test_dataset_form_binds_directly_to_controller_models(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    editor = configured_editor(tmp_path)
    editor._open_document(new_document(yaml.safe_load(template_text("property_table"))))

    assert isinstance(editor.form.fluids, QListView)
    assert editor.form.fluids.model() is editor.dataset_draft.selected_fluids
    assert editor.form.properties.model() is editor.dataset_draft.selected_properties
    assert editor.form.property_input.model() is editor.dataset_draft.property_choices
    assert editor.form.model.model() is editor.dataset_draft.model_choices
    assert editor.visualization.draft is editor.visualization_draft
    assert editor.visualization.format.model() is editor.visualization_draft.format_choices
    assert editor.visualization.plots.model() is editor.visualization_draft.plot_model
    assert editor.visualization.filters._draft is editor.visualization_draft.filters
    assert editor.visualization.display_units._draft is editor.visualization_draft.display_units
    editor.shutdown()


def test_invalid_visualization_blocks_save_and_requires_discard(
    tmp_path: Path,
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    editor = configured_editor(tmp_path)
    editor._open_document(new_document(yaml.safe_load(template_text("property_table"))))
    questions: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: questions.append("asked") or QMessageBox.StandardButton.Cancel,
    )

    editor.visualization_draft.set_enabled(True)

    assert editor.visualization_draft.get_dirty()
    assert not editor.visualization_draft.get_locally_valid()
    assert not editor._form_valid
    assert not editor.save_button.isEnabled()
    with pytest.raises(ConfigDocumentError, match="complete the configuration form"):
        editor.execution_snapshot()
    assert not editor.confirm_discard()
    assert questions == ["asked"]
    editor.shutdown()


def test_incomplete_saved_dataset_draft_is_dirty_and_requires_discard(
    tmp_path: Path,
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    editor = configured_editor(tmp_path)
    editor._open_document(new_document(yaml.safe_load(template_text("property_table"))))
    assert editor.document is not None
    saved = editor.workspace.configs / "saved.yaml"
    editor.document.mark_saved(saved, editor.document.yaml_bytes)
    editor.dataset_draft.mark_baseline()
    temperature = editor.dataset_draft.sampler("temperature")
    assert temperature is not None
    questions: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: questions.append("asked") or QMessageBox.StandardButton.Cancel,
    )

    temperature.set_text("start", "")

    assert editor.dataset_draft.get_dirty()
    assert not editor._form_valid
    assert not editor.save_button.isEnabled()
    assert "unavailable" in editor.preview.toPlainText()
    assert not editor.confirm_discard()
    assert questions == ["asked"]
    editor.shutdown()


def test_cancelled_mode_change_restores_display_without_mutating_draft(
    tmp_path: Path,
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    editor = configured_editor(tmp_path)
    editor._open_document(new_document(yaml.safe_load(template_text("property_table"))))
    original = editor.document.payload if editor.document is not None else {}
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.No,
    )

    editor.form.mode.setCurrentText("saturation_table")

    assert editor.dataset_draft.get_mode_name() == "property_table"
    assert editor.form.mode.currentText() == "property_table"
    assert editor.document is not None
    assert editor.document.payload == original
    editor.shutdown()


def test_visualization_editor_round_trips_all_plot_kinds_and_fields(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    editor = configured_editor(tmp_path)
    payload = yaml.safe_load(template_text("property_table"))
    payload["visualization"] = {
        "format": "svg",
        "fluids": ["Propane"],
        "filters": {"phase": "gas"},
        "display_units": {"pressure": "bar"},
        "plots": [
            {
                "name": "density-curves",
                "kind": "property_curves",
                "property": "mass_density",
                "x": "temperature",
                "filters": {"pressure": 100000.0},
                "series": {"pressure": [100000.0, 300000.0]},
                "display_units": {"temperature": "degC"},
                "fluids": ["Propane"],
                "value_scale": "log",
                "format": "pdf",
            },
            {
                "name": "density-map",
                "kind": "property_heatmap",
                "property": "mass_density",
                "color_scale": "log",
            },
            {
                "name": "enthalpy-entropy",
                "kind": "xy",
                "x": "specific_enthalpy",
                "y": "specific_entropy",
                "group_by": "pressure",
                "x_scale": "log",
                "y_scale": "linear",
            },
            {
                "name": "pressure-volume",
                "kind": "pv",
                "series": {"temperature": [293.15, 313.15]},
                "x_scale": "log",
                "y_scale": "log",
            },
            {
                "name": "temperature-entropy",
                "kind": "ts",
                "filters": {"phase": "gas"},
                "x_scale": "linear",
                "y_scale": "linear",
            },
        ],
    }

    editor._open_document(new_document(payload))

    rendered = yaml.safe_load(editor.preview.toPlainText())["visualization"]
    assert rendered["format"] == "svg"
    assert rendered["fluids"] == ["Propane"]
    assert rendered["filters"] == {"phase": "gas"}
    assert rendered["display_units"] == {"pressure": "bar"}
    assert [plot["kind"] for plot in rendered["plots"]] == [
        "property_curves",
        "property_heatmap",
        "xy",
        "pv",
        "ts",
    ]
    assert rendered["plots"][0]["series"]["pressure"] == [100000.0, 300000.0]
    assert rendered["plots"][0]["format"] == "pdf"
    assert rendered["plots"][3]["series"]["temperature"] == [293.15, 313.15]
    assert editor._form_valid
    editor.shutdown()


def test_dataset_edit_preserves_complete_visualization_payload(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    editor = configured_editor(tmp_path)
    payload = yaml.safe_load(template_text("property_table"))
    payload["visualization"] = {
        "format": "svg",
        "plots": [{"name": "density", "kind": "pv"}],
    }
    editor._open_document(new_document(payload))

    assert editor.dataset_draft.add_fluid("Cyclopentane")

    rendered = yaml.safe_load(editor.preview.toPlainText())
    assert rendered["visualization"] == payload["visualization"]
    assert rendered["fluids"][-1] == "Cyclopentane"
    editor.shutdown()


@pytest.mark.parametrize(
    ("kind", "plot", "expected_keys"),
    [
        (
            "property_curves",
            {
                "name": "curves",
                "kind": "property_curves",
                "property": "mass_density",
                "x": "temperature",
                "value_scale": "log",
            },
            {"name", "kind", "property", "x", "value_scale"},
        ),
        (
            "property_heatmap",
            {
                "name": "map",
                "kind": "property_heatmap",
                "property": "mass_density",
                "color_scale": "log",
            },
            {"name", "kind", "property", "color_scale"},
        ),
        (
            "xy",
            {
                "name": "xy",
                "kind": "xy",
                "x": "specific_enthalpy",
                "y": "specific_entropy",
                "group_by": "pressure",
            },
            {"name", "kind", "x", "y", "group_by", "x_scale", "y_scale"},
        ),
        (
            "pv",
            {"name": "pv", "kind": "pv", "x_scale": "log"},
            {"name", "kind", "x_scale", "y_scale"},
        ),
        (
            "ts",
            {"name": "ts", "kind": "ts", "y_scale": "log"},
            {"name", "kind", "x_scale", "y_scale"},
        ),
    ],
)
def test_plot_dialog_applies_kind_specific_fields(
    application: QApplication,
    kind: str,
    plot: dict[str, object],
    expected_keys: set[str],
) -> None:
    del application, kind
    dataset = yaml.safe_load(template_text("property_table"))
    dialog = PlotRequestDialog(PlotDraft(capabilities(), dataset, plot))

    result = dialog.plot_payload()

    assert set(result) == expected_keys
    dialog.close()


def test_visualization_editor_offers_guided_shared_choices(
    application: QApplication,
) -> None:
    del application
    dataset = yaml.safe_load(template_text("property_table"))
    editor = VisualizationEditor()
    editor.apply_capabilities(capabilities())
    editor.set_dataset_context(dataset)
    editor.load_visualization(
        {
            "fluids": ["Propane"],
            "filters": {"phase": "gas"},
            "display_units": {"pressure": "bar"},
            "plots": [{"name": "density", "kind": "pv"}],
        }
    )

    assert editor.fluids.selected_values() == ["Propane"]
    filter_field = editor.filters.table.cellWidget(0, 0)
    filter_value = editor.filters.table.cellWidget(0, 1)
    assert isinstance(filter_field, QComboBox)
    assert isinstance(filter_value, QComboBox)
    assert filter_field.currentText() == "phase"
    assert [filter_value.itemText(index) for index in range(filter_value.count())] == [
        "gas",
        "liquid",
        "two_phase",
    ]
    filter_field.setCurrentText("pressure")
    assert isinstance(editor.filters.table.cellWidget(0, 1), QLineEdit)
    filter_field = editor.filters.table.cellWidget(0, 0)
    assert isinstance(filter_field, QComboBox)
    filter_field.setCurrentText("phase")
    reset_filter_value = editor.filters.table.cellWidget(0, 1)
    assert isinstance(reset_filter_value, QComboBox)
    assert reset_filter_value.currentText() == "gas"
    unit_field = editor.display_units.table.cellWidget(0, 0)
    unit_value = editor.display_units.table.cellWidget(0, 1)
    assert isinstance(unit_field, QComboBox)
    assert isinstance(unit_value, QComboBox)
    assert unit_field.currentText() == "pressure"
    assert [unit_value.itemText(index) for index in range(unit_value.count())] == [
        "Pa",
        "kPa",
        "MPa",
        "bar",
    ]
    editor.close()


def test_plot_dialog_guides_series_fields_and_validates_numeric_filters(
    application: QApplication,
) -> None:
    del application
    dataset = yaml.safe_load(template_text("property_table"))
    dialog = PlotRequestDialog(
        PlotDraft(
            capabilities(),
            dataset,
            {
                "name": "density-curves",
                "kind": "property_curves",
                "property": "mass_density",
                "x": "temperature",
            },
        )
    )

    dialog.series.add_row("pressure", "100000, 300000")
    series_field = dialog.series.table.cellWidget(0, 0)
    series_values = dialog.series.table.cellWidget(0, 1)
    assert isinstance(series_field, QComboBox)
    assert isinstance(series_values, QLineEdit)
    assert [series_field.itemText(index) for index in range(series_field.count())] == ["pressure"]
    assert dialog.plot_payload()["series"] == {"pressure": [100000.0, 300000.0]}

    dialog.filters.add_row("pressure", "not-a-number")
    with pytest.raises(ValueError, match="numeric field requires a number"):
        dialog.plot_payload()
    dialog.close()


def test_visualization_requires_unique_names_and_preserves_plot_order(
    application: QApplication,
) -> None:
    del application
    dataset = yaml.safe_load(template_text("property_table"))
    editor = VisualizationEditor()
    editor.apply_capabilities(capabilities())
    editor.set_dataset_context(dataset)
    editor.load_visualization(
        {
            "plots": [
                {"name": "first", "kind": "pv"},
                {"name": "second", "kind": "ts"},
            ]
        }
    )
    editor.plots.setCurrentRow(1)
    editor.move_plot(-1)

    assert [plot["name"] for plot in editor.plot_payloads()] == ["second", "first"]
    editor.load_visualization(
        {
            "plots": [
                {"name": "second", "kind": "ts"},
                {"name": "second", "kind": "pv"},
            ]
        }
    )
    with pytest.raises(ValueError, match="unique"):
        editor.visualization_payload()
    editor.close()


def test_opening_document_replaces_previous_visualization_state(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    editor = configured_editor(tmp_path)
    first = yaml.safe_load(template_text("property_table"))
    first["visualization"] = {
        "plots": [{"name": "old-plot", "kind": "pv"}],
    }
    second = yaml.safe_load(template_text("property_table"))

    editor._open_document(new_document(first))
    assert [plot["name"] for plot in editor.visualization.plot_payloads()] == ["old-plot"]
    assert editor.visualization_draft.begin_edit_plot(0) is not None

    editor._open_document(new_document(second))
    assert editor.visualization_draft.get_active_plot_draft() is None
    assert editor.visualization.plot_payloads() == []
    assert "visualization" not in yaml.safe_load(editor.preview.toPlainText())
    editor.shutdown()


def test_model_change_keeps_incompatible_property_visible_and_blocks_save(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    editor = configured_editor(tmp_path)
    payload = yaml.safe_load(template_text("saturation_table"))
    editor._open_document(new_document(payload))

    editor.form.model.setCurrentText("pr")

    values = editor.form.list_values(editor.form.properties)
    surface_row = values.index("surface_tension")
    item = editor.form.properties.model().index(surface_row, 0)
    assert item.data(DISPLAY_ROLE) == "Unsupported by pr: surface_tension"
    assert not editor._form_valid
    assert not editor.save_button.isEnabled()
    assert "surface_tension" in editor.status.text()
    editor.shutdown()


def test_alias_spelling_and_order_are_preserved_without_canonical_duplicates(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    editor = configured_editor(tmp_path)
    payload = yaml.safe_load(template_text("property_table"))
    payload["fluids"] = ["R290", "Cyclopentane"]
    editor._open_document(new_document(payload))

    editor.form.fluids.setCurrentRow(1)
    editor.form.move_selected(editor.form.fluids, -1)
    editor.form.fluid_input.setEditText("Propane")
    editor.form._add_fluid()

    assert editor.form.list_values(editor.form.fluids) == ["Cyclopentane", "R290"]
    assert "already selected" in editor.status.text()
    assert yaml.safe_load(editor.preview.toPlainText())["fluids"] == [
        "Cyclopentane",
        "R290",
    ]
    editor.shutdown()


def test_selecting_fluid_choice_preserves_edit_text_and_adds_value(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    editor = configured_editor(tmp_path)
    editor._open_document(new_document(yaml.safe_load(template_text("property_table"))))
    row = editor.dataset_draft.fluid_choices.values.index("Cyclopentane")

    editor.form.fluid_input.setCurrentIndex(row)

    assert editor.form.fluid_input.currentText() == "Cyclopentane"
    assert editor.form.fluid_feedback.text() == "Canonical fluid: Cyclopentane"
    editor.form._add_fluid()
    assert editor.dataset_draft.selected_fluid_values()[-1] == "Cyclopentane"
    editor.shutdown()


def test_changing_workspace_clears_the_previous_workspace_draft(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    editor = configured_editor(tmp_path)
    editor._open_document(new_document(yaml.safe_load(template_text("property_table"))))
    editor.visualization_draft.set_enabled(True)
    assert editor.visualization_draft.begin_add_plot() is not None
    editor._capability_cache["heos"] = capabilities()
    replacement = initialize_workspace(tmp_path / "replacement")

    editor.set_workspace(replacement)

    assert editor.workspace == replacement
    assert editor.document is None
    assert editor.visualization_draft.get_active_plot_draft() is None
    assert editor.file_label.text() == "No dataset configuration is open."
    assert editor.preview.toPlainText() == ""
    editor.shutdown()


def test_confirmed_mode_change_preserves_shared_fields_and_resets_mode_state(
    tmp_path: Path,
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    editor = configured_editor(tmp_path)
    payload = yaml.safe_load(template_text("property_table"))
    payload["visualization"] = {
        "plots": [
            {
                "name": "density",
                "kind": "property_curves",
                "property": "mass_density",
                "x": "temperature",
            }
        ]
    }
    editor._open_document(new_document(payload))
    assert editor.visualization_draft.begin_edit_plot(0) is not None
    original_fluids = editor.form.list_values(editor.form.fluids)
    original_properties = editor.form.list_values(editor.form.properties)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    editor.form.mode.setCurrentText("saturation_table")

    assert editor.document is not None
    changed = editor.document.payload
    assert changed["mode"] == "saturation_table"
    assert set(changed["grid"]) == {"temperature"}
    assert changed["fluids"] == original_fluids
    assert changed["properties"] == original_properties
    assert "visualization" not in changed
    assert editor.visualization_draft.get_active_plot_draft() is None
    assert editor.visualization_draft.get_dirty()
    editor.shutdown()


def test_invalid_import_remains_external_and_unopened(
    tmp_path: Path,
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    editor = configured_editor(tmp_path)
    invalid = tmp_path / "invalid.yaml"
    original = b"schema_version: 2\ndocument_type: dataset\n"
    invalid.write_bytes(original)
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (str(invalid), "YAML"),
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args, **_kwargs: None)

    editor.import_dataset()
    _wait_for_worker(application, editor)

    assert editor.document is None
    assert invalid.read_bytes() == original
    assert "failed" in editor.status.text().lower() or "required" in editor.status.text().lower()
    editor.shutdown()


def test_save_as_validates_exact_preview_and_refuses_overwrite(
    tmp_path: Path,
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    editor = configured_editor(tmp_path)
    payload = yaml.safe_load(template_text("property_table"))
    payload["visualization"] = {
        "plots": [
            {
                "name": "density-curves",
                "kind": "property_curves",
                "property": "mass_density",
                "x": "temperature",
            }
        ]
    }
    editor._open_document(new_document(payload))
    assert editor.workspace is not None
    destination = editor.workspace.configs / "property.yaml"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(destination), "YAML"),
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args, **_kwargs: None)

    editor.save_as()
    _wait_for_worker(application, editor)

    assert destination.read_text(encoding="utf-8") == editor.preview.toPlainText()
    assert editor.document is not None
    assert editor.document.source_path == destination
    assert not editor.dataset_draft.get_dirty()
    assert not editor.visualization_draft.get_dirty()
    original = destination.read_bytes()
    editor.save_as()
    _wait_for_worker(application, editor)
    assert destination.read_bytes() == original
    assert "overwrite" in editor.status.text()
    editor.shutdown()


def test_gui_editor_import_does_not_load_scientific_execution_modules() -> None:
    code = """
import sys
import carnopy.app.config_editor
for name in (
    "CoolProp", "numpy", "pandas", "pyarrow", "matplotlib",
    "carnopy.cli", "carnopy.pipeline",
):
    if name in sys.modules:
        raise SystemExit(name)
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def _wait_for_worker(application: QApplication, editor: DatasetConfigEditor) -> None:
    loop = QEventLoop()
    timed_out = False

    def timeout() -> None:
        nonlocal timed_out
        timed_out = True
        loop.quit()

    editor.coordinator.busy_changed.connect(lambda busy: None if busy else loop.quit())
    QTimer.singleShot(15_000, timeout)
    if editor.coordinator.is_busy:
        loop.exec()
    application.processEvents()
    assert not timed_out
    assert not editor.coordinator.is_busy
