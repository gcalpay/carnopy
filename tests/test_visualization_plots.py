from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg", force=True)

from carnopy.api import generate_dataset
from carnopy.visualization import plot_dataset
from carnopy.visualization.models import VisualizationError


def _write_surface_config(path: Path, fluids: list[str] | None = None) -> Path:
    fluid_lines = "\n".join(f"  - {fluid}" for fluid in (fluids or ["Propane"]))
    path.write_text(
        f"""
schema_version: 1
backend: coolprop
mode: vapor_mass_fraction_table
fluids:
{fluid_lines}
grid:
  pressure:
    kind: explicit
    values: [1.0, 2.0]
    unit: bar
  vapor_mass_fraction:
    kind: explicit
    values: [0.0, 0.5, 1.0]
    unit: "1"
properties:
  - mass_density
  - specific_enthalpy
""",
        encoding="utf-8",
    )
    return path


def test_curves_export_image_sidecar_and_sampled_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _write_surface_config(tmp_path / "surface.yaml")
    run = generate_dataset(config, output_root=tmp_path / "runs")
    monkeypatch.chdir(tmp_path)
    before = {path.name for path in run.output_directory.iterdir()}
    result = plot_dataset(
        run.output_directory,
        property_name="mass_density",
        kind="curves",
    )
    after = {path.name for path in run.output_directory.iterdir()}
    assert before == after
    assert result.image_path.parent == tmp_path / "figures"
    assert result.image_path.is_file()
    assert result.sidecar_path.is_file()
    assert len(result.figure.axes[0].lines) == 2
    assert result.figure.axes[0].get_xlabel() == "Vapor mass fraction [-]"
    assert "Mass density" in result.figure.axes[0].get_ylabel()
    assert result.figure.axes[0].get_position().y0 > 0.1
    assert result.figure.axes[0].get_position().y1 < 0.9
    sidecar = json.loads(result.sidecar_path.read_text())
    assert sidecar["source"]["integrity"] == "verified"
    assert sidecar["image"]["sha256"]
    assert sidecar["settings"]["raster_dpi"] == 300


def test_contour_exports_pdf_and_uses_sample_overlay(tmp_path: Path) -> None:
    config = _write_surface_config(tmp_path / "surface.yaml")
    run = generate_dataset(config, output_root=tmp_path / "runs")
    output = tmp_path / "density.pdf"
    result = plot_dataset(
        run.output_directory,
        property_name="mass_density",
        kind="contour",
        output=output,
    )
    assert result.image_path == output
    assert result.sidecar_path == output.with_suffix(".plot.json")
    assert len(result.figure.axes[0].collections) >= 2
    sidecar = json.loads(result.sidecar_path.read_text())
    assert sidecar["settings"]["contour_levels"] == 20
    assert sidecar["settings"]["sample_point_overlay"] is True


def test_multi_fluid_requires_selection_and_uses_facets(tmp_path: Path) -> None:
    config = _write_surface_config(tmp_path / "multi.yaml", ["Propane", "Isobutane"])
    run = generate_dataset(config, output_root=tmp_path / "runs")
    with pytest.raises(VisualizationError, match="multiple fluids"):
        plot_dataset(run.output_directory, property_name="mass_density")
    result = plot_dataset(
        run.output_directory,
        property_name="mass_density",
        fluids=["n-Propane", "IsoButane"],
        output=tmp_path / "multi.svg",
    )
    facet_titles = [axis.get_title() for axis in result.figure.axes[:2]]
    assert facet_titles == ["n-Propane", "IsoButane"]
    assert result.selected_fluids == ("n-Propane", "IsoButane")


def test_log_scale_rejects_nonpositive_values(
    tmp_path: Path,
    vapor_config_path: Path,
) -> None:
    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    frame = pd.read_csv(run.output_directory / "dataset.csv")
    frame.loc[0, "mass_density_kg_m3"] = 0.0
    standalone = tmp_path / "nonpositive.csv"
    frame.to_csv(standalone, index=False)
    with pytest.raises(VisualizationError, match="requires positive"):
        plot_dataset(
            standalone,
            property_name="mass_density",
            scale="log",
            coordinate="temperature",
            output=tmp_path / "log.png",
        )


def test_invalid_rows_remain_curve_gaps(
    tmp_path: Path,
    vapor_config_path: Path,
) -> None:
    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    frame = pd.read_csv(run.output_directory / "dataset.csv")
    frame.loc[1, "valid"] = False
    standalone = tmp_path / "gap.csv"
    frame.to_csv(standalone, index=False)
    result = plot_dataset(
        standalone,
        property_name="mass_density",
        coordinate="temperature",
        output=tmp_path / "gap.png",
    )
    y_values = np.asarray(result.figure.axes[0].lines[0].get_ydata(), dtype=float)
    assert np.isnan(y_values[1])
    assert result.invalid_rows_excluded == 1


def test_all_invalid_and_absent_property_fail(
    tmp_path: Path,
    vapor_config_path: Path,
) -> None:
    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    with pytest.raises(VisualizationError, match="not present"):
        plot_dataset(
            run.output_directory,
            property_name="thermal_conductivity",
            output=tmp_path / "missing.png",
        )
    frame = pd.read_csv(run.output_directory / "dataset.csv")
    frame["valid"] = False
    standalone = tmp_path / "all-invalid.csv"
    frame.to_csv(standalone, index=False)
    with pytest.raises(VisualizationError, match="no valid"):
        plot_dataset(
            standalone,
            property_name="mass_density",
            coordinate="temperature",
            output=tmp_path / "invalid.png",
        )


def test_show_occurs_after_export(
    tmp_path: Path,
    vapor_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import matplotlib.pyplot as plt

    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    output = tmp_path / "shown.png"
    calls: list[bool] = []

    def record_show() -> None:
        calls.append(output.is_file())

    monkeypatch.setattr(plt, "show", record_show)
    plot_dataset(
        run.output_directory,
        property_name="mass_density",
        output=output,
        show=True,
    )
    assert calls == [True]


def test_output_inside_immutable_run_is_rejected(
    tmp_path: Path,
    vapor_config_path: Path,
) -> None:
    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    with pytest.raises(VisualizationError, match="immutable"):
        plot_dataset(
            run.output_directory,
            property_name="mass_density",
            output=run.output_directory / "plot.png",
        )
