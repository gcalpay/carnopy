from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from carnopy.app.field_ids import PLOT_FILTERS, PLOT_KIND, PLOT_NAME, plot_field
from carnopy.app.mapping_draft import FIELD_ROLE, ISSUE_ROLE, MappingDraftModel
from carnopy.app.plot_draft import PlotDraft


def capabilities(*, inspected: bool = False) -> dict[str, Any]:
    visualization: dict[str, Any] = {
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
        "fields": [
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
                "name": "phase",
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
                "name": "mass_density",
                "kind": "numeric",
                "axis_allowed": True,
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
        ],
        "display_units": {
            "temperature": ["K", "degC"],
            "pressure": ["Pa", "bar"],
        },
        "categorical_values": {"phase": ["gas", "liquid"]},
    }
    if inspected:
        visualization["series_fields"] = {
            "property_curves": ["pressure"],
            "pv": ["temperature"],
        }
        visualization["numeric_levels"] = {
            "pressure": {
                "count": 2,
                "choices": [
                    {"label": "1 bar", "value": 100_000.0},
                    {"label": "2 bar", "value": 200_000.0},
                ],
                "minimum_display": 1.0,
                "maximum_display": 2.0,
                "display_unit": "bar",
            }
        }
    return {
        "fluids": [
            {"name": "Propane", "aliases": ["R290"]},
            {"name": "Cyclopentane", "aliases": []},
        ],
        "visualization": visualization,
    }


def dataset() -> dict[str, object]:
    return {
        "mode": "property_table",
        "fluids": ["R290", "Cyclopentane"],
        "grid": {"temperature": {}, "pressure": {}},
        "properties": ["mass_density"],
    }


def curves_plot() -> dict[str, object]:
    return {
        "name": "density-curves",
        "kind": "property_curves",
        "property": "mass_density",
        "x": "temperature",
    }


def test_configured_and_manual_drafts_are_workflow_local() -> None:
    configured = PlotDraft(capabilities(), dataset(), curves_plot())
    manual = PlotDraft(
        capabilities(inspected=True),
        dataset(),
        curves_plot(),
        allow_format=False,
    )

    configured.set_name("configured")
    configured.series.add_row("pressure", "100000")

    assert manual.get_name() == "density-curves"
    assert manual.series.raw_rows() == ()
    assert "format" not in manual.payload()


def test_configured_context_does_not_require_inspection_extensions() -> None:
    draft = PlotDraft(capabilities(), dataset(), curves_plot())

    draft.series.add_row("pressure", "100000, 200000")

    assert draft.payload()["series"] == {"pressure": [100000.0, 200000.0]}


def test_inspection_levels_use_labels_but_return_canonical_si() -> None:
    draft = PlotDraft(capabilities(inspected=True), dataset(), curves_plot())

    draft.series.add_row("pressure", "1 bar, 2 bar")
    draft.filters.add_row("pressure", "1 bar")

    payload = draft.payload()
    assert payload["series"] == {"pressure": [100000.0, 200000.0]}
    assert payload["filters"] == {"pressure": 100000.0}


@pytest.mark.parametrize("raw", ["", "not-a-number", "nan", "inf"])
def test_numeric_mapping_rows_preserve_invalid_text(
    raw: str,
) -> None:
    model = MappingDraftModel()
    model.configure(["pressure"], field_kinds={"pressure": "numeric"})
    model.add_row("pressure", raw)

    assert model.raw_rows() == (("pressure", raw),)
    assert not model.get_valid()
    assert model.data(model.index(0, 0), FIELD_ROLE) == "pressure"
    assert model.data(model.index(0, 0), ISSUE_ROLE)
    assert model.get_first_invalid_row() == 0
    with pytest.raises(ValueError):
        model.mapping()


def test_duplicate_and_unsupported_mapping_rows_remain_visible() -> None:
    model = MappingDraftModel()
    model.configure(["pressure"], field_kinds={"pressure": "numeric"})
    model.add_row("pressure", "100000")
    model.add_row("pressure", "200000")

    assert "duplicate" in model.get_issue()
    model.set_field(1, "temperature")
    model.set_raw_value(1, "300")
    assert model.raw_rows()[1] == ("temperature", "300")
    assert "not available" in model.get_issue()


def test_non_applicable_values_are_retained_but_omitted() -> None:
    draft = PlotDraft(
        capabilities(),
        dataset(),
        {
            **curves_plot(),
            "series": {"pressure": [100000.0]},
            "value_scale": "log",
        },
    )

    draft.set_kind("property_heatmap")

    assert draft.series.raw_rows() == (("pressure", "100000"),)
    payload = draft.payload()
    assert "series" not in payload
    assert "value_scale" not in payload


@pytest.mark.parametrize(
    ("kind", "properties", "required"),
    [
        ("pv", ["specific_entropy"], "mass_density"),
        ("ts", ["mass_density"], "specific_entropy"),
    ],
)
def test_fixed_axis_plots_require_their_emitted_properties(
    kind: str,
    properties: list[str],
    required: str,
) -> None:
    payload = dataset()
    payload["properties"] = properties
    draft = PlotDraft(
        capabilities(),
        payload,
        {"name": "fixed-axes", "kind": kind},
    )

    assert not draft.get_locally_valid()
    assert required in draft.get_issue()
    assert draft.get_first_invalid_field() == PLOT_KIND
    assert draft.get_first_invalid_row() == -1


def test_context_refresh_preserves_raw_plot_state() -> None:
    draft = PlotDraft(capabilities(), dataset(), curves_plot())
    draft.filters.add_row("pressure", "not-a-number")
    replacement = dataset()
    replacement["properties"] = ["specific_entropy"]

    draft.refresh_context(capabilities(), replacement)

    assert draft.filters.raw_rows() == (("pressure", "not-a-number"),)
    assert draft.get_property_name() == "mass_density"
    assert not draft.get_locally_valid()


@pytest.mark.parametrize("name", ["Plot", "plot name", "plot--name", "plot-"])
def test_plot_names_use_the_public_pattern(
    name: str,
) -> None:
    draft = PlotDraft(capabilities(), dataset(), curves_plot())
    draft.set_name(name)

    assert not draft.get_locally_valid()
    assert "plot name" in draft.get_issue()
    assert draft.get_first_invalid_field() == PLOT_NAME


def test_plot_structured_issue_projects_scalar_and_mapping_rows() -> None:
    draft = PlotDraft(capabilities(), dataset(), curves_plot())
    draft.set_property_name("")

    assert draft.get_first_invalid_field() == plot_field("property")
    assert draft.get_first_invalid_row() == -1

    draft.set_property_name("mass_density")
    draft.filters.add_row("pressure", "not-a-number")

    assert draft.get_first_invalid_field() == PLOT_FILTERS
    assert draft.get_first_invalid_row() == 0


def test_gui_plot_draft_import_excludes_heavy_modules() -> None:
    code = """
import sys
import carnopy.app.plot_draft
for name in (
    "CoolProp", "numpy", "pandas", "pyarrow", "matplotlib",
    "carnopy.cli", "carnopy.pipeline", "carnopy.visualization.plots",
    "carnopy.visualization.render", "carnopy.app.plot_rendering",
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
