from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg", force=True)

from carnopy.api import generate_dataset
from carnopy.visualization import (
    plot_dataset,
    plot_thermodynamic_diagram,
    plot_xy,
)
from carnopy.visualization.models import VisualizationError


@pytest.fixture(autouse=True)
def _close_figures_after_test() -> Iterator[None]:
    yield
    import matplotlib.pyplot as plt

    plt.close("all")


def _write_diagram_config(
    path: Path,
    *,
    mode: str,
    temperatures: tuple[float, ...] = (250.0, 260.0, 270.0),
    pressures_bar: tuple[float, ...] = (1.0, 2.0, 3.0),
    qualities: tuple[float, ...] = (0.0, 0.5, 1.0),
) -> Path:
    if mode == "property_table":
        grid = f"""
  temperature:
    kind: explicit
    values: {list(temperatures)}
    unit: K
  pressure:
    kind: explicit
    values: {list(pressures_bar)}
    unit: bar
"""
    elif mode == "saturation_table":
        grid = f"""
  temperature:
    kind: explicit
    values: {list(temperatures)}
    unit: K
"""
    else:
        grid = f"""
  pressure:
    kind: explicit
    values: {list(pressures_bar)}
    unit: bar
  vapor_mass_fraction:
    kind: explicit
    values: {list(qualities)}
    unit: "1"
"""
    path.write_text(
        f"""
schema_version: 2
document_type: dataset
backend:
  name: coolprop
  model: heos
mode: {mode}
fluids: [Propane]
grid:
{grid.rstrip()}
properties:
  - mass_density
  - specific_enthalpy
  - specific_entropy
""",
        encoding="utf-8",
    )
    return path


def test_xy_auto_groups_single_remaining_sampling_coordinate(
    tmp_path: Path,
) -> None:
    run = generate_dataset(
        _write_diagram_config(
            tmp_path / "vapor.yaml",
            mode="vapor_mass_fraction_table",
            pressures_bar=(1.0, 2.0),
        ),
        output_root=tmp_path / "runs",
    )
    result = plot_xy(
        run.output_directory,
        x="specific_enthalpy",
        y="vapor_mass_fraction",
        output=tmp_path / "xy.png",
    )
    lines = result.figure.axes[0].lines
    assert len(lines) == 2
    assert all(line.get_marker() == "o" for line in lines)
    assert result.effective_settings["group_by"] == "pressure"
    frame = pd.read_parquet(run.output_directory / "dataset.parquet")
    expected = frame.loc[frame["pressure_Pa"] == 100_000.0].sort_values("vapor_mass_fraction")
    np.testing.assert_allclose(
        np.asarray(lines[0].get_xdata(), dtype=float),
        expected["specific_enthalpy_J_kg"].to_numpy(dtype=float),
        rtol=0.0,
        atol=0.0,
    )
    np.testing.assert_allclose(
        np.asarray(lines[0].get_ydata(), dtype=float),
        expected["vapor_mass_fraction"].to_numpy(dtype=float),
        rtol=0.0,
        atol=0.0,
    )


def test_xy_requires_grouping_when_two_sampling_coordinates_remain(
    tmp_path: Path,
) -> None:
    run = generate_dataset(
        _write_diagram_config(tmp_path / "property.yaml", mode="property_table"),
        output_root=tmp_path / "runs",
    )
    with pytest.raises(VisualizationError, match="ambiguous"):
        plot_xy(
            run.output_directory,
            x="specific_enthalpy",
            y="specific_entropy",
            output=tmp_path / "ambiguous.png",
        )
    result = plot_xy(
        run.output_directory,
        x="specific_enthalpy",
        y="specific_entropy",
        group_by="pressure",
        output=tmp_path / "isobars.png",
    )
    assert len(result.figure.axes[0].lines) == 3
    assert result.effective_settings["group_by"] == "pressure"
    assert result.effective_settings["path_coordinate"] == "temperature"


def test_xy_without_remaining_sampling_coordinate_uses_markers_only(
    tmp_path: Path,
) -> None:
    run = generate_dataset(
        _write_diagram_config(
            tmp_path / "property.yaml",
            mode="property_table",
            temperatures=(250.0,),
            pressures_bar=(1.0,),
        ),
        output_root=tmp_path / "runs",
    )
    result = plot_xy(
        run.output_directory,
        x="specific_enthalpy",
        y="specific_entropy",
        output=tmp_path / "marker.png",
    )
    line = result.figure.axes[0].lines[0]
    assert line.get_linestyle() == "None"
    assert line.get_marker() == "o"


