from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from carnopy.domain.properties import PROPERTY_REGISTRY
from carnopy.visualization.fields import FIELD_REGISTRY, format_unit, get_field
from carnopy.visualization.models import VisualizationError
from carnopy.visualization.requests import (
    ExactFilter,
    PlotRequest,
    property_plot_request,
    request_id,
)
from carnopy.visualization.selection import (
    dynamic_range_advisories,
    resolve_group_by,
    select_rows,
)


def test_field_registry_covers_properties_and_scientific_units() -> None:
    assert set(PROPERTY_REGISTRY) <= set(FIELD_REGISTRY)
    assert get_field("specific_volume").required_property == "mass_density"
    assert get_field("specific_volume").derivation == "reciprocal"
    assert get_field("phase").axis_allowed is False
    assert get_field("fluid").filter_allowed is False
    assert format_unit("kg/m^3") == r"$\mathrm{kg\,m^{-3}}$"
    assert "m^3" not in get_field("mass_density").display_label


def test_every_registered_unit_has_a_display_mapping() -> None:
    units = {definition.unit for definition in PROPERTY_REGISTRY.values()}
    for unit in units:
        assert format_unit(unit)


def test_request_identity_expands_defaults_and_preserves_order() -> None:
    implicit = PlotRequest(kind="property_curves", property_name="mass_density")
    explicit = PlotRequest(
        kind="property_curves",
        property_name="mass_density",
        value_scale="linear",
        color_scale="linear",
        x_scale="linear",
        y_scale="linear",
        output_format="png",
    )
    assert request_id((implicit,)) == request_id((explicit,))

    entropy = PlotRequest(kind="property_curves", property_name="specific_entropy")
    assert request_id((implicit, entropy)) != request_id((entropy, implicit))

    filters_first = PlotRequest(
        kind="xy",
        x_field="specific_enthalpy",
        y_field="vapor_mass_fraction",
        filters=(
            ExactFilter(field="pressure", value=100_000.0),
            ExactFilter(field="phase", value="gas"),
        ),
        fluids=("Propane", "Isobutane"),
    )
    filters_reordered = PlotRequest(
        kind="xy",
        x_field="specific_enthalpy",
        y_field="vapor_mass_fraction",
        filters=tuple(reversed(filters_first.filters)),
        fluids=tuple(reversed(filters_first.fluids)),
    )
    assert request_id((filters_first,)) == request_id((filters_reordered,))

    png = property_plot_request(
        property_name="mass_density",
        kind="property_curves",
        fluids=(),
        output_format="png",
    )
    pdf = png.model_copy(update={"output_format": "pdf"})
    assert request_id((png,)) != request_id((pdf,))


def test_filter_identity_canonicalizes_equivalent_values() -> None:
    uppercase = PlotRequest(
        kind="property_curves",
        property_name="mass_density",
        filters=(ExactFilter(field="phase", value=" GAS "),),
    )
    lowercase = PlotRequest(
        kind="property_curves",
        property_name="mass_density",
        filters=(ExactFilter(field="phase", value="gas"),),
    )
    numeric_text = PlotRequest(
        kind="property_curves",
        property_name="mass_density",
        filters=(ExactFilter(field="pressure", value="100000"),),
    )
    numeric_float = PlotRequest(
        kind="property_curves",
        property_name="mass_density",
        filters=(ExactFilter(field="pressure", value=100_000.0),),
    )
    assert request_id((uppercase,)) == request_id((lowercase,))
    assert request_id((numeric_text,)) == request_id((numeric_float,))


def test_plot_request_rejects_invalid_field_contracts() -> None:
    with pytest.raises(ValueError, match="requires property_name"):
        PlotRequest(kind="property_curves")
    with pytest.raises(ValueError, match="requires both"):
        PlotRequest(kind="xy", x_field="temperature")
    with pytest.raises(ValueError, match="fixed axes"):
        PlotRequest(kind="pv", x_field="specific_volume")
    with pytest.raises(ValueError, match="not supported for exact filters"):
        ExactFilter(field="mass_density", value=1.0)


