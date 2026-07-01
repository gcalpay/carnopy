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
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from carnopy.app.config_document import new_document
from carnopy.app.config_editor import DatasetConfigEditor
from carnopy.app.config_widgets import SamplerEditor
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
    }


def configured_editor(tmp_path: Path) -> DatasetConfigEditor:
    editor = DatasetConfigEditor()
    editor.workspace = initialize_workspace(tmp_path / "workspace")
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
    editor = SamplerEditor("pressure")
    editor.configure_units(["Pa", "bar"])
    editor.load_sampler(sampler)

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
    item = editor.form.properties.item(surface_row)
    assert item is not None
    assert item.text() == "Unsupported by pr: surface_tension"
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


def test_changing_workspace_clears_the_previous_workspace_draft(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    editor = configured_editor(tmp_path)
    editor._open_document(new_document(yaml.safe_load(template_text("property_table"))))
    editor.client._capabilities["heos"] = capabilities()
    replacement = initialize_workspace(tmp_path / "replacement")

    editor.set_workspace(replacement)

    assert editor.workspace == replacement
    assert editor.document is None
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

    editor.client.busy_changed.connect(lambda busy: None if busy else loop.quit())
    QTimer.singleShot(15_000, timeout)
    if editor.client.is_busy:
        loop.exec()
    application.processEvents()
    assert not timed_out
    assert not editor.client.is_busy
