from __future__ import annotations

import os
import subprocess
import sys
from typing import Any, cast

import pytest
import yaml

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from carnopy.app.sweep_draft import SweepDraft
from carnopy.config.sweep import ModelSweepConfig
from carnopy.templates import template_text


def _capabilities(
    *,
    models: list[str] | None = None,
    density_models: list[str] | None = None,
) -> dict[str, object]:
    available_models = models or ["heos", "pr", "srk"]
    return {
        "model": "heos",
        "models": available_models,
        "modes": ["property_table", "saturation_table", "vapor_mass_fraction_table"],
        "units_by_axis": {
            "temperature": ["K", "degC"],
            "pressure": ["Pa", "bar"],
            "vapor_mass_fraction": ["1"],
        },
        "dataset_formats": ["csv", "parquet"],
        "fluids": [{"name": "Propane", "aliases": ["R290"]}],
        "property_catalog": [
            {
                "name": "mass_density",
                "supported_models": density_models or available_models,
            },
            {
                "name": "specific_enthalpy",
                "supported_models": available_models,
            },
        ],
        "reference_dependent_fields": [],
        "reference_state": {},
        "visualization": {
            "plot_kinds": [],
            "formats": ["png", "svg", "pdf"],
            "scales": ["linear", "log"],
            "kind_contracts": {},
            "fields": [],
            "display_units": {},
            "categorical_values": {},
        },
    }


def _sweep_payload(mode: str = "property_table") -> dict[str, Any]:
    value = yaml.safe_load(template_text(cast(Any, mode)))
    assert isinstance(value, dict)
    value["document_type"] = "model_sweep"
    value["backend"] = {
        "name": "coolprop",
        "models": ["heos", "pr", "srk"],
        "reference_model": "heos",
    }
    value["fluids"] = ["Propane"]
    value["properties"] = ["mass_density"]
    return value


def _normalized(payload: dict[str, Any]) -> dict[str, Any]:
    return ModelSweepConfig.model_validate(payload).model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )


def _sweep_with_comparisons() -> dict[str, Any]:
    payload = _sweep_payload()
    payload["comparison_plots"] = {
        "format": "svg",
        "plots": [
            {
                "name": "density-comparison",
                "kind": "property_comparison",
                "fluid": "Propane",
                "property": "mass_density",
                "x": "temperature",
                "group_by": "pressure",
                "models": ["heos", "pr", "srk"],
            },
            {
                "name": "density-delta",
                "kind": "property_delta",
                "fluid": "Propane",
                "property": "mass_density",
                "x": "temperature",
                "group_by": "pressure",
                "models": ["pr", "srk"],
                "delta_metric": "signed_absolute_difference",
                "format": "pdf",
            },
        ],
    }
    return payload


@pytest.mark.parametrize(
    "mode",
    ["property_table", "saturation_table", "vapor_mass_fraction_table"],
)
def test_sweep_draft_round_trips_every_dataset_mode(mode: str) -> None:
    payload = _sweep_payload(mode)
    draft = SweepDraft()
    draft.apply_capabilities(_capabilities())
    draft.load_payload(payload)

    assert draft.get_locally_valid()
    assert not draft.get_dirty()
    assert draft.payload() == _normalized(payload)
    assert draft.dataset_draft.get_mode_name() == mode
    assert draft.dataset_draft.selected_fluid_values() == ("Propane",)
    assert draft.dataset_draft.selected_property_values() == ("mass_density",)
    assert draft.dataset_draft.output_selected("csv")
    assert draft.dataset_draft.output_selected("parquet")


@pytest.mark.parametrize(
    "sampler",
    [
        {"kind": "explicit", "values": [280.0, 300.0], "unit": "K"},
        {"kind": "linspace", "start": 280.0, "stop": 340.0, "num": 5, "unit": "K"},
        {"kind": "stepspace", "start": 280.0, "stop": 340.0, "step": 15.0, "unit": "K"},
        {"kind": "geomspace", "start": 280.0, "stop": 340.0, "num": 5, "unit": "K"},
        {
            "kind": "logspace",
            "start_exp": 2.0,
            "stop_exp": 3.0,
            "num": 5,
            "base": 10.0,
            "unit": "K",
        },
    ],
)
def test_sweep_draft_round_trips_every_sampler_shape(sampler: dict[str, object]) -> None:
    payload = _sweep_payload()
    payload["grid"]["temperature"] = sampler
    draft = SweepDraft()
    draft.apply_capabilities(_capabilities())
    draft.load_payload(payload)

    assert draft.get_locally_valid()
    assert draft.payload() == _normalized(payload)
    temperature = draft.dataset_draft.sampler("temperature")
    assert temperature is not None
    assert temperature.get_kind() == sampler["kind"]