def test_xy_single_varying_sampling_coordinate_forms_one_ordered_series(
    tmp_path: Path,
) -> None:
    run = generate_dataset(
        _write_diagram_config(
            tmp_path / "property.yaml",
            mode="property_table",
            pressures_bar=(1.0,),
        ),
        output_root=tmp_path / "runs",
    )
    result = plot_xy(
        run.output_directory,
        x="specific_enthalpy",
        y="specific_entropy",
        output=tmp_path / "single-path.png",
    )
    line = result.figure.axes[0].lines[0]
    assert len(line.get_xdata()) == 3
    assert line.get_linestyle() != "None"
    assert result.effective_settings["group_by"] is None
    assert result.effective_settings["path_coordinate"] == "temperature"


def test_saturation_xy_keeps_endpoint_branches_separate(tmp_path: Path) -> None:
    run = generate_dataset(
        _write_diagram_config(tmp_path / "saturation.yaml", mode="saturation_table"),
        output_root=tmp_path / "runs",
    )
    result = plot_xy(
        run.output_directory,
        x="specific_enthalpy",
        y="pressure",
        output=tmp_path / "saturation-xy.png",
    )
    assert {line.get_label() for line in result.figure.axes[0].lines} == {
        "saturated liquid",
        "saturated vapor",
    }
    with pytest.raises(VisualizationError, match="saturation_endpoint"):
        plot_xy(
            run.output_directory,
            x="specific_enthalpy",
            y="pressure",
            group_by="temperature",
            output=tmp_path / "unsafe-grouping.png",
        )


def test_pv_property_table_uses_exact_reciprocal_density_and_isotherms(
    tmp_path: Path,
) -> None:
    run = generate_dataset(
        _write_diagram_config(tmp_path / "property.yaml", mode="property_table"),
        output_root=tmp_path / "runs",
    )
    result = plot_thermodynamic_diagram(
        run.output_directory,
        kind="pv",
        output=tmp_path / "pv.png",
    )
    lines = result.figure.axes[0].lines
    assert len(lines) == 3
    assert "m^{3}" in result.figure.axes[0].get_xlabel()
    assert "Pressure" in result.figure.axes[0].get_ylabel()
    frame = pd.read_parquet(run.output_directory / "dataset.parquet")
    expected = frame.loc[frame["temperature_K"] == 250.0].sort_values("pressure_Pa")
    actual_volume = np.asarray(lines[0].get_xdata(), dtype=float)
    actual_pressure = np.asarray(lines[0].get_ydata(), dtype=float)
    assert np.isnan(actual_volume).any()
    np.testing.assert_allclose(
        actual_volume[np.isfinite(actual_volume)],
        1.0 / expected["mass_density_kg_m3"].to_numpy(dtype=float),
        rtol=1e-15,
        atol=0.0,
    )
    np.testing.assert_allclose(
        actual_pressure[np.isfinite(actual_pressure)],
        expected["pressure_Pa"].to_numpy(dtype=float),
        rtol=0.0,
        atol=0.0,
    )


