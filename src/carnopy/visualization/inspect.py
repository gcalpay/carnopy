from __future__ import annotations

import json
import math
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
import yaml

from carnopy.domain.properties import PROPERTY_REGISTRY
from carnopy.visualization.fields import FIELD_REGISTRY, get_field
from carnopy.visualization.io import (
    convert_field_for_display,
    display_unit_for_field,
    load_plot_source,
)
from carnopy.visualization.models import (
    PlotCoordinate,
    PlotSource,
    VisualizationError,
)
from carnopy.visualization.selection import row_valid_mask
from carnopy.visualization.units import supported_display_units

INSPECTION_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class PlotInspection:
    source: Path
    dataset_path: Path
    source_format: str
    source_sha256: str
    mode: str
    run_id: str
    spec_id: str | None
    generation_context_id: str | None
    integrity: str
    backend: str
    backend_version: str
    backend_model: str | None
    fluids: tuple[str, ...]
    row_count: int
    valid_rows: int
    invalid_rows: int
    sampling: tuple[str, ...]
    coordinates: tuple[dict[str, Any], ...]
    properties: tuple[str, ...]
    property_details: tuple[dict[str, Any], ...]
    columns: tuple[dict[str, str], ...]
    phase_counts: dict[str, int]
    failure_counts: dict[str, dict[str, int]]
    plot_kinds: tuple[str, ...]
    series_fields: dict[str, tuple[str, ...]]
    display_units: dict[str, tuple[str, ...]]
    examples: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "inspection_schema_version": INSPECTION_SCHEMA_VERSION,
            "source": {
                "requested_path": str(self.source),
                "dataset_path": str(self.dataset_path),
                "format": self.source_format,
                "sha256": self.source_sha256,
                "integrity": self.integrity,
            },
            "identity": {
                "mode": self.mode,
                "run_id": self.run_id,
                "spec_id": self.spec_id,
                "generation_context_id": self.generation_context_id,
            },
            "backend": {
                "name": self.backend,
                "version": self.backend_version,
                "model": self.backend_model,
            },
            "rows": {
                "total": self.row_count,
                "valid": self.valid_rows,
                "invalid": self.invalid_rows,
            },
            "fluids": list(self.fluids),
            "coordinates": list(self.coordinates),
            "properties": list(self.property_details),
            "columns": list(self.columns),
            "phase_counts": self.phase_counts,
            "failure_counts": self.failure_counts,
            "plot_capabilities": [
                {
                    "kind": kind,
                    "series_fields": list(self.series_fields.get(kind, ())),
                }
                for kind in self.plot_kinds
            ],
            "display_units": {field: list(units) for field, units in self.display_units.items()},
            "examples": list(self.examples),
        }

    def format_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)

    def format_text(self) -> str:
        lines = [
            f"Source: {self.source}",
            f"Dataset: {self.dataset_path} ({self.source_format})",
            f"Mode: {self.mode}",
            f"Run ID: {self.run_id}",
            f"Spec ID: {self.spec_id or 'unreported'}",
            f"Generation context: {self.generation_context_id or 'unreported'}",
            f"Integrity: {self.integrity}",
            (
                f"Backend: {self.backend} {self.backend_version}"
                + (f" ({self.backend_model})" if self.backend_model else "")
            ),
            f"Fluids: {', '.join(self.fluids)}",
            (f"Rows: {self.row_count} total, {self.valid_rows} valid, {self.invalid_rows} invalid"),
            "Sampling:",
            *(f"  {item}" for item in self.sampling),
            "Phases:",
            *(
                (f"  {phase}: {count}" for phase, count in sorted(self.phase_counts.items()))
                if self.phase_counts
                else ("  none",)
            ),
            "Failures:",
            *_failure_text(self.failure_counts),
            "Properties:",
            *(_property_text(detail) for detail in self.property_details),
            "Compatible plot kinds:",
            *(
                "  "
                + kind
                + (
                    f" (series: {', '.join(self.series_fields[kind])})"
                    if self.series_fields.get(kind)
                    else ""
                )
                for kind in self.plot_kinds
            ),
            "Supported display units:",
            *(
                f"  {field}: {', '.join(units)}"
                for field, units in sorted(self.display_units.items())
            ),
            "Examples:",
            *(f"  {example}" for example in self.examples),
        ]
        return "\n".join(lines)

    def write_visualization(self, output: str | Path) -> Path:
        output_path = Path(output).expanduser()
        if output_path.suffix.lower() not in {".yaml", ".yml"}:
            raise VisualizationError("visualization configuration path must end in .yaml or .yml")
        if not output_path.parent.exists():
            raise VisualizationError(
                f"visualization configuration parent does not exist: {output_path.parent}"
            )
        if not self.properties or "property-curves" not in self.plot_kinds:
            raise VisualizationError(
                "source has no emitted property compatible with property-curves"
            )
        plot: dict[str, object] = {
            "name": f"{self.properties[0].replace('_', '-')}-curves",
            "kind": "property_curves",
            "property": self.properties[0],
        }
        if self.mode == "property_table":
            plot["x"] = "temperature"
        payload = {
            "visualization": {
                "format": "png",
                "plots": [plot],
            }
        }
        try:
            with output_path.open("x", encoding="utf-8", newline="\n") as stream:
                yaml.safe_dump(
                    payload,
                    stream,
                    sort_keys=False,
                    allow_unicode=True,
                )
        except FileExistsError as exc:
            raise VisualizationError(
                f"refusing to overwrite existing visualization configuration: {output_path}"
            ) from exc
        except OSError as exc:
            raise VisualizationError(
                f"could not write visualization configuration {output_path}: {exc}"
            ) from exc
        return output_path.resolve()


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
    coordinates = _coordinate_details(plot_source)
    sampling = tuple(_coordinate_summary(item) for item in coordinates)
    plot_kinds = _compatible_plot_kinds(plot_source, properties)
    series_fields = {kind: _series_fields(plot_source, kind) for kind in plot_kinds}
    examples = _examples(
        plot_source,
        fluids,
        properties,
        plot_kinds,
        series_fields,
    )
    backend = _single_text(frame, "backend")
    backend_version = _single_text(frame, "backend_version")
    return PlotInspection(
        source=plot_source.requested_path,
        dataset_path=plot_source.dataset_path,
        source_format=plot_source.source_format,
        source_sha256=plot_source.source_sha256,
        mode=plot_source.mode,
        run_id=plot_source.run_id,
        spec_id=plot_source.spec_id,
        generation_context_id=plot_source.generation_context_id,
        integrity=plot_source.source_integrity,
        backend=backend,
        backend_version=backend_version,
        backend_model=_backend_model(plot_source),
        fluids=fluids,
        row_count=len(frame),
        valid_rows=int(valid_mask.sum()),
        invalid_rows=int((~valid_mask).sum()),
        sampling=sampling,
        coordinates=coordinates,
        properties=properties,
        property_details=_property_details(frame, valid_mask, properties),
        columns=tuple(
            {"name": str(column), "dtype": str(frame[column].dtype)} for column in frame.columns
        ),
        phase_counts=_counts(frame, "phase"),
        failure_counts={
            "layer": _counts(frame, "failure_layer"),
            "code": _counts(frame, "failure_code"),
            "property": _counts(frame, "failure_property"),
        },
        plot_kinds=plot_kinds,
        series_fields=series_fields,
        display_units={
            field: units
            for field in FIELD_REGISTRY
            if (units := supported_display_units(field)) and _field_is_available(plot_source, field)
        },
        examples=examples,
    )


