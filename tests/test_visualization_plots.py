from __future__ import annotations

import errno
import json
import os
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import pytest
from matplotlib.axes import Axes

matplotlib.use("Agg", force=True)

from carnopy.api import generate_dataset
from carnopy.provenance import sha256_file
from carnopy.visualization import plot_dataset
from carnopy.visualization.models import VisualizationError


def _write_surface_config(
    path: Path,
    fluids: list[str] | None = None,
    pressures: list[float] | None = None,
) -> Path:
    fluid_lines = "\n".join(f"  - {fluid}" for fluid in (fluids or ["Propane"]))
    pressure_values = pressures or [1.0, 2.0]
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
    values: {pressure_values}
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
    assert sidecar["source"]["sha256"] == sha256_file(run.output_directory / "dataset.parquet")
    assert sidecar["image"]["sha256"] == sha256_file(result.image_path)
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
    assert sidecar["settings"]["corner_mask"] is False
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


def test_contour_masks_invalid_interior_cell_without_corner_filling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _write_surface_config(
        tmp_path / "surface.yaml",
        pressures=[1.0, 2.0, 3.0],
    )
    run = generate_dataset(config, output_root=tmp_path / "runs")
    frame = pd.read_csv(run.output_directory / "dataset.csv")
    interior = (frame["pressure_Pa"] == 200_000.0) & (frame["vapor_mass_fraction"] == 0.5)
    frame.loc[interior, "valid"] = False
    standalone = tmp_path / "masked.csv"
    frame.to_csv(standalone, index=False)

    captured: dict[str, object] = {}
    original_contourf = Axes.contourf

    def record_contourf(self: Axes, *args: object, **kwargs: object) -> object:
        captured["mask"] = np.ma.getmaskarray(args[2]).copy()
        captured["corner_mask"] = kwargs.get("corner_mask")
        return original_contourf(self, *args, **kwargs)

    monkeypatch.setattr(Axes, "contourf", record_contourf)
    result = plot_dataset(
        standalone,
        property_name="mass_density",
        kind="contour",
        coordinate="pressure",
        output=tmp_path / "masked.png",
    )
    mask = np.asarray(captured["mask"], dtype=bool)
    assert mask.shape == (3, 3)
    assert mask[1, 1]
    assert int(mask.sum()) == 1
    assert captured["corner_mask"] is False
    sidecar = json.loads(result.sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["settings"]["corner_mask"] is False


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
        plot_dataset(
            run.output_directory,
            property_name="mass_density",
            output=output,
        )
    assert existing.read_bytes() == b"external-content"
    other = output.with_suffix(".plot.json") if existing_kind == "image" else output
    assert not other.exists()


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
        plot_dataset(
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
        plot_dataset(
            run.output_directory,
            property_name="mass_density",
            output=output,
        )
    assert output.read_bytes() == b"external-race-winner"
    assert not output.with_suffix(".plot.json").exists()


def test_rollback_preserves_external_replacement_with_different_inode(
    tmp_path: Path,
    vapor_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import carnopy.visualization.export as export_module

    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    output = tmp_path / "density.png"
    real_link = os.link
    calls = 0

    def replace_before_second_link(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            real_link(source, destination)
            return
        output.unlink()
        output.write_bytes(b"external-replacement")
        raise OSError(errno.EIO, "controlled sidecar link failure")

    monkeypatch.setattr(export_module.os, "link", replace_before_second_link)
    with pytest.raises(VisualizationError, match="could not export plot artifacts"):
        plot_dataset(
            run.output_directory,
            property_name="mass_density",
            output=output,
        )
    assert output.read_bytes() == b"external-replacement"
    assert not output.with_suffix(".plot.json").exists()


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
        plot_dataset(
            run.output_directory,
            property_name="mass_density",
            output=output,
        )
    assert not output.exists()
    assert not output.with_suffix(".plot.json").exists()