def test_sweep_reference_and_model_selection_preserve_explicit_constraints() -> None:
    draft = SweepDraft()
    draft.apply_capabilities(_capabilities())
    draft.load_payload(_sweep_payload())
    messages: list[str] = []
    draft.message.connect(messages.append)

    assert not draft.set_model_selected("heos", False)
    assert messages == ["Choose another reference model before removing this model."]
    assert draft.set_reference_model("pr")
    assert draft.dataset_draft.get_model_name() == "pr"
    assert draft.set_model_selected("heos", False)
    assert draft.get_selected_models() == ["pr", "srk"]
    assert draft.get_dirty()
    assert draft.payload()["backend"] == {
        "name": "coolprop",
        "models": ["pr", "srk"],
        "reference_model": "pr",
    }

    assert draft.set_model_selected("srk", False)
    assert not draft.get_locally_valid()
    assert draft.get_first_invalid_field() == "sweep.backend.models"
    assert draft.set_model_selected("srk", True)
    assert draft.get_locally_valid()
    draft.mark_baseline()
    assert not draft.get_dirty()


def test_sweep_dataset_fields_edit_through_existing_draft_models() -> None:
    draft = SweepDraft()
    draft.apply_capabilities(_capabilities())
    draft.load_payload(_sweep_payload())

    assert draft.dataset_draft.add_fluid("R290") is False
    assert draft.dataset_draft.add_property("specific_enthalpy")
    assert draft.dataset_draft.set_output_selected("csv", False)
    pressure = draft.dataset_draft.sampler("pressure")
    assert pressure is not None
    pressure.set_text("num", "7")

    value = draft.payload()
    assert value["properties"] == ["mass_density", "specific_enthalpy"]
    assert value["outputs"] == {"dataset_formats": ["parquet"]}
    assert value["grid"]["pressure"]["num"] == 7
    assert draft.get_dirty()


def test_sweep_mode_and_coordinate_recomposition_require_confirmation() -> None:
    draft = SweepDraft()
    draft.apply_capabilities(_capabilities())
    draft.load_payload(_sweep_payload())

    assert not draft.apply_mode_change("saturation_table", False)
    assert draft.dataset_draft.get_mode_name() == "property_table"
    assert draft.apply_mode_change("saturation_table", True)
    assert draft.dataset_draft.get_mode_name() == "saturation_table"
    assert draft.get_dirty()

    assert not draft.apply_coordinate_change("pressure", False)
    assert draft.dataset_draft.get_coordinate_name() == "temperature"
    assert draft.apply_coordinate_change("pressure", True)
    assert draft.dataset_draft.get_coordinate_name() == "pressure"
    assert draft.get_locally_valid()
    assert set(draft.payload()["grid"]) == {"pressure"}


def test_imported_capability_incompatibility_is_retained_clean_and_blocking() -> None:
    payload = _sweep_payload()
    draft = SweepDraft()
    draft.apply_capabilities(_capabilities(models=["heos", "pr"], density_models=["heos"]))
    draft.load_payload(payload)

    assert not draft.get_locally_valid()
    assert not draft.get_dirty()
    assert draft.get_selected_models() == ["heos", "pr", "srk"]
    assert draft.dataset_draft.selected_property_values() == ("mass_density",)
    assert "srk" in draft.get_issue()
    unavailable = next(item for item in draft.model_choices.items if item.value == "srk")
    assert unavailable.selected
    assert not unavailable.compatible

    assert draft.set_model_selected("srk", False)
    assert "mass_density" in draft.get_issue()
    assert draft.get_first_invalid_field() == "sweep.properties"
    assert draft.get_first_invalid_row() == 0
    with pytest.raises(ValueError, match="cannot mark an invalid model sweep"):
        draft.mark_baseline()