def test_ts_property_table_uses_emitted_entropy_and_reference_policy(
    tmp_path: Path,
) -> None:
    run = generate_dataset(
        _write_diagram_config(tmp_path / "property.yaml", mode="property_table"),
        output_root=tmp_path / "runs",
    )
    result = plot_thermodynamic_diagram(
        run.output_directory,
        kind="ts",
        output=tmp_path / "ts.png",
    )
    lines = result.figure.axes[0].lines
    assert len(lines) == 3
    frame = pd.read_parquet(run.output_directory / "dataset.parquet")
    expected = frame.loc[frame["pressure_Pa"] == 100_000.0].sort_values("temperature_K")
    np.testing.assert_allclose(
        np.asarray(lines[0].get_xdata(), dtype=float),
        expected["specific_entropy_J_kgK"].to_numpy(dtype=float),
        rtol=0.0,
        atol=0.0,
    )
    np.testing.assert_allclose(
        np.asarray(lines[0].get_ydata(), dtype=float),
        expected["temperature_K"].to_numpy(dtype=float),
        rtol=0.0,
        atol=0.0,
    )
    assert "Reference state: coolprop_DEF" in result.figure.texts[-1].get_text()
    sidecar = json.loads(result.sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["plot_kind"] == "ts"
    assert sidecar["source_identity"]["reference_state_policy"] == "coolprop_DEF"
    assert sidecar["axes"]["x"]["field"] == "specific_entropy"
    assert sidecar["axes"]["y"]["field"] == "temperature"


@pytest.mark.parametrize("kind", ["pv", "ts"])
def test_saturation_diagrams_keep_liquid_and_vapor_branches_separate(
    tmp_path: Path,
    kind: str,
) -> None:
    run = generate_dataset(
        _write_diagram_config(tmp_path / "saturation.yaml", mode="saturation_table"),
        output_root=tmp_path / "runs",
    )
    result = plot_thermodynamic_diagram(
        run.output_directory,
        kind=kind,  # type: ignore[arg-type]
        output=tmp_path / f"{kind}.png",
    )
    assert len(result.figure.axes[0].lines) == 2
    assert {line.get_label() for line in result.figure.axes[0].lines} == {
        "saturated liquid",
        "saturated vapor",
    }


def test_vapor_diagram_adds_quality_lines_and_sampled_boundary_branches(
    tmp_path: Path,
) -> None:
    run = generate_dataset(
        _write_diagram_config(
            tmp_path / "vapor.yaml",
            mode="vapor_mass_fraction_table",
            pressures_bar=(1.0, 2.0),
        ),
        output_root=tmp_path / "runs",
    )
    result = plot_thermodynamic_diagram(
        run.output_directory,
        kind="pv",
        output=tmp_path / "vapor-pv.png",
    )
    labels = [line.get_label() for line in result.figure.axes[0].lines]
    assert len(labels) == 4
    assert r"$x_{\mathrm{vap}}$ = 0 boundary" in labels
    assert r"$x_{\mathrm{vap}}$ = 1 boundary" in labels


def test_diagram_invalid_sample_remains_a_gap(tmp_path: Path) -> None:
    run = generate_dataset(
        _write_diagram_config(
            tmp_path / "vapor.yaml",
            mode="vapor_mass_fraction_table",
            pressures_bar=(1.0, 2.0),
        ),
        output_root=tmp_path / "runs",
    )
    frame = pd.read_csv(run.output_directory / "dataset.csv")
    invalid = (frame["pressure_Pa"] == 100_000.0) & (frame["vapor_mass_fraction"] == 0.5)
    frame.loc[invalid, "valid"] = False
    standalone = tmp_path / "gap.csv"
    frame.to_csv(standalone, index=False)
    result = plot_thermodynamic_diagram(
        standalone,
        kind="pv",
        saturation_coordinate="pressure",
        output=tmp_path / "gap-pv.png",
    )
    first_line_x = np.asarray(result.figure.axes[0].lines[0].get_xdata(), dtype=float)
    assert np.isnan(first_line_x[1])
    assert result.invalid_rows_excluded == 1


def test_ts_standalone_source_requires_reference_metadata(
    tmp_path: Path,
) -> None:
    run = generate_dataset(
        _write_diagram_config(tmp_path / "property.yaml", mode="property_table"),
        output_root=tmp_path / "runs",
    )
    standalone = tmp_path / "standalone.csv"
    standalone.write_bytes((run.output_directory / "dataset.csv").read_bytes())
    with pytest.raises(VisualizationError, match="reference_state_policy"):
        plot_thermodynamic_diagram(
            standalone,
            kind="ts",
            output=tmp_path / "standalone-ts.png",
        )


def test_standalone_vapor_diagram_accepts_explicit_saturation_coordinate(
    tmp_path: Path,
) -> None:
    run = generate_dataset(
        _write_diagram_config(tmp_path / "vapor.yaml", mode="vapor_mass_fraction_table"),
        output_root=tmp_path / "runs",
    )
    standalone = tmp_path / "standalone.csv"
    standalone.write_bytes((run.output_directory / "dataset.csv").read_bytes())
    result = plot_thermodynamic_diagram(
        standalone,
        kind="pv",
        saturation_coordinate="pressure",
        output=tmp_path / "standalone-pv.png",
    )
    assert result.source_integrity == "unverified"


def test_diagram_log_scale_rejects_nonpositive_axis_values(
    tmp_path: Path,
) -> None:
    run = generate_dataset(
        _write_diagram_config(tmp_path / "property.yaml", mode="property_table"),
        output_root=tmp_path / "runs",
    )
    frame = pd.read_csv(run.output_directory / "dataset.csv")
    frame.loc[0, "specific_entropy_J_kgK"] = 0.0
    standalone = tmp_path / "nonpositive.csv"
    frame.to_csv(standalone, index=False)
    with pytest.raises(VisualizationError, match="positive specific_entropy"):
        plot_dataset(
            standalone,
            kind="xy",
            x="specific_entropy",
            y="temperature",
            group_by="pressure",
            x_scale="log",
            output=tmp_path / "log.png",
        )


def test_fixed_diagram_dispatch_rejects_custom_axes(
    property_config_path: Path,
    tmp_path: Path,
) -> None:
    run = generate_dataset(property_config_path, output_root=tmp_path / "runs")
    with pytest.raises(VisualizationError, match="fixed axes"):
        plot_dataset(
            run.output_directory,
            kind="pv",
            x="pressure",
            output=tmp_path / "invalid.png",
        )
