from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, Qt

from carnopy.app.dataset_draft import DatasetDraft
from carnopy.app.draft_models import (
    CANONICAL_ROLE,
    COMPATIBLE_ROLE,
    DISPLAY_ROLE,
    ISSUE_ROLE,
    SELECTED_ROLE,
    VALUE_ROLE,
)
from carnopy.app.sampler_draft import SamplerDraft


@pytest.fixture(scope="module")
def application() -> QCoreApplication:
    existing = QCoreApplication.instance()
    app = existing if isinstance(existing, QCoreApplication) else QCoreApplication([])
    yield app
    if type(app) is QCoreApplication:
        app.quit()
        app.deleteLater()
        QCoreApplication.sendPostedEvents(app, QEvent.Type.DeferredDelete)


def capabilities() -> dict[str, Any]:
    return {
        "models": ["heos", "pr", "srk"],
        "modes": [
            "property_table",
            "saturation_table",
            "vapor_mass_fraction_table",
        ],
        "units_by_axis": {
            "temperature": ["K", "degC"],
            "pressure": ["Pa", "bar"],
            "vapor_mass_fraction": ["1"],
        },
        "dataset_formats": ["csv", "parquet"],
        "fluids": [
            {"name": "Propane", "aliases": ["R290", "n-Propane"]},
            {"name": "Cyclopentane", "aliases": []},
        ],
        "property_catalog": [
            {"name": "mass_density", "supported_models": ["heos", "pr", "srk"]},
            {"name": "specific_enthalpy", "supported_models": ["heos", "pr", "srk"]},
            {"name": "surface_tension", "supported_models": ["heos"]},
        ],
        "reference_dependent_fields": ["specific_enthalpy"],
    }


def dataset_payload(
    mode: str = "property_table",
    *,
    properties: list[str] | None = None,
) -> dict[str, Any]:
    grids: dict[str, dict[str, object]] = {
        "property_table": {
            "temperature": {
                "kind": "linspace",
                "start": 280.0,
                "stop": 320.0,
                "num": 3,
                "unit": "K",
            },
            "pressure": {
                "kind": "explicit",
                "values": [1.0, 2.0],
                "unit": "bar",
            },
        },
        "saturation_table": {
            "temperature": {
                "kind": "stepspace",
                "start": 280.0,
                "stop": 320.0,
                "step": 10.0,
                "unit": "K",
            }
        },
        "vapor_mass_fraction_table": {
            "temperature": {
                "kind": "linspace",
                "start": 280.0,
                "stop": 320.0,
                "num": 3,
                "unit": "K",
            },
            "vapor_mass_fraction": {
                "kind": "explicit",
                "values": [0.0, 0.5, 1.0],
                "unit": "1",
            },
        },
    }
    return {
        "schema_version": 2,
        "document_type": "dataset",
        "backend": {"name": "coolprop", "model": "heos"},
        "mode": mode,
        "fluids": ["R290"],
        "grid": grids[mode],
        "properties": properties or ["mass_density"],
        "outputs": {"dataset_formats": ["csv", "parquet"]},
    }


def configured_draft(payload: Mapping[str, object] | None = None) -> DatasetDraft:
    draft = DatasetDraft()
    draft.apply_capabilities(capabilities())
    draft.load_payload(payload or dataset_payload())
    return draft


@pytest.mark.parametrize(
    "sampler",
    [
        {"kind": "explicit", "values": [2.0, 1.0], "unit": "bar"},
        {"kind": "linspace", "start": 1.0, "stop": 5.0, "num": 5, "unit": "bar"},
        {
            "kind": "stepspace",
            "start": 1.0,
            "stop": 5.0,
            "step": 1.0,
            "unit": "bar",
        },
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
def test_sampler_draft_round_trips_public_kinds(
    application: QCoreApplication,
    sampler: dict[str, object],
) -> None:
    del application
    draft = SamplerDraft("pressure")
    draft.load_payload(sampler, available_units=["Pa", "bar"])

    assert draft.get_valid()
    assert draft.payload() == sampler


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("start", "", "requires a number"),
        ("start", "nan", "must be finite"),
        ("num", "2.5", "requires an integer"),
        ("num", "1000001", "must be between"),
    ],
)
def test_sampler_draft_preserves_invalid_raw_text(
    application: QCoreApplication,
    field: str,
    value: str,
    message: str,
) -> None:
    del application
    draft = SamplerDraft("pressure")
    draft.load_payload(
        {"kind": "linspace", "start": 1.0, "stop": 5.0, "num": 5, "unit": "bar"},
        available_units=["Pa", "bar"],
    )

    draft.set_text(field, value)

    assert draft.text(field) == value
    assert not draft.get_valid()
    assert message in draft.get_issue()
    with pytest.raises(ValueError, match=message):
        draft.payload()