def test_unavailable_imported_reference_model_is_retained_clean_and_blocking() -> None:
    payload = _sweep_payload()
    payload["backend"]["reference_model"] = "srk"
    draft = SweepDraft()
    draft.apply_capabilities(_capabilities(models=["heos", "pr"]))

    draft.load_payload(payload)

    assert draft.get_reference_model() == "srk"
    assert draft.dataset_draft.get_model_name() == "srk"
    assert draft.dataset_draft.selected_fluid_values() == ("Propane",)
    assert draft.dataset_draft.selected_property_values() == ("mass_density",)
    assert not draft.get_locally_valid()
    assert not draft.get_dirty()
    assert "srk" in draft.get_issue()


def test_import_before_capabilities_remains_clean_until_rechecked() -> None:
    payload = _sweep_payload()
    draft = SweepDraft()

    draft.load_payload(payload)

    assert not draft.get_locally_valid()
    assert draft.get_issue() == "Sweep capabilities are not loaded."
    assert not draft.get_dirty()
    assert draft.get_selected_models() == ["heos", "pr", "srk"]

    draft.apply_capabilities(_capabilities())
    assert draft.get_locally_valid()
    assert not draft.get_dirty()
    assert draft.payload() == _normalized(payload)


def test_comparison_payload_handoff_is_detached_and_retained_when_incompatible() -> None:
    payload = _sweep_payload()
    payload["comparison_plots"] = {
        "format": "svg",
        "plots": [
            {
                "name": "density-comparison",
                "kind": "property_comparison",
                "fluid": "Propane",
                "property": "mass_density",
                "x": "temperature",
                "models": ["heos", "pr", "srk"],
            }
        ],
    }
    draft = SweepDraft()
    draft.apply_capabilities(_capabilities())
    draft.load_payload(payload)
    expected = _normalized(payload)

    assert draft.payload() == expected
    preserved = draft.comparison_plots_payload()
    assert preserved == expected["comparison_plots"]
    assert preserved is not None
    preserved["format"] = "pdf"
    assert draft.comparison_plots_payload() == expected["comparison_plots"]

    assert draft.set_reference_model("pr")
    assert draft.set_model_selected("heos", False)
    assert not draft.get_locally_valid()
    assert draft.comparison_plots_payload() == expected["comparison_plots"]


def test_structured_comparisons_round_trip_with_effective_summaries() -> None:
    payload = _sweep_with_comparisons()
    draft = SweepDraft()
    draft.apply_capabilities(_capabilities())
    draft.load_payload(payload)

    assert draft.get_locally_valid()
    assert not draft.get_dirty()
    assert draft.payload() == _normalized(payload)
    assert draft.get_comparison_format() == "svg"
    assert draft.comparison_plots_model.values == (
        "density-comparison",
        "density-delta",
    )
    first, second = draft.comparison_plots_model.items
    assert "Property comparison" in first.display
    assert "HEOS, PR, SRK" in first.display
    assert first.display.endswith("SVG")
    assert "Property delta" in second.display
    assert "absolute difference" in second.display
    assert second.display.endswith("PDF")

    assert not draft.set_comparison_format("jpg")
    assert draft.set_comparison_format("pdf")
    assert draft.get_dirty()
    assert draft.comparison_plots_model.items[0].display.endswith("PDF")
    assert draft.comparison_plots_model.items[1].display.endswith("PDF")


