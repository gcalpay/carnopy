from __future__ import annotations

import errno
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg", force=True)

from carnopy.api import generate_dataset
from carnopy.provenance import sha256_file
from carnopy.visualization import (
    plot_dataset,
    plot_property_curves,
    plot_property_heatmap,
)
from carnopy.visualization.models import VisualizationError
from carnopy.visualization.requests import ExactFilter


@pytest.fixture(autouse=True)
def _close_figures_after_test() -> Iterator[None]:
    yield
    import matplotlib.pyplot as plt

    plt.close("all")


def _write_config(
    path: Path,
    *,
    mode: str,
    fluids: tuple[str, ...] = ("Propane",),
    temperatures: tuple[float, ...] = (250.0, 260.0, 270.0),
    pressures_bar: tuple[float, ...] = (1.0, 2.0, 3.0),
    qualities: tuple[float, ...] = (0.0, 0.5, 1.0),
) -> Path:
    fluid_text = ", ".join(fluids)
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
fluids: [{fluid_text}]
grid:
{grid.rstrip()}
properties:
  - mass_density
  - specific_enthalpy
""",
        encoding="utf-8",
    )
    return path


def test_vapor_property_curves_use_discrete_series_markers_and_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _write_config(tmp_path / "vapor.yaml", mode="vapor_mass_fraction_table")
    run = generate_dataset(config, output_root=tmp_path / "runs")
    monkeypatch.chdir(tmp_path)
    before = {path.name for path in run.output_directory.iterdir()}
    result = plot_dataset(
        run.output_directory,
        kind="property-curves",
        property_name="mass_density",
    )
    assert before == {path.name for path in run.output_directory.iterdir()}
    assert result.kind == "property_curves"
    assert len(result.figure.axes[0].lines) == 3
    assert all(line.get_marker() == "o" for line in result.figure.axes[0].lines)
    assert len({line.get_color() for line in result.figure.axes[0].lines}) == 3
    assert result.figure.axes[0].get_legend() is not None
    assert "Vapor mass fraction" in result.figure.axes[0].get_xlabel()
    assert "m^{-3}" in result.figure.axes[0].get_ylabel()
    assert "^" not in result.figure.axes[0].get_ylabel().replace("^{-3}", "")
    sidecar = json.loads(result.sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["plot_schema_version"] == 2
    assert sidecar["plot_kind"] == "property_curves"
    assert sidecar["series_or_cells"]["representation"] == "sampled_series"
    assert sidecar["effective_settings"]["palette"] == "tab10"
    assert sidecar["effective_settings"]["smoothing"] is False
    assert any(advisory["code"] == "sparse_sampled_series" for advisory in sidecar["advisories"])
    assert sidecar["source_identity"]["dataset_sha256"] == sha256_file(
        run.output_directory / "dataset.parquet"
    )
    assert sidecar["image"]["sha256"] == sha256_file(result.image_path)
    frame = pd.read_parquet(run.output_directory / "dataset.parquet")
    expected = (
        frame.loc[frame["pressure_Pa"] == 100_000.0]
        .sort_values("vapor_mass_fraction")["mass_density_kg_m3"]
        .to_numpy(dtype=float)
    )
    np.testing.assert_allclose(
        np.asarray(result.figure.axes[0].lines[0].get_ydata(), dtype=float),
        expected,
        rtol=0.0,
        atol=0.0,
    )


def test_property_table_curves_require_explicit_x_and_group_by_other_coordinate(
    tmp_path: Path,
) -> None:
    run = generate_dataset(
        _write_config(tmp_path / "property.yaml", mode="property_table"),
        output_root=tmp_path / "runs",
    )
    with pytest.raises(VisualizationError, match="requires --x"):
        plot_property_curves(
            run.output_directory,
            property_name="mass_density",
            output=tmp_path / "missing-x.png",
        )
    result = plot_property_curves(
        run.output_directory,
        property_name="mass_density",
        x="temperature",
        output=tmp_path / "property-curves.png",
    )
    assert len(result.figure.axes[0].lines) == 3
    assert "Temperature" in result.figure.axes[0].get_xlabel()
    legend = result.figure.axes[0].get_legend()
    assert legend is not None
    assert "Pressure" in legend.get_title().get_text()


def test_property_curves_select_unit_bearing_series_and_convert_display_units(
    tmp_path: Path,
) -> None:
    run = generate_dataset(
        _write_config(tmp_path / "property.yaml", mode="property_table"),
        output_root=tmp_path / "runs",
    )
    result = plot_property_curves(
        run.output_directory,
        property_name="specific_enthalpy",
        x="temperature",
        series={"pressure": ("1bar", "3bar")},
        display_units={
            "temperature": "degC",
            "pressure": "bar",
            "specific_enthalpy": "kJ/kg",
        },
        output=tmp_path / "selected-units.png",
    )
    assert len(result.figure.axes[0].lines) == 2
    np.testing.assert_allclose(
        np.asarray(result.figure.axes[0].lines[0].get_xdata(), dtype=float),
        np.asarray([-23.15, -13.15, -3.15]),
        rtol=0.0,
        atol=1e-12,
    )
    frame = pd.read_parquet(run.output_directory / "dataset.parquet")
    expected = (
        frame.loc[frame["pressure_Pa"] == 100_000.0]
        .sort_values("temperature_K")["specific_enthalpy_J_kg"]
        .to_numpy(dtype=float)
        / 1_000.0
    )
    np.testing.assert_allclose(
        np.asarray(result.figure.axes[0].lines[0].get_ydata(), dtype=float),
        expected,
        rtol=0.0,
        atol=0.0,
    )
    assert "kJ" in result.figure.axes[0].get_ylabel()
    assert r"^\circ" in result.figure.axes[0].get_xlabel()
    legend_labels = {text.get_text() for text in result.figure.axes[0].get_legend().get_texts()}
    assert legend_labels == {r"$p$ = 1 bar", r"$p$ = 3 bar"}
    sidecar = json.loads(result.sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["normalized_request"]["series"] == [
        {"field": "pressure", "values": [100000.0, 300000.0]}
    ]
    assert sidecar["axes"]["y"]["unit"] == "kJ/kg"


def test_property_curves_reject_missing_or_wrong_series_levels(tmp_path: Path) -> None:
    run = generate_dataset(
        _write_config(tmp_path / "property.yaml", mode="property_table"),
        output_root=tmp_path / "runs",
    )
    with pytest.raises(VisualizationError, match="available levels"):
        plot_property_curves(
            run.output_directory,
            property_name="mass_density",
            x="temperature",
            series={"pressure": ("9bar",)},
            output=tmp_path / "missing-series.png",
        )
    with pytest.raises(VisualizationError, match="uses 'pressure' as its series field"):
        plot_property_curves(
            run.output_directory,
            property_name="mass_density",
            x="temperature",
            series={"temperature": ("250K",)},
            output=tmp_path / "wrong-series.png",
        )


def test_saturation_curves_render_two_unconnected_endpoint_branches(
    tmp_path: Path,
) -> None:
    run = generate_dataset(
        _write_config(tmp_path / "saturation.yaml", mode="saturation_table"),
        output_root=tmp_path / "runs",
    )
    result = plot_property_curves(
        run.output_directory,
        property_name="mass_density",
        output=tmp_path / "saturation.png",
    )
    lines = result.figure.axes[0].lines
    assert len(lines) == 2
    assert {line.get_label() for line in lines} == {
        "saturated liquid",
        "saturated vapor",
    }
    assert all(len(line.get_xdata()) == 3 for line in lines)


def test_property_table_curves_split_at_phase_changes(tmp_path: Path) -> None:
    run = generate_dataset(
        _write_config(tmp_path / "property.yaml", mode="property_table"),
        output_root=tmp_path / "runs",
    )
    frame = pd.read_csv(run.output_directory / "dataset.csv")
    first_pressure = frame["pressure_Pa"] == 100_000.0
    frame.loc[first_pressure, "phase"] = ["gas", "liquid", "gas"]
    standalone = tmp_path / "phase-change.csv"
    frame.to_csv(standalone, index=False)
    result = plot_property_curves(
        standalone,
        property_name="mass_density",
        x="temperature",
        output=tmp_path / "phase-change.png",
    )
    y_values = np.asarray(result.figure.axes[0].lines[0].get_ydata(), dtype=float)
    assert int(np.isnan(y_values).sum()) == 2


def test_property_curves_preserve_descending_sampler_order(tmp_path: Path) -> None:
    run = generate_dataset(
        _write_config(
            tmp_path / "descending.yaml",
            mode="property_table",
            temperatures=(270.0, 260.0, 250.0),
        ),
        output_root=tmp_path / "runs",
    )
    result = plot_property_curves(
        run.output_directory,
        property_name="mass_density",
        x="temperature",
        output=tmp_path / "descending.png",
    )
    np.testing.assert_array_equal(
        np.asarray(result.figure.axes[0].lines[0].get_xdata(), dtype=float),
        np.asarray([270.0, 260.0, 250.0]),
    )


def test_property_heatmap_uses_sampled_flat_cells_and_masks_invalid_state(
    tmp_path: Path,
) -> None:
    run = generate_dataset(
        _write_config(tmp_path / "vapor.yaml", mode="vapor_mass_fraction_table"),
        output_root=tmp_path / "runs",
    )
    frame = pd.read_csv(run.output_directory / "dataset.csv")
    interior = (frame["pressure_Pa"] == 200_000.0) & (frame["vapor_mass_fraction"] == 0.5)
    frame.loc[interior, "valid"] = False
    standalone = tmp_path / "masked.csv"
    frame.to_csv(standalone, index=False)
    result = plot_property_heatmap(
        standalone,
        property_name="mass_density",
        saturation_coordinate="pressure",
        output=tmp_path / "heatmap.png",
    )
    sidecar = json.loads(result.sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["plot_kind"] == "property_heatmap"
    assert sidecar["effective_settings"]["shading"] == "flat"
    assert sidecar["effective_settings"]["interpolation"] is False
    cells = sidecar["series_or_cells"]["cells"]["n-Propane"]
    assert cells["masked_cell_count"] == 1
    assert cells["sampled_cell_count"] == 9
    assert not any(
        collection.__class__.__name__.startswith("QuadContour")
        for collection in result.figure.axes[0].collections
    )
    mesh_values = np.ma.asarray(result.figure.axes[0].collections[0].get_array())
    emitted = pd.to_numeric(
        frame.loc[~interior, "mass_density_kg_m3"],
        errors="coerce",
    ).to_numpy(dtype=float)
    np.testing.assert_allclose(
        np.sort(mesh_values.compressed()),
        np.sort(emitted),
        rtol=0.0,
        atol=0.0,
    )


def test_property_table_heatmap_uses_temperature_and_pressure_axes(
    tmp_path: Path,
) -> None:
    run = generate_dataset(
        _write_config(tmp_path / "property.yaml", mode="property_table"),
        output_root=tmp_path / "runs",
    )
    result = plot_property_heatmap(
        run.output_directory,
        property_name="mass_density",
        output=tmp_path / "property-heatmap.png",
    )
    sidecar = json.loads(result.sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["axes"]["x"]["field"] == "temperature"
    assert sidecar["axes"]["y"]["field"] == "pressure"
    assert sidecar["axes"]["color"]["field"] == "mass_density"


def test_multifluid_heatmaps_share_color_normalization(tmp_path: Path) -> None:
    run = generate_dataset(
        _write_config(
            tmp_path / "multi-heatmap.yaml",
            mode="vapor_mass_fraction_table",
            fluids=("Propane", "Isobutane"),
        ),
        output_root=tmp_path / "runs",
    )
    result = plot_property_heatmap(
        run.output_directory,
        property_name="mass_density",
        fluids=["n-Propane", "IsoButane"],
        output=tmp_path / "multi-heatmap.png",
    )
    first_norm = result.figure.axes[0].collections[0].norm
    second_norm = result.figure.axes[1].collections[0].norm
    assert first_norm.vmin == second_norm.vmin
    assert first_norm.vmax == second_norm.vmax


def test_property_heatmap_rejects_saturation_and_one_dimensional_sources(
    tmp_path: Path,
) -> None:
    saturation = generate_dataset(
        _write_config(tmp_path / "saturation.yaml", mode="saturation_table"),
        output_root=tmp_path / "sat-runs",
    )
    with pytest.raises(VisualizationError, match="does not support property_heatmap"):
        plot_property_heatmap(
            saturation.output_directory,
            property_name="mass_density",
            output=tmp_path / "sat.png",
        )
    one_dimensional = generate_dataset(
        _write_config(
            tmp_path / "one-dimensional.yaml",
            mode="vapor_mass_fraction_table",
            pressures_bar=(1.0,),
        ),
        output_root=tmp_path / "one-runs",
    )
    with pytest.raises(VisualizationError, match="at least two unique x values"):
        plot_property_heatmap(
            one_dimensional.output_directory,
            property_name="mass_density",
            output=tmp_path / "one.png",
        )


@pytest.mark.parametrize(
    ("kind", "message"),
    [
        ("curves", "replaced by 'property-curves'"),
        ("heatmap", "Use --kind property-heatmap"),
        ("contour", "Contour plots interpolate"),
    ],
)
def test_legacy_plot_kinds_are_rejected_with_migration_guidance(
    vapor_config_path: Path,
    tmp_path: Path,
    kind: str,
    message: str,
) -> None:
    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    with pytest.raises(VisualizationError, match=message):
        plot_dataset(
            run.output_directory,
            kind=kind,
            property_name="mass_density",
            output=tmp_path / f"{kind}.png",
        )


def test_dispatch_rejects_plot_kind_specific_options_instead_of_ignoring_them(
    vapor_config_path: Path,
    tmp_path: Path,
) -> None:
    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    with pytest.raises(VisualizationError, match="color_scale"):
        plot_dataset(
            run.output_directory,
            kind="property-curves",
            property_name="mass_density",
            color_scale="log",
        )
    with pytest.raises(VisualizationError, match="rejects x"):
        plot_dataset(
            run.output_directory,
            kind="property-heatmap",
            property_name="mass_density",
            x="temperature",
        )


def test_exact_filter_is_recorded_and_limits_curve_family(tmp_path: Path) -> None:
    run = generate_dataset(
        _write_config(tmp_path / "vapor.yaml", mode="vapor_mass_fraction_table"),
        output_root=tmp_path / "runs",
    )
    result = plot_property_curves(
        run.output_directory,
        property_name="mass_density",
        filters=(ExactFilter(field="pressure", value=200_000.0),),
        output=tmp_path / "filtered.png",
    )
    assert len(result.figure.axes[0].lines) == 1
    sidecar = json.loads(result.sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["data_selection"]["filters"] == [
        {
            "field": "pressure",
            "requested_value": 200_000.0,
            "matched_values": [200_000.0],
        }
    ]


def test_multi_fluid_requires_selection_and_uses_facets(tmp_path: Path) -> None:
    run = generate_dataset(
        _write_config(
            tmp_path / "multi.yaml",
            mode="vapor_mass_fraction_table",
            fluids=("Propane", "Isobutane"),
        ),
        output_root=tmp_path / "runs",
    )
    with pytest.raises(VisualizationError, match="multiple fluids"):
        plot_property_curves(
            run.output_directory,
            property_name="mass_density",
            output=tmp_path / "missing-selection.png",
        )
    result = plot_property_curves(
        run.output_directory,
        property_name="mass_density",
        fluids=["n-Propane", "IsoButane"],
        output=tmp_path / "multi.svg",
    )
    assert [axis.get_title() for axis in result.figure.axes[:2]] == [
        "IsoButane",
        "n-Propane",
    ]


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
        plot_property_curves(
            standalone,
            property_name="mass_density",
            value_scale="log",
            saturation_coordinate="temperature",
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
    result = plot_property_curves(
        standalone,
        property_name="mass_density",
        saturation_coordinate="temperature",
        output=tmp_path / "gap.png",
    )
    y_values = np.asarray(result.figure.axes[0].lines[0].get_ydata(), dtype=float)
    assert np.isnan(y_values[1])
    assert result.invalid_rows_excluded == 1


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
    plot_property_curves(
        run.output_directory,
        property_name="mass_density",
        output=output,
        show=True,
    )
    assert calls == [True]


def test_output_format_changes_request_identity_and_pdf_exports(
    tmp_path: Path,
    vapor_config_path: Path,
) -> None:
    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    png = plot_property_curves(
        run.output_directory,
        property_name="mass_density",
        output=tmp_path / "density.png",
    )
    pdf = plot_property_curves(
        run.output_directory,
        property_name="mass_density",
        output=tmp_path / "density-pdf.pdf",
    )
    assert png.visualization_request_id != pdf.visualization_request_id
    sidecar = json.loads(pdf.sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["image"]["format"] == "pdf"


def test_plot_execution_in_fresh_process_does_not_import_coolprop(
    tmp_path: Path,
    vapor_config_path: Path,
) -> None:
    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    script = """
