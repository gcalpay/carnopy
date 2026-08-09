from __future__ import annotations

import os
import subprocess
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from carnopy.app.comparison_plot_draft import ComparisonPlotDraft
from carnopy.config.sweep import ComparisonPlotConfig


def _draft(payload: dict[str, object] | None = None) -> ComparisonPlotDraft:
    return ComparisonPlotDraft(
        selected_models=("heos", "pr", "srk"),
        reference_model="heos",
        fluids=("R290",),
        properties=("mass_density", "specific_enthalpy"),
        fluid_aliases={"R290": "Propane", "Propane": "Propane"},
        categorical_values={"saturation_endpoint": ("saturated_liquid", "saturated_vapor")},
        payload=payload,
    )


def _normalized(payload: dict[str, object]) -> dict[str, object]:
    return ComparisonPlotConfig.model_validate(payload).model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )


def test_property_comparison_round_trips_every_public_field() -> None:
    payload: dict[str, object] = {
        "name": "density-comparison",
        "kind": "property_comparison",
        "fluid": "Propane",
        "property": "mass_density",
        "x": "temperature",
        "group_by": "pressure",
        "filters": {
            "pressure": 100_000.0,
            "saturation_endpoint": "saturated_liquid",
        },
        "models": ["heos", "pr"],
        "delta_metric": "signed_absolute_difference",
        "value_scale": "log",
        "format": "svg",
    }

    draft = _draft(payload)

    assert draft.get_locally_valid()
    assert draft.payload() == _normalized(payload)
    assert draft.get_explicit_models()
    assert draft.filters.raw_rows() == (
        ("pressure", "100000"),
        ("saturation_endpoint", "saturated_liquid"),
    )
    reference = next(item for item in draft.model_choices.items if item.value == "heos")
    assert reference.selected
    assert reference.compatible


def test_property_delta_round_trips_metric_models_scale_and_format() -> None:
    payload: dict[str, object] = {
        "name": "density-delta",
        "kind": "property_delta",
        "fluid": "R290",
        "property": "mass_density",
        "x": "pressure",
        "models": ["pr", "srk"],
        "delta_metric": "signed_absolute_difference",
        "value_scale": "linear",
        "format": "pdf",
    }

    draft = _draft(payload)

    assert draft.get_locally_valid()
    assert draft.payload() == _normalized(payload)
    reference = next(item for item in draft.model_choices.items if item.value == "heos")
    assert not reference.selected
    assert not reference.compatible
    assert "implicitly" in reference.issue


def test_kind_change_retains_explicit_reference_selection_as_blocking() -> None:
    draft = _draft()
    draft.set_name("kind-change")
    draft.set_fluid("Propane")
    draft.set_property_name("mass_density")
    draft.set_explicit_models(True)

    assert draft.get_locally_valid()
    assert draft.set_model_selected("heos", True) is False
    draft.set_kind("property_delta")

    assert not draft.get_locally_valid()
    assert "reference model" in draft.get_issue()
    assert draft.get_first_invalid_field() == "sweep.comparison.active.models"
    assert draft.set_model_selected("heos", False)
    assert draft.get_locally_valid()
    assert not draft.set_model_selected("heos", True)


def test_implicit_and_empty_explicit_models_preserve_public_schema_distinction() -> None:
    implicit = _draft(
        {
            "name": "implicit",
            "kind": "property_delta",
            "fluid": "R290",
            "property": "mass_density",
            "x": "temperature",
        }
    )
    explicit_empty = _draft(
        {
            "name": "explicit-empty",
            "kind": "property_delta",
            "fluid": "R290",
            "property": "mass_density",
            "x": "temperature",
            "models": [],
        }
    )

    assert implicit.get_locally_valid()
    assert "models" not in implicit.payload()
    assert explicit_empty.get_locally_valid()
    assert explicit_empty.payload()["models"] == []


def test_invalid_filter_rows_remain_visible_with_stable_focus() -> None:
    draft = _draft(
        {
            "name": "invalid-filter",
            "kind": "property_comparison",
            "fluid": "R290",
            "property": "mass_density",
            "x": "temperature",
            "filters": {"backend_model": "pr"},
        }
    )

    assert draft.filters.raw_rows() == (("backend_model", "pr"),)
    assert not draft.get_locally_valid()
    assert draft.get_first_invalid_field() == "sweep.comparison.active.filters"
    assert draft.get_first_invalid_row() == 0


def test_detached_payload_does_not_share_nested_filter_state() -> None:
    draft = _draft(
        {
            "name": "detached",
            "kind": "property_comparison",
            "fluid": "R290",
            "property": "mass_density",
            "x": "temperature",
            "filters": {"pressure": 100_000.0},
        }
    )

    detached = draft.detached_payload()
    detached["filters"]["pressure"] = 200_000.0

    assert draft.payload()["filters"] == {"pressure": 100_000.0}


def test_comparison_plot_draft_import_is_qtcore_only_and_scientifically_isolated() -> None:
    code = """
import sys
import carnopy.app.comparison_plot_draft
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
