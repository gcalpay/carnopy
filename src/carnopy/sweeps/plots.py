from __future__ import annotations

import json
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

import pandas as pd

from carnopy._version import __version__
from carnopy.config.sweep import ComparisonPlotsConfig
from carnopy.domain.failures import OutputError
from carnopy.provenance import sha256_file
from carnopy.visualization.fields import get_field
from carnopy.visualization.render import import_matplotlib

COMPARISON_REPORT_SCHEMA_VERSION = 1


def render_comparison_plots(
    *,
    comparison_plots: ComparisonPlotsConfig,
    values_path: Path,
    deltas_path: Path,
    output_directory: Path,
    sweep_identity: dict[str, str],
    selected_models: tuple[str, ...],
    fluid_aliases: dict[str, str],
) -> tuple[Path, Path, int]:
    try:
        output_directory.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise OutputError(f"could not create comparison plot directory: {exc}") from exc
    values = pd.read_parquet(values_path)
    values_hash = sha256_file(values_path)
    deltas_hash = sha256_file(deltas_path)
    outcomes: list[dict[str, Any]] = []
    succeeded = 0
    failed = 0
    mpl = import_matplotlib()
    for plot in comparison_plots.plots:
        image_path = output_directory / f"{plot.name}.{plot.format or comparison_plots.format}"
        sidecar_path = output_directory / f"{plot.name}.plot.json"
        try:
            _render_property_comparison(
                plot=plot,
                values=values,
                selected_models=selected_models,
                fluid_aliases=fluid_aliases,
                image_path=image_path,
                sidecar_path=sidecar_path,
                sweep_identity=sweep_identity,
                comparison_hashes={
                    "comparison/values.parquet": values_hash,
                    "comparison/deltas.parquet": deltas_hash,
                },
            )
        except Exception as exc:
            failed += 1
            outcomes.append(
                {
                    "name": plot.name,
                    "kind": plot.kind,
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            )
        else:
            succeeded += 1
            outcomes.append(
                {
                    "name": plot.name,
                    "kind": plot.kind,
                    "status": "completed",
                    "image_path": str(image_path),
                    "sidecar_path": str(sidecar_path),
                }
            )
        finally:
            mpl["pyplot"].close("all")
    report_path = output_directory / "comparison-report.json"
    report = {
        "comparison_report_schema_version": COMPARISON_REPORT_SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_sweep_identity": sweep_identity,
        "status": "completed" if failed == 0 else "completed_with_failures",
        "requested_plot_count": len(comparison_plots.plots),
        "succeeded_plot_count": succeeded,
        "failed_plot_count": failed,
        "outcomes": outcomes,
        "runtime_versions": {
            "carnopy": __version__,
            "matplotlib": metadata.version("matplotlib"),
        },
    }
    _write_json_exclusive(report_path, report)
    return output_directory, report_path, failed


def _render_property_comparison(
    *,
    plot: Any,
    values: pd.DataFrame,
    selected_models: tuple[str, ...],
    fluid_aliases: dict[str, str],
    image_path: Path,
    sidecar_path: Path,
    sweep_identity: dict[str, str],
    comparison_hashes: dict[str, str],
) -> None:
    if image_path.exists() or sidecar_path.exists():
        raise OutputError(f"refusing to overwrite comparison plot artifacts for {plot.name}")
    models = tuple(plot.models or selected_models)
    selected_fluid = fluid_aliases.get(plot.fluid.casefold(), plot.fluid)
    subset = values.loc[
        (values["fluid"].astype(str).str.casefold() == selected_fluid.casefold())
        & (values["property"] == plot.property_name)
        & (values["backend_model"].isin(models))
    ].copy()
    for field, requested in plot.filters.items():
        column = _field_column(field)
        if column not in subset.columns:
            raise OutputError(f"comparison filter field {field!r} is unavailable")
        if isinstance(requested, (int, float)):
            expected = float(requested)
            subset = subset.loc[
                subset[column].map(lambda value, expected=expected: _float_equal(value, expected))
            ]
        else:
            expected_text = str(requested).casefold()
            subset = subset.loc[subset[column].astype(str).str.casefold() == expected_text]
    if subset.empty:
        raise OutputError(f"comparison plot {plot.name!r} matched no values")
    x_column = _field_column(plot.x_field)
    group_column = _field_column(plot.group_by) if plot.group_by is not None else None
    _validate_one_dimensional(subset, x_column=x_column, group_column=group_column)
    mpl = import_matplotlib()
    plt = mpl["pyplot"]
    fig, axes = plt.subplots(1, len(models), figsize=(5.5 * len(models), 4.2), squeeze=False)
    group_values = (
        sorted(subset[group_column].dropna().unique().tolist())
        if group_column is not None
        else [None]
    )
    skipped_reasons: dict[str, int] = {}
    for model_index, model in enumerate(models):
        axis = axes[0][model_index]
        model_frame = subset.loc[subset["backend_model"] == model]
        for group in group_values:
            series = model_frame
            label = "samples"
            if group_column is not None:
                series = series.loc[series[group_column] == group]
                label = f"{plot.group_by}={group}"
            series = series.sort_values([x_column, "state_key"])
            x_values = pd.to_numeric(series[x_column], errors="coerce")
            y_values = pd.to_numeric(series["value"], errors="coerce")
            valid = series["row_valid"].astype(bool) & x_values.notna() & y_values.notna()
            for reason in series.loc[~valid, "failure_code"].fillna("missing_or_nonfinite"):
                skipped_reasons[str(reason)] = skipped_reasons.get(str(reason), 0) + 1
            y_plot = y_values.where(valid)
            axis.plot(x_values, y_plot, marker="o", label=label)
        axis.set_title(model)
        axis.set_xlabel(get_field(plot.x_field).display_label)
        axis.set_ylabel(get_field(plot.property_name).display_label)
        axis.grid(True, which="both", alpha=0.25)
        if plot.value_scale == "log":
            if (pd.to_numeric(model_frame["value"], errors="coerce").dropna() <= 0).any():
                raise OutputError("log comparison plots require positive values")
            axis.set_yscale("log")
        if group_column is not None:
            axis.legend()
    fig.suptitle(f"{plot.property_name} comparison for {selected_fluid}")
    fig.tight_layout()
    suffix = image_path.suffix.lower().removeprefix(".")
    if suffix not in {"png", "pdf", "svg"}:
        raise OutputError("comparison plot output format must be png, pdf, or svg")
    kwargs: dict[str, Any] = {"format": suffix}
    if suffix == "png":
        kwargs["dpi"] = 300
    fig.savefig(image_path, **kwargs)
    image_hash = sha256_file(image_path)
    sidecar = {
        "plot_schema_version": 2,
        "plot_kind": plot.kind,
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_sweep_identity": sweep_identity,
        "comparison_artifact_hashes": comparison_hashes,
        "resolved_models": list(models),
        "selected_fluid": selected_fluid,
        "requested_fluid": plot.fluid,
        "property": plot.property_name,
        "x_axis": plot.x_field,
        "group_by": plot.group_by,
        "group_values": [str(value) for value in group_values],
        "filters": plot.filters,
        "skipped_rows": int(sum(skipped_reasons.values())),
        "missing_or_invalid_reasons": skipped_reasons,
        "image": {"path": str(image_path), "sha256": image_hash},
        "runtime_versions": {
            "carnopy": __version__,
            "matplotlib": metadata.version("matplotlib"),
        },
    }
    _write_json_exclusive(sidecar_path, sidecar)


def _validate_one_dimensional(
    frame: pd.DataFrame,
    *,
    x_column: str,
    group_column: str | None,
) -> None:
    candidate_columns = [
        "temperature_K",
        "pressure_Pa",
        "vapor_mass_fraction",
        "saturation_endpoint",
    ]
    uncontrolled: list[str] = []
    for column in candidate_columns:
        if column not in frame.columns or column in {x_column, group_column}:
            continue
        if frame[column].dropna().nunique() > 1:
            uncontrolled.append(column)
    if uncontrolled:
        raise OutputError(
            "comparison plot leaves uncontrolled dimensions: " + ", ".join(uncontrolled)
        )


def _field_column(field: str | None) -> str:
    if field is None:
        raise OutputError("comparison plot field must not be empty")
    if field == "temperature":
        return "temperature_K"
    if field == "pressure":
        return "pressure_Pa"
    return get_field(field).column


def _float_equal(value: object, expected: float) -> bool:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return False
    return abs(float(numeric) - expected) <= max(1e-12, 1e-9 * abs(expected))


def _write_json_exclusive(path: Path, value: dict[str, Any]) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    except OSError as exc:
        raise OutputError(f"could not write {path.name}: {exc}") from exc