import sys
from carnopy.visualization import plot_property_curves
plot_property_curves(sys.argv[1], property_name="mass_density", output=sys.argv[2])
raise SystemExit("CoolProp" in sys.modules)
"""
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(run.output_directory),
            str(tmp_path / "subprocess-plot.png"),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "MPLBACKEND": "Agg", "MPLCONFIGDIR": str(tmp_path / "mpl-subprocess")},
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.parametrize("existing_kind", ["image", "sidecar"])
def test_existing_plot_artifact_is_preserved(
    tmp_path: Path,
    vapor_config_path: Path,
    existing_kind: str,
) -> None:
    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    output = tmp_path / "density.png"
    existing = output if existing_kind == "image" else output.with_suffix(".plot.json")
    existing.write_bytes(b"external-content")
    with pytest.raises(VisualizationError, match="refusing to overwrite"):
        plot_property_curves(
            run.output_directory,
            property_name="mass_density",
            output=output,
        )
    assert existing.read_bytes() == b"external-content"


def test_second_link_failure_rolls_back_new_image_and_temporary_files(
    tmp_path: Path,
    vapor_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import carnopy.visualization.export as export_module

    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    output = tmp_path / "density.png"
    real_link = os.link
    calls = 0

    def fail_second_link(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError(errno.EIO, "controlled sidecar link failure")
        real_link(source, destination)

    monkeypatch.setattr(export_module.os, "link", fail_second_link)
    with pytest.raises(VisualizationError, match="could not export plot artifacts"):
        plot_property_curves(
            run.output_directory,
            property_name="mass_density",
            output=output,
        )
    assert not output.exists()
    assert not output.with_suffix(".plot.json").exists()
    assert not [path for path in tmp_path.iterdir() if path.name.startswith(".density")]


def test_external_image_created_after_precheck_is_not_overwritten(
    tmp_path: Path,
    vapor_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import carnopy.visualization.export as export_module

    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    output = tmp_path / "density.png"
    real_link = os.link

    def race_link(source: Path, destination: Path) -> None:
        Path(destination).write_bytes(b"external-race-winner")
        real_link(source, destination)

    monkeypatch.setattr(export_module.os, "link", race_link)
    with pytest.raises(VisualizationError, match="could not export plot artifacts"):
        plot_property_curves(
            run.output_directory,
            property_name="mass_density",
            output=output,
        )
    assert output.read_bytes() == b"external-race-winner"


def test_unsupported_hard_links_fail_without_fallback(
    tmp_path: Path,
    vapor_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import carnopy.visualization.export as export_module

    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    output = tmp_path / "density.png"

    def unsupported_link(_source: Path, _destination: Path) -> None:
        raise OSError(errno.EOPNOTSUPP, "hard links unavailable")

    monkeypatch.setattr(export_module.os, "link", unsupported_link)
    with pytest.raises(VisualizationError, match="hard-link support"):
        plot_property_curves(
            run.output_directory,
            property_name="mass_density",
            output=output,
        )
    assert not output.exists()