def _coordinate_details(plot_source: PlotSource) -> tuple[dict[str, Any], ...]:
    fields = {
        "property_table": ("temperature", "pressure"),
        "saturation_table": (plot_source.saturation_coordinate,),
        "vapor_mass_fraction_table": (
            plot_source.saturation_coordinate,
            "vapor_mass_fraction",
        ),
    }[plot_source.mode]
    details: list[dict[str, Any]] = []
    for field in fields:
        if field is None:
            continue
        definition = get_field(field)
        si_values = _ordered_unique(
            pd.to_numeric(
                plot_source.frame[definition.column],
                errors="coerce",
            )
        )
        display_values = _ordered_unique(_display_series(plot_source, field))
        display_unit = (
            display_unit_for_field(plot_source, cast(PlotCoordinate, field))
            if field in {"temperature", "pressure"}
            else definition.unit
        )
        details.append(
            {
                "field": field,
                "column": definition.column,
                "si_unit": definition.unit,
                "display_unit": display_unit,
                "level_count": len(si_values),
                "levels_si": si_values,
                "levels_display": display_values,
            }
        )
    return tuple(details)


def _coordinate_summary(detail: dict[str, Any]) -> str:
    suffix = f" {detail['display_unit']}" if detail["display_unit"] not in (None, "1") else ""
    rendered = ", ".join(_format_value(float(value)) for value in detail["levels_display"])
    return f"{detail['field']}: {detail['level_count']} level(s) [{rendered}]{suffix}"


def _property_details(
    frame: pd.DataFrame,
    valid_mask: pd.Series,
    properties: tuple[str, ...],
) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    for name in properties:
        definition = PROPERTY_REGISTRY[name]
        values = pd.to_numeric(frame[definition.column], errors="coerce")
        finite = pd.Series(
            np.isfinite(values.to_numpy(dtype=float)),
            index=frame.index,
        )
        valid_values = values.loc[valid_mask & finite]
        result.append(
            {
                "name": name,
                "column": definition.column,
                "unit": definition.unit,
                "classification": definition.classification,
                "reference_dependent": definition.reference_dependent,
                "finite_count": int(finite.sum()),
                "valid_finite_count": int((valid_mask & finite).sum()),
                "minimum": (float(valid_values.min()) if not valid_values.empty else None),
                "maximum": (float(valid_values.max()) if not valid_values.empty else None),
            }
        )
    return tuple(result)


def _display_series(plot_source: PlotSource, field: str) -> pd.Series:
    if field in {"temperature", "pressure"}:
        return convert_field_for_display(
            plot_source,
            cast(PlotCoordinate, field),
        )
    return pd.to_numeric(
        plot_source.frame[get_field(field).column],
        errors="coerce",
    )