def test_valid_equivalent_text_and_invalid_recovery_follow_dirty_contract(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft()
    pressure = draft.sampler("pressure")
    assert pressure is not None
    model_changes: list[object] = []
    draft.samplers.dataChanged.connect(lambda *_args: model_changes.append(object()))

    pressure.set_text("values", "1.0, 2.0")
    assert draft.get_locally_valid()
    assert not draft.get_dirty()

    pressure.set_text("values", "")
    assert not draft.get_locally_valid()
    assert draft.get_dirty()
    assert "comma-separated" in draft.get_issue()
    assert model_changes

    pressure.set_text("values", "1, 2")
    assert draft.get_locally_valid()
    assert not draft.get_dirty()


def test_dataset_payload_is_dataset_only_and_merge_preserves_visualization(
    application: QCoreApplication,
) -> None:
    del application
    complete = dataset_payload()
    complete["visualization"] = {
        "plots": [{"name": "density", "kind": "pv"}],
    }
    draft = configured_draft(complete)

    dataset = draft.dataset_payload()
    merged = draft.merge_into(complete)

    assert "visualization" not in dataset
    assert merged["visualization"] == complete["visualization"]
    complete["visualization"] = {"plots": [{"name": "other", "kind": "ts"}]}
    assert not draft.get_dirty()


def test_alias_identity_order_and_roles_are_stable(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft()
    messages: list[str] = []
    draft.message.connect(messages.append)

    assert draft.add_fluid("Cyclopentane")
    assert not draft.add_fluid("Propane")
    assert draft.move_fluid(1, -1)

    assert draft.selected_fluid_values() == ("Cyclopentane", "R290")
    assert "already selected" in messages[-1]
    first = draft.selected_fluids.index(1, 0)
    assert first.data(VALUE_ROLE) == "R290"
    assert first.data(CANONICAL_ROLE) == "Propane"


def test_model_change_retains_incompatible_property_and_blocks_payload(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft(dataset_payload(properties=["surface_tension"]))

    draft.set_model_name("pr")

    assert draft.selected_property_values() == ("surface_tension",)
    assert not draft.get_locally_valid()
    assert draft.get_dirty()
    index = draft.selected_properties.index(0, 0)
    assert index.data(DISPLAY_ROLE) == "Unsupported by pr: surface_tension"
    assert index.data(COMPATIBLE_ROLE) is False
    assert index.data(SELECTED_ROLE) is True
    assert "Remove this property" in str(index.data(ISSUE_ROLE))
    assert index.flags() & Qt.ItemFlag.ItemIsEnabled
    choice = next(
        draft.property_choices.index(row, 0)
        for row in range(draft.property_choices.rowCount())
        if draft.property_choices.index(row, 0).data(VALUE_ROLE) == "surface_tension"
    )
    assert not choice.flags() & Qt.ItemFlag.ItemIsEnabled


def test_mode_request_is_provisional_and_apply_resets_only_mode_state(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft()
    requested: list[str] = []
    draft.mode_change_requested.connect(requested.append)
    fluids = draft.selected_fluid_values()
    properties = draft.selected_property_values()

    draft.request_mode_change("saturation_table")
    assert requested == ["saturation_table"]
    assert draft.get_mode_name() == "property_table"

    assert draft.apply_mode_change("saturation_table")
    assert draft.get_mode_name() == "saturation_table"
    assert draft.selected_fluid_values() == fluids
    assert draft.selected_property_values() == properties
    assert [sampler.get_axis() for sampler in draft.samplers.drafts] == ["temperature"]


def test_coordinate_change_preserves_vapor_fraction_sampler(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft(dataset_payload("vapor_mass_fraction_table"))
    vapor = draft.sampler("vapor_mass_fraction")
    assert vapor is not None
    vapor_state = vapor.raw_state()

    assert draft.set_coordinate("pressure")

    assert draft.get_coordinate_name() == "pressure"
    assert draft.sampler("temperature") is None
    assert draft.sampler("pressure") is not None
    retained = draft.sampler("vapor_mass_fraction")
    assert retained is vapor
    assert retained.raw_state() == vapor_state


def test_reference_advisory_comes_from_capabilities(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft(dataset_payload(properties=["specific_enthalpy"]))

    assert "Reference-state advisory" in draft.get_reference_advisory()

    payload = capabilities()
    payload["reference_dependent_fields"] = []
    without_advisory = DatasetDraft()
    without_advisory.apply_capabilities(payload)
    without_advisory.load_payload(dataset_payload(properties=["specific_enthalpy"]))
    assert without_advisory.get_reference_advisory() == ""


def test_change_signals_emit_only_for_effective_changes(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft()
    model_changes: list[str] = []
    draft.model_name_changed.connect(lambda: model_changes.append(draft.get_model_name()))

    draft.set_model_name("heos")
    draft.set_model_name("pr")
    draft.set_model_name("pr")

    assert model_changes == ["pr"]


def test_capabilities_do_not_create_phantom_draft_state(
    application: QCoreApplication,
) -> None:
    del application
    draft = DatasetDraft()

    draft.apply_capabilities(capabilities())

    assert draft.get_model_name() == ""
    assert not draft.add_fluid("Propane")
    assert not draft.set_output_selected("csv", True)
    assert not draft.get_dirty()
    assert not draft.get_locally_valid()


def test_dataset_draft_import_keeps_scientific_modules_out_of_gui_process() -> None:
    code = """
import sys
import carnopy.app.dataset_draft
for name in (
    "CoolProp", "numpy", "pandas", "pyarrow", "matplotlib",
    "carnopy.cli", "carnopy.pipeline", "carnopy.visualization.plots",
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