def test_selection_applies_numeric_and_categorical_filters() -> None:
    frame = pd.DataFrame(
        {
            "fluid": ["Propane", "Propane", "Propane"],
            "pressure_Pa": [100_000.0, 200_000.0, 200_000.0],
            "phase": ["liquid", "gas", "gas"],
        }
    )
    result = select_rows(
        frame,
        filters=(
            ExactFilter(field="pressure", value=200_000.0),
            ExactFilter(field="phase", value="GAS"),
        ),
    )
    assert len(result.frame) == 2
    assert result.selected_fluids == ("Propane",)
    assert result.filter_matches[0].matched_values == (200_000.0,)
    assert result.filter_matches[1].matched_values == ("gas",)


def test_numeric_filter_uses_tolerance_without_nearest_selection() -> None:
    frame = pd.DataFrame(
        {
            "fluid": ["Propane", "Propane"],
            "pressure_Pa": [100_000.0, 100_001.0],
        }
    )
    result = select_rows(
        frame,
        filters=(ExactFilter(field="pressure", value=100_000.00001),),
    )
    assert result.frame["pressure_Pa"].tolist() == [100_000.0]

    with pytest.raises(VisualizationError, match="matches no rows"):
        select_rows(
            frame,
            filters=(ExactFilter(field="pressure", value=100_000.5),),
        )


def test_grouping_requires_explicit_resolution_when_ambiguous() -> None:
    frame = pd.DataFrame(
        {
            "temperature_K": [300.0, 310.0, 300.0, 310.0],
            "pressure_Pa": [100_000.0, 100_000.0, 200_000.0, 200_000.0],
            "vapor_mass_fraction": [0.0, 0.0, 1.0, 1.0],
        }
    )
    with pytest.raises(VisualizationError, match="ambiguous"):
        resolve_group_by(
            frame,
            axis_fields=("vapor_mass_fraction", "specific_enthalpy"),
            sampling_fields=("temperature", "pressure", "vapor_mass_fraction"),
            requested=None,
        )
    resolution = resolve_group_by(
        frame,
        axis_fields=("vapor_mass_fraction", "specific_enthalpy"),
        sampling_fields=("temperature", "pressure", "vapor_mass_fraction"),
        requested="pressure",
    )
    assert resolution.group_by == "pressure"
    assert resolution.varying_coordinate == "temperature"

    single = resolve_group_by(
        frame.loc[frame["pressure_Pa"] == 100_000.0],
        axis_fields=("vapor_mass_fraction", "specific_enthalpy"),
        sampling_fields=("temperature", "pressure", "vapor_mass_fraction"),
        requested=None,
    )
    assert single.group_by is None
    assert single.varying_coordinate == "temperature"


def test_dynamic_range_advisory_never_changes_scale() -> None:
    advisories = dynamic_range_advisories(
        [1.0, 100.0],
        scale="linear",
        subject="mass_density property",
    )
    assert len(advisories) == 1
    assert advisories[0].code == "large_linear_dynamic_range"
    assert advisories[0].dynamic_range_ratio == 100.0
    assert dynamic_range_advisories([1.0, 100.0], scale="log", subject="property") == ()
    assert dynamic_range_advisories([0.0, 100.0], scale="linear", subject="property") == ()


def test_visualization_foundation_does_not_import_coolprop() -> None:
    script = """
import sys
import carnopy.visualization.fields
import carnopy.visualization.plots
import carnopy.visualization.requests
import carnopy.visualization.selection
raise SystemExit("CoolProp" in sys.modules)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_generation_without_visualization_does_not_import_matplotlib(
    property_config_path: Path,
    tmp_path: Path,
) -> None:
    script = """
import sys
from carnopy.api import generate_dataset
generate_dataset(sys.argv[1], output_root=sys.argv[2])
raise SystemExit("matplotlib" in sys.modules)
"""
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(property_config_path),
            str(tmp_path / "subprocess-runs"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