def test_comparison_editor_is_transient_until_explicit_commit_or_cancel() -> None:
    draft = SweepDraft()
    draft.apply_capabilities(_capabilities())
    draft.load_payload(_sweep_payload())

    assert draft.begin_add_comparison()
    assert draft.get_has_active_comparison_edit()
    assert not draft.get_dirty()
    assert not draft.get_locally_valid()
    with pytest.raises(ValueError, match="Commit or cancel"):
        draft.payload()
    with pytest.raises(ValueError, match="invalid model sweep"):
        draft.mark_baseline()
    assert not draft.remove_comparison(0)
    assert not draft.move_comparison(0, 0)

    active = draft.get_active_comparison_draft()
    assert active is not None
    active.set_name("new-comparison")
    active.set_property_name("mass_density")
    assert draft.commit_comparison()
    assert not draft.get_has_active_comparison_edit()
    assert draft.get_dirty()
    assert [item["name"] for item in draft.comparison_payloads()] == ["new-comparison"]

    draft.mark_baseline()
    assert draft.begin_edit_comparison(0)
    active = draft.get_active_comparison_draft()
    assert active is not None
    active.set_name("temporary-name")
    assert not draft.get_dirty()
    assert draft.cancel_comparison()
    assert not draft.get_has_active_comparison_edit()
    assert not draft.get_dirty()
    assert draft.comparison_payloads()[0]["name"] == "new-comparison"


def test_comparison_names_order_and_removal_are_committed_deterministically() -> None:
    draft = SweepDraft()
    draft.apply_capabilities(_capabilities())
    draft.load_payload(_sweep_with_comparisons())
    messages: list[str] = []
    draft.message.connect(messages.append)

    assert draft.begin_edit_comparison(0)
    active = draft.get_active_comparison_draft()
    assert active is not None
    active.set_name("density-delta")
    assert not draft.commit_comparison()
    assert messages[-1] == "Comparison plot names must be unique."
    assert draft.get_has_active_comparison_edit()
    assert draft.cancel_comparison()

    assert draft.move_comparison(1, 0)
    assert [item["name"] for item in draft.comparison_payloads()] == [
        "density-delta",
        "density-comparison",
    ]
    assert [item["name"] for item in draft.payload()["comparison_plots"]["plots"]] == [
        "density-delta",
        "density-comparison",
    ]
    assert draft.remove_comparison(1)
    assert [item["name"] for item in draft.comparison_payloads()] == ["density-delta"]


def test_incompatible_committed_comparison_is_retained_clean_and_focusable() -> None:
    payload = _sweep_payload()
    payload["comparison_plots"] = {
        "plots": [
            {
                "name": "unsupported-filter",
                "kind": "property_comparison",
                "fluid": "Propane",
                "property": "mass_density",
                "x": "temperature",
                "filters": {"backend_model": "pr"},
            }
        ]
    }
    draft = SweepDraft()
    draft.apply_capabilities(_capabilities())
    draft.load_payload(payload)

    assert not draft.get_locally_valid()
    assert not draft.get_dirty()
    assert draft.get_first_invalid_field() == "sweep.comparison_plots"
    assert draft.get_first_invalid_row() == 0
    assert draft.comparison_payloads()[0]["filters"] == {"backend_model": "pr"}
    assert not draft.comparison_plots_model.items[0].compatible


def test_comparison_commit_rechecks_current_sweep_context() -> None:
    payload = _sweep_payload()
    payload["properties"].append("specific_enthalpy")
    draft = SweepDraft()
    draft.apply_capabilities(_capabilities())
    draft.load_payload(payload)
    messages: list[str] = []
    draft.message.connect(messages.append)

    assert draft.begin_add_comparison()
    active = draft.get_active_comparison_draft()
    assert active is not None
    active.set_name("enthalpy-comparison")
    active.set_property_name("specific_enthalpy")
    assert draft.dataset_draft.remove_property_value("specific_enthalpy")

    assert not draft.commit_comparison()
    assert "unselected property" in messages[-1]
    assert draft.get_has_active_comparison_edit()
    assert draft.cancel_comparison()


def test_sweep_draft_clear_resets_document_state_without_capabilities() -> None:
    draft = SweepDraft()
    draft.apply_capabilities(_capabilities())
    draft.load_payload(_sweep_payload())

    draft.clear()

    assert not draft.get_locally_valid()
    assert not draft.get_dirty()
    assert draft.get_selected_models() == []
    assert draft.get_reference_model() == ""
    assert draft.comparison_plots_payload() is None


def test_sweep_draft_import_is_qtcore_only_and_scientifically_isolated() -> None:
    code = """
import sys
import carnopy.app.sweep_draft
for name in (
    "PySide6.QtWidgets", "CoolProp", "numpy", "pandas", "pyarrow", "matplotlib",
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