def _ordered_unique(series: pd.Series) -> list[float]:
    result: list[float] = []
    for value in pd.to_numeric(series, errors="coerce").dropna().tolist():
        numeric = float(value)
        if not any(
            math.isclose(numeric, existing, rel_tol=1e-12, abs_tol=1e-12) for existing in result
        ):
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


def _series_fields(plot_source: PlotSource, kind: str) -> tuple[str, ...]:
    if kind == "property-curves":
        if plot_source.mode == "property_table":
            return ("pressure", "temperature")
        if plot_source.mode == "saturation_table":
            return ("saturation_endpoint",)
        return (
            (plot_source.saturation_coordinate,)
            if plot_source.saturation_coordinate is not None
            else ()
        )
    if kind == "xy":
        return tuple(
            field
            for field in ("temperature", "pressure", "vapor_mass_fraction")
            if get_field(field).column in plot_source.frame.columns
            and plot_source.frame[get_field(field).column].nunique(dropna=True) > 1
        )
    if kind == "pv":
        if plot_source.mode == "property_table":
            return ("temperature",)
        if plot_source.mode == "saturation_table":
            return ("saturation_endpoint",)
        return (
            (plot_source.saturation_coordinate,)
            if plot_source.saturation_coordinate is not None
            else ()
        )
    if kind == "ts":
        if plot_source.mode == "property_table":
            return ("pressure",)
        if plot_source.mode == "saturation_table":
            return ("saturation_endpoint",)
        return (
            (plot_source.saturation_coordinate,)
            if plot_source.saturation_coordinate is not None
            else ()
        )
    return ()


def _examples(
    plot_source: PlotSource,
    fluids: tuple[str, ...],
    properties: tuple[str, ...],
    plot_kinds: tuple[str, ...],
    series_fields: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
    source = shlex.quote(str(plot_source.requested_path))
    fluid_option = f" --fluid {shlex.quote(fluids[0])}" if len(fluids) > 1 else ""
    examples: list[str] = []
    if "property-curves" in plot_kinds:
        x_option = " --x temperature" if plot_source.mode == "property_table" else ""
        series_option = _series_example(
            plot_source,
            series_fields["property-curves"][0] if series_fields["property-curves"] else None,
        )
        examples.append(
            f"carnopy plot {source} --kind property-curves "
            f"--property {properties[0]}{x_option}{series_option}{fluid_option}"
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


def _series_example(plot_source: PlotSource, field: str | None) -> str:
    if field is None:
        return ""
    definition = get_field(field)
    values = plot_source.frame[definition.column].dropna()
    if values.empty:
        return ""
    value = values.iloc[0]
    if field in {"temperature", "pressure"}:
        display = _display_series(plot_source, field)
        unit = display_unit_for_field(plot_source, cast(PlotCoordinate, field))
        display_value = display.dropna().iloc[0]
        return f" --series {field}={_format_value(float(display_value))}{unit}"
    return f" --series {field}={value!s}"


def _counts(frame: pd.DataFrame, column: str) -> dict[str, int]:
    if column not in frame.columns:
        return {}
    values = frame[column].dropna().astype(str).str.strip()
    values = values.loc[values.ne("")]
    counts = values.value_counts().sort_index()
    return {str(key): int(value) for key, value in counts.items()}


def _single_text(frame: pd.DataFrame, column: str) -> str:
    values = sorted(frame[column].dropna().astype(str).unique().tolist())
    return ", ".join(values) if values else "unreported"


def _backend_model(plot_source: PlotSource) -> str | None:
    if "backend_model" in plot_source.frame.columns:
        value = _single_text(plot_source.frame, "backend_model")
        return None if value == "unreported" else value
    if isinstance(plot_source.metadata, dict):
        metadata_value = plot_source.metadata.get("backend_model")
        if isinstance(metadata_value, str) and metadata_value.strip():
            return metadata_value
    return None


def _field_is_available(plot_source: PlotSource, field: str) -> bool:
    definition = get_field(field)
    if definition.column in plot_source.frame.columns:
        return True
    return bool(
        definition.required_property is not None
        and get_field(definition.required_property).column in plot_source.frame.columns
    )


def _failure_text(
    counts: dict[str, dict[str, int]],
) -> list[str]:
    lines: list[str] = []
    for category in ("layer", "code", "property"):
        values = counts[category]
        if values:
            lines.append(
                f"  {category}: "
                + ", ".join(f"{name}={count}" for name, count in sorted(values.items()))
            )
    return lines or ["  none"]


def _property_text(detail: dict[str, Any]) -> str:
    bounds = (
        "no valid finite values"
        if detail["minimum"] is None
        else f"min={detail['minimum']:.6g}, max={detail['maximum']:.6g}"
    )
    return (
        f"  {detail['name']}: {detail['column']} [{detail['unit']}], "
        f"valid finite={detail['valid_finite_count']}, {bounds}"
    )


def _format_value(value: float) -> str:
    return format(value, ".6g")
