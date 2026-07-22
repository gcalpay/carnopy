# ruff: noqa: RUF001

from __future__ import annotations

import copy
import os
import subprocess
import sys
from collections.abc import Mapping
from typing import Any

import pytest
import yaml

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, Qt

from carnopy.app.dataset_draft import DatasetDraft
from carnopy.app.draft_models import (
    CANONICAL_ROLE,
    COMPATIBLE_ROLE,
    DISPLAY_ROLE,
    ISSUE_ROLE,
    LABEL_ROLE,
    SELECTED_ROLE,
    SYMBOL_ROLE,
    UNIT_ROLE,
    VALUE_ROLE,
)
from carnopy.app.sampler_draft import SamplerDraft
from carnopy.config.models import CarnopyConfig
from carnopy.config.normalize import normalize_config
from carnopy.templates import template_text


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
            {"name": "Isobutane", "aliases": ["R600a"]},
            {"name": "Cyclopentane", "aliases": []},
        ],
        "property_catalog": [
            {"name": "mass_density", "supported_models": ["heos", "pr", "srk"]},
            {"name": "specific_enthalpy", "supported_models": ["heos", "pr", "srk"]},
            {"name": "specific_entropy", "supported_models": ["heos", "pr", "srk"]},
            {
                "name": "isobaric_specific_heat_capacity",
                "supported_models": ["heos", "pr", "srk"],
            },
            {"name": "dynamic_viscosity", "supported_models": ["heos"]},
            {"name": "thermal_conductivity", "supported_models": ["heos"]},
            {"name": "surface_tension", "supported_models": ["heos"]},
        ],
        "reference_dependent_fields": ["specific_enthalpy"],
        "reference_state": {
            "policy": "coolprop_DEF",
            "display": "CoolProp DEF",
            "description": (
                "CoolProp's factory reference state is reset before generation and is not "
                "changed while rows are evaluated."
            ),
            "user_selectable": False,
        },
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
    assert index.data(DISPLAY_ROLE) == "Unsupported by pr: Surface tension"
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


