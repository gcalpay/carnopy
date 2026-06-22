from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pandas as pd

from carnopy.domain.properties import PROPERTY_REGISTRY
from carnopy.visualization.fields import FIELD_REGISTRY, get_field
from carnopy.visualization.io import (
    convert_field_for_display,
    display_unit_for_field,
    load_plot_source,
)
from carnopy.visualization.models import PlotCoordinate, PlotSource
from carnopy.visualization.selection import row_valid_mask


@dataclass(frozen=True)
class PlotInspection:
    source: Path
    mode: str
    run_id: str
    integrity: str
    fluids: tuple[str, ...]
    valid_rows: int
    invalid_rows: int
    sampling: tuple[str, ...]
    properties: tuple[str, ...]
    plot_kinds: tuple[str, ...]
    examples: tuple[str, ...]

    def format_text(self) -> str:
        lines = [
            f"Source: {self.source}",
            f"Mode: {self.mode}",
            f"Run ID: {self.run_id}",
            f"Integrity: {self.integrity}",
            f"Fluids: {', '.join(self.fluids)}",
            f"Rows: {self.valid_rows} valid, {self.invalid_rows} invalid",
            "Sampling:",
            *(f"  {item}" for item in self.sampling),
            f"Properties: {', '.join(self.properties) if self.properties else 'none'}",
            f"Compatible plot kinds: {', '.join(self.plot_kinds) or 'none'}",
            "Examples:",
            *(f"  {example}" for example in self.examples),
        ]
        return "\n".join(lines)


def inspect_plot_source(source: str | Path) -> PlotInspection:
    plot_source = load_plot_source(source)
    frame = plot_source.frame
    valid_mask = row_valid_mask(frame)
    fluids = tuple(sorted(frame["fluid"].dropna().astype(str).unique().tolist()))
    properties = tuple(
        name
        for name in sorted(PROPERTY_REGISTRY)
        if PROPERTY_REGISTRY[name].column in frame.columns
    )
    sampling = _sampling_summary(plot_source)
    plot_kinds = _compatible_plot_kinds(plot_source, properties)
    examples = _examples(plot_source, fluids, properties, plot_kinds)
    return PlotInspection(
        source=plot_source.requested_path,
        mode=plot_source.mode,
        run_id=plot_source.run_id,
        integrity=plot_source.source_integrity,
        fluids=fluids,
        valid_rows=int(valid_mask.sum()),
        invalid_rows=int((~valid_mask).sum()),
        sampling=sampling,
        properties=properties,
        plot_kinds=plot_kinds,
        examples=examples,
    )


def _sampling_summary(plot_source: PlotSource) -> tuple[str, ...]:
    fields = {
        "property_table": ("temperature", "pressure"),
        "saturation_table": (plot_source.saturation_coordinate,),
        "vapor_mass_fraction_table": (
            plot_source.saturation_coordinate,
            "vapor_mass_fraction",
        ),
    }[plot_source.mode]
    summaries: list[str] = []
    for field in fields:
        if field is None:
            continue
        definition = get_field(field)
        series = _display_series(plot_source, field)
        levels = _ordered_unique(series)
        unit = (
            display_unit_for_field(plot_source, cast(PlotCoordinate, field))
            if field in {"temperature", "pressure"}
            else definition.unit
        )
        suffix = f" {unit}" if unit and unit != "1" else ""
        rendered_levels = ", ".join(_format_value(value) for value in levels)
        summaries.append(f"{field}: {len(levels)} level(s) [{rendered_levels}]{suffix}")
    return tuple(summaries)


def _display_series(plot_source: PlotSource, field: str) -> pd.Series:
    if field in {"temperature", "pressure"}:
        return convert_field_for_display(plot_source, cast(PlotCoordinate, field))
    return pd.to_numeric(plot_source.frame[get_field(field).column], errors="coerce")


def _ordered_unique(series: pd.Series) -> list[float]:
    result: list[float] = []
    for value in pd.to_numeric(series, errors="coerce").dropna().tolist():
        numeric = float(value)
        if numeric not in result:
            result.append(numeric)
    return result


def _compatible_plot_kinds(
    plot_source: PlotSource,
    properties: tuple[str, ...],
) -> tuple[str, ...]:
    result: list[str] = []
    if properties:
        result.append("property-curves")
    if properties and plot_source.mode in {
        "property_table",
        "vapor_mass_fraction_table",
    }:
        x_field, y_field = (
            ("temperature", "pressure")
            if plot_source.mode == "property_table"
            else ("vapor_mass_fraction", plot_source.saturation_coordinate)
        )
        if (
            x_field is not None
            and y_field is not None
            and plot_source.frame[get_field(x_field).column].nunique(dropna=True) >= 2
            and plot_source.frame[get_field(y_field).column].nunique(dropna=True) >= 2
        ):
            result.append("property-heatmap")
    numeric_fields = [
        name
        for name, definition in FIELD_REGISTRY.items()
        if definition.axis_allowed
        and (
            definition.column in plot_source.frame.columns
            or (
                definition.required_property is not None
                and get_field(definition.required_property).column in plot_source.frame.columns
            )
        )
    ]
    if len(numeric_fields) >= 2:
        result.append("xy")
    if "mass_density" in properties and "pressure_Pa" in plot_source.frame:
        result.append("pv")
    if (
        "specific_entropy" in properties
        and "temperature_K" in plot_source.frame
        and isinstance(plot_source.metadata, dict)
        and isinstance(plot_source.metadata.get("reference_state_policy"), str)
    ):
        result.append("ts")
    return tuple(result)


def _examples(
    plot_source: PlotSource,
    fluids: tuple[str, ...],
    properties: tuple[str, ...],
    plot_kinds: tuple[str, ...],
) -> tuple[str, ...]:
    source = shlex.quote(str(plot_source.requested_path))
    fluid_option = f" --fluid {shlex.quote(fluids[0])}" if len(fluids) > 1 else ""
    examples: list[str] = []
    if "property-curves" in plot_kinds:
        x_option = " --x temperature" if plot_source.mode == "property_table" else ""
        examples.append(
            f"carnopy plot {source} --kind property-curves "
            f"--property {properties[0]}{x_option}{fluid_option}"
        )
    if "property-heatmap" in plot_kinds:
        examples.append(
            f"carnopy plot {source} --kind property-heatmap "
            f"--property {properties[0]}{fluid_option}"
        )
    if "xy" in plot_kinds and len(properties) >= 2:
        examples.append(
            f"carnopy plot {source} --kind xy --x {properties[0]} "
            f"--y {properties[1]} --group-by pressure{fluid_option}"
        )
    if "pv" in plot_kinds:
        examples.append(f"carnopy plot {source} --kind pv{fluid_option}")
    if "ts" in plot_kinds:
        examples.append(f"carnopy plot {source} --kind ts{fluid_option}")
    return tuple(examples)


def _format_value(value: float) -> str:
    return format(value, ".6g")