def test_model_choices_use_scientific_display_names_and_stable_values(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft()

    observed = [
        (
            draft.model_choices.index(row, 0).data(VALUE_ROLE),
            draft.model_choices.index(row, 0).data(DISPLAY_ROLE),
        )
        for row in range(draft.model_choices.rowCount())
    ]

    assert observed == [
        ("heos", "Helmholtz Equation of State (HEOS)"),
        ("pr", "Peng-Robinson (PR)"),
        ("srk", "Soave-Redlich-Kwong (SRK)"),
    ]


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
    pressure = draft.sampler("pressure")
    assert pressure is not None
    assert pressure.raw_state() == (
        "pressure",
        "explicit",
        "Pa",
        (("values", "101325"),),
    )
    retained = draft.sampler("vapor_mass_fraction")
    assert retained is vapor
    assert retained.raw_state() == vapor_state

    assert draft.set_coordinate("temperature")
    temperature = draft.sampler("temperature")
    assert temperature is not None
    assert temperature.raw_state() == (
        "temperature",
        "explicit",
        "K",
        (("values", "293.15"),),
    )


def test_reference_advisory_comes_from_capabilities(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft(dataset_payload(properties=["specific_enthalpy"]))

    advisory = draft.get_reference_advisory()
    assert "Reference state: CoolProp DEF" in advisory
    assert "factory reference state is reset before generation" in advisory
    assert "backend, model, version" in advisory

    payload = capabilities()
    payload["reference_dependent_fields"] = []
    without_advisory = DatasetDraft()
    without_advisory.apply_capabilities(payload)
    without_advisory.load_payload(dataset_payload(properties=["specific_enthalpy"]))
    assert without_advisory.get_reference_advisory() == ""


def test_mode_and_coordinate_choices_have_human_readable_labels(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft()

    assert [
        draft.mode_choices.data(draft.mode_choices.index(row, 0), DISPLAY_ROLE)
        for row in range(draft.mode_choices.rowCount())
    ] == ["Property table", "Saturation table", "Vapor-mass-fraction table"]
    assert [
        draft.coordinate_choices.data(
            draft.coordinate_choices.index(row, 0),
            DISPLAY_ROLE,
        )
        for row in range(draft.coordinate_choices.rowCount())
    ] == ["Temperature", "Pressure"]


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


def test_structured_first_invalid_field_and_row_follow_authoritative_order(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft(dataset_payload(properties=["surface_tension"]))
    draft.set_model_name("pr")

    assert draft.get_first_invalid_field() == "dataset.properties"
    assert draft.get_first_invalid_row() == 0

    draft.remove_property(0)
    assert draft.get_first_invalid_field() == "dataset.properties"
    assert draft.get_first_invalid_row() == -1

    pressure = draft.sampler("pressure")
    assert pressure is not None
    pressure.set_text("values", "")
    assert draft.get_first_invalid_field() == "dataset.grid.pressure.values"
    assert draft.get_first_invalid_row() == -1


def test_rejected_unit_change_does_not_change_dataset_dirty_state(
    application: QCoreApplication,
) -> None:
    del application
    payload = dataset_payload()
    grid = payload["grid"]
    assert isinstance(grid, dict)
    grid["temperature"] = {
        "kind": "explicit",
        "values": [0.0072992700729927],
        "unit": "K",
    }
    draft = configured_draft(payload)
    temperature = draft.sampler("temperature")
    assert temperature is not None
    before = draft.raw_state()

    assert not temperature.requestUnitChange("degC")

    assert draft.raw_state() == before
    assert not draft.get_dirty()
    assert draft.get_locally_valid()


def test_destructive_dataset_methods_are_not_qml_invokable(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft()
    meta = draft.metaObject()
    methods = {
        bytes(meta.method(index).name()).decode("utf-8")
        for index in range(meta.methodOffset(), meta.methodCount())
    }

    assert "apply_mode_change" not in methods
    assert "set_coordinate" not in methods


def test_default_property_table_exposes_approved_projection(
    application: QCoreApplication,
) -> None:
    del application
    payload = yaml.safe_load(template_text("property_table"))
    assert isinstance(payload, dict)
    draft = configured_draft(payload)

    assert draft.get_grid_combinations_per_fluid() == 4_141
    assert draft.get_projected_rows_per_fluid() == 4_141
    assert draft.get_projected_rows() == 8_282
    assert draft.get_projection_available()
    assert draft.get_projection_issue() == ""


def test_projection_preserves_per_fluid_counts_when_no_fluid_is_selected(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft()

    assert draft.remove_fluid(0)

    assert draft.get_grid_combinations_per_fluid() == 6
    assert draft.get_projected_rows_per_fluid() == 6
    assert draft.get_projected_rows() == 0
    assert not draft.get_projection_available()
    assert draft.get_projection_issue() == "Add at least one fluid."


def test_invalid_sampler_makes_projection_unavailable(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft()
    pressure = draft.sampler("pressure")
    assert pressure is not None

    pressure.set_text("values", "")

    assert draft.get_grid_combinations_per_fluid() == 0
    assert draft.get_projected_rows_per_fluid() == 0
    assert draft.get_projected_rows() == 0
    assert not draft.get_projection_available()
    assert draft.get_projection_issue() == pressure.get_issue()


@pytest.mark.parametrize("failure", ["unknown", "duplicate", "incompatible"])
def test_capability_refresh_retains_fluid_projection_failures(
    application: QCoreApplication,
    failure: str,
) -> None:
    del application
    initial = dataset_payload()
    initial["fluids"] = ["R290", "Cyclopentane"]
    draft = configured_draft(initial)
    revised = copy.deepcopy(capabilities())
    if failure == "unknown":
        revised["fluids"] = [{"name": "Cyclopentane", "aliases": []}]
    elif failure == "duplicate":
        revised["fluids"] = [{"name": "Propane", "aliases": ["R290", "Cyclopentane"]}]
    else:
        revised["fluids"][0]["supported_models"] = ["pr"]

    draft.apply_capabilities(revised)

    assert draft.selected_fluid_values() == ("R290", "Cyclopentane")
    assert draft.get_grid_combinations_per_fluid() == 6
    assert draft.get_projected_rows_per_fluid() == 6
    assert draft.get_projected_rows() == 0
    assert not draft.get_projection_available()
    assert draft.get_projection_issue()
    assert draft.get_first_invalid_field() == "dataset.fluids"


def test_over_limit_projection_is_exact_available_and_blocking(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft()
    temperature = draft.sampler("temperature")
    assert temperature is not None

    temperature.set_text("num", "1000000")

    assert draft.get_grid_combinations_per_fluid() == 2_000_000
    assert draft.get_projected_rows_per_fluid() == 2_000_000
    assert draft.get_projected_rows() == 2_000_000
    assert draft.get_projection_available()
    assert "exceeds limit 1,000,000" in draft.get_projection_issue()
    assert not draft.get_locally_valid()


def test_property_models_expose_locked_scientific_presentation_roles(
    application: QCoreApplication,
) -> None:
    del application
    expected = {
        "specific_enthalpy": ("Specific enthalpy", "h", "J·kg⁻¹"),
        "specific_entropy": ("Specific entropy", "s", "J·kg⁻¹·K⁻¹"),
        "specific_internal_energy": ("Specific internal energy", "u", "J·kg⁻¹"),
        "mass_density": ("Mass density", "ρ", "kg·m⁻³"),
        "isobaric_specific_heat_capacity": (
            "Isobaric specific heat capacity",
            "cₚ",
            "J·kg⁻¹·K⁻¹",
        ),
        "isochoric_specific_heat_capacity": (
            "Isochoric specific heat capacity",
            "cᵥ",
            "J·kg⁻¹·K⁻¹",
        ),
        "dynamic_viscosity": ("Dynamic viscosity", "μ", "Pa·s"),
        "kinematic_viscosity": ("Kinematic viscosity", "ν", "m²·s⁻¹"),
        "thermal_conductivity": ("Thermal conductivity", "k", "W·m⁻¹·K⁻¹"),
        "prandtl_number": ("Prandtl number", "Pr", "1"),
        "speed_of_sound": ("Speed of sound", "a", "m·s⁻¹"),
        "molar_mass": ("Molar mass", "M", "kg·mol⁻¹"),
        "critical_temperature": ("Critical temperature", "T<sub>c</sub>", "K"),
        "critical_pressure": ("Critical pressure", "p<sub>c</sub>", "Pa"),
        "triple_point_temperature": (
            "Triple-point temperature",
            "T<sub>tr</sub>",
            "K",
        ),
        "surface_tension": ("Surface tension", "σ", "N·m⁻¹"),
    }
    payload = capabilities()
    payload["property_catalog"] = [
        {"name": name, "supported_models": ["heos", "pr", "srk"]} for name in expected
    ]
    draft = DatasetDraft()
    draft.apply_capabilities(payload)
    draft.load_payload(dataset_payload())

    observed: dict[str, tuple[object, object, object]] = {}
    for row in range(draft.property_choices.rowCount()):
        index = draft.property_choices.index(row, 0)
        name = str(index.data(VALUE_ROLE))
        observed[name] = (
            index.data(LABEL_ROLE),
            index.data(SYMBOL_ROLE),
            index.data(UNIT_ROLE),
        )
        assert index.data(CANONICAL_ROLE) == name

    assert observed == expected


class ProjectionBackend:
    name = "coolprop"
    model = "heos"

    def canonicalize_fluid(self, fluid: str) -> str:
        assert fluid == "R290"
        return "Propane"

    def unsupported_properties(self, _properties: list[str]) -> list[str]:
        return []


@pytest.mark.parametrize(
    "sampler",
    [
        {"kind": "explicit", "values": [280.0, 300.0, 320.0], "unit": "K"},
        {"kind": "linspace", "start": 280.0, "stop": 320.0, "num": 3, "unit": "K"},
        {"kind": "stepspace", "start": 280.0, "stop": 320.0, "step": 20.0, "unit": "K"},
        {"kind": "geomspace", "start": 280.0, "stop": 320.0, "num": 3, "unit": "K"},
        {
            "kind": "logspace",
            "start_exp": 2.45,
            "stop_exp": 2.5,
            "num": 3,
            "base": 10.0,
            "unit": "K",
        },
    ],
)
@pytest.mark.parametrize(
    "mode",
    ["property_table", "saturation_table", "vapor_mass_fraction_table"],
)
def test_gui_projection_matches_production_for_every_sampler_kind_and_mode(
    application: QCoreApplication,
    sampler: dict[str, object],
    mode: str,
) -> None:
    del application
    payload = dataset_payload(mode)
    grid = payload["grid"]
    assert isinstance(grid, dict)
    grid["temperature"] = sampler
    draft = configured_draft(payload)
    config = CarnopyConfig.model_validate(payload)

    normalized = normalize_config(config, ProjectionBackend())  # type: ignore[arg-type]

    assert draft.get_projection_available()
    assert draft.get_projected_rows() == normalized.projected_rows
