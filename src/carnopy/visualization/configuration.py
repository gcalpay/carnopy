from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from carnopy.config.models import NormalizedConfig
from carnopy.config.visualization import VisualizationConfig
from carnopy.domain.failures import ConfigError
from carnopy.visualization.fields import FIELD_REGISTRY, get_field
from carnopy.visualization.models import PlotSource, VisualizationError
from carnopy.visualization.requests import (
    ExactFilter,
    PlotRequest,
    normalize_display_units,
    normalize_series_selections,
    request_id,
)


@dataclass(frozen=True)
class NormalizedVisualization:
    visualization_request_id: str
    requests: tuple[PlotRequest, ...]

    def canonical_dict(self) -> dict[str, object]:
        return {
            "visualization_request_id": self.visualization_request_id,
            "plots": [request.canonical_dict() for request in self.requests],
        }


def normalize_visualization(
    visualization: VisualizationConfig | None,
    *,
    scientific_config: NormalizedConfig,
) -> NormalizedVisualization | None:
    if visualization is None:
        return None
    requests: list[PlotRequest] = []
    for plot in visualization.plots:
        fluids = _canonical_fluids(
            plot.fluids if plot.fluids is not None else visualization.fluids,
            scientific_config=scientific_config,
        )
        filters = _merged_filters(visualization.filters, plot.filters)
        try:
            request = PlotRequest(
                kind=plot.kind,
                property_name=plot.property_name,
                x_field=plot.x_field,
                y_field=plot.y_field,
                group_by=plot.group_by,
                filters=filters,
                series=normalize_series_selections(plot.series),
                display_units=normalize_display_units(
                    {**visualization.display_units, **plot.display_units}
                ),
                fluids=fluids,
                value_scale=plot.value_scale,
                color_scale=plot.color_scale,
                x_scale=plot.x_scale,
                y_scale=plot.y_scale,
                output_format=plot.format or visualization.format,
                name=plot.name,
            )
        except (ValidationError, ValueError) as exc:
            raise ConfigError(f"invalid visualization plot {plot.name!r}: {exc}") from exc
        _validate_static_request(request, scientific_config)
        requests.append(request)
    normalized = tuple(requests)
    return NormalizedVisualization(
        visualization_request_id=request_id(normalized),
        requests=normalized,
    )


def normalize_visualization_for_source(
    visualization: VisualizationConfig,
    *,
    plot_source: PlotSource,
) -> NormalizedVisualization:
    requests: list[PlotRequest] = []
    for plot in visualization.plots:
        fluids = _source_fluids(
            plot.fluids if plot.fluids is not None else visualization.fluids,
            plot_source=plot_source,
        )
        filters = _merged_filters(visualization.filters, plot.filters)
        try:
            request = PlotRequest(
                kind=plot.kind,
                property_name=plot.property_name,
                x_field=plot.x_field,
                y_field=plot.y_field,
                group_by=plot.group_by,
                filters=filters,
                series=normalize_series_selections(plot.series),
                display_units=normalize_display_units(
                    {**visualization.display_units, **plot.display_units}
                ),
                fluids=fluids,
                value_scale=plot.value_scale,
                color_scale=plot.color_scale,
                x_scale=plot.x_scale,
                y_scale=plot.y_scale,
                output_format=plot.format or visualization.format,
                name=plot.name,
            )
        except (ValidationError, ValueError) as exc:
            raise VisualizationError(f"invalid visualization plot {plot.name!r}: {exc}") from exc
        _validate_source_request(request, plot_source)
        requests.append(request)
    normalized = tuple(requests)
    return NormalizedVisualization(
        visualization_request_id=request_id(normalized),
        requests=normalized,
    )


def _canonical_fluids(
    requested: tuple[str, ...],
    *,
    scientific_config: NormalizedConfig,
) -> tuple[str, ...]:
    if not requested:
        return tuple(scientific_config.fluids)
    lookup = {
        alias.casefold(): canonical
        for alias, canonical in zip(
            scientific_config.requested_fluid_aliases,
            scientific_config.requested_fluid_canonical_names,
            strict=True,
        )
    }
    lookup.update({fluid.casefold(): fluid for fluid in scientific_config.fluids})
    canonical: list[str] = []
    for fluid in requested:
        name = lookup.get(fluid.casefold())
        if name is None:
            raise ConfigError(
                f"visualization fluid {fluid!r} is not one of the dataset's "
                "requested aliases or canonical fluids"
            )
        canonical.append(name)
    if len(set(canonical)) != len(canonical):
        raise ConfigError("visualization fluid aliases resolve to duplicate canonical fluids")
    return tuple(sorted(canonical, key=str.casefold))


def _source_fluids(
    requested: tuple[str, ...],
    *,
    plot_source: PlotSource,
) -> tuple[str, ...]:
    available = sorted(
        plot_source.frame["fluid"].dropna().astype(str).unique().tolist(),
        key=str.casefold,
    )
    if not requested:
        return tuple(available)
    lookup = {fluid.casefold(): fluid for fluid in available}
    metadata = plot_source.metadata
    if isinstance(metadata, dict):
        aliases = metadata.get("requested_fluid_aliases")
        canonical = metadata.get("requested_fluid_canonical_names")
        if isinstance(aliases, list) and isinstance(canonical, list):
            for alias, name in zip(aliases, canonical, strict=False):
                if isinstance(alias, str) and isinstance(name, str) and name in available:
                    lookup[alias.casefold()] = name
    selected: list[str] = []
    for fluid in requested:
        name = lookup.get(fluid.casefold())
        if name is None:
            raise VisualizationError(
                f"visualization fluid {fluid!r} is not present; available fluids: "
                + ", ".join(available)
            )
        if name in selected:
            raise VisualizationError(
                "visualization fluid aliases resolve to duplicate canonical fluids"
            )
        selected.append(name)
    return tuple(sorted(selected, key=str.casefold))


def _merged_filters(
    shared: dict[str, float | str],
    plot: dict[str, float | str],
) -> tuple[ExactFilter, ...]:
    merged: dict[str, ExactFilter] = {}
    for source in (shared, plot):
        for field, value in source.items():
            try:
                exact_filter = ExactFilter(field=field, value=value)
            except (ValidationError, ValueError) as exc:
                raise ConfigError(f"invalid visualization filter {field!r}: {exc}") from exc
            existing = merged.get(field)
            if existing is not None and existing.value != exact_filter.value:
                raise ConfigError(
                    f"conflicting shared and per-plot visualization filters for {field!r}"
                )
            merged[field] = exact_filter
    return tuple(merged[field] for field in sorted(merged))


def _validate_static_request(
    request: PlotRequest,
    scientific_config: NormalizedConfig,
) -> None:
    if request.kind == "property_heatmap" and scientific_config.mode == "saturation_table":
        raise ConfigError(
            "saturation_table does not support property_heatmap because it contains only "
            "x_vap=0 and x_vap=1 endpoint states. Use vapor_mass_fraction_table for "
            "quality-resolved maps."
        )
    if request.kind == "property_curves":
        if scientific_config.mode == "property_table":
            if request.x_field not in {"temperature", "pressure"}:
                raise ConfigError(
                    "property_table property_curves requires x: temperature or x: pressure"
                )
        elif request.x_field is not None:
            raise ConfigError(
                f"{scientific_config.mode} property_curves uses its mode-defined x-axis "
                "and rejects x"
            )

    available = _available_fields(scientific_config)
    referenced = [
        request.property_name,
        request.x_field,
        request.y_field,
        request.group_by,
        *(exact_filter.field for exact_filter in request.filters),
        *(selection.field for selection in request.series),
        *(selection.field for selection in request.display_units),
    ]
    for field in referenced:
        if field is not None and field not in available:
            raise ConfigError(
                f"visualization field {field!r} is not emitted by this dataset specification"
            )
    _validate_series_field(
        request,
        mode=scientific_config.mode,
        saturation_coordinate=_config_saturation_coordinate(scientific_config),
        error_type=ConfigError,
    )
    _validate_display_fields(
        request,
        mode=scientific_config.mode,
        saturation_coordinate=_config_saturation_coordinate(scientific_config),
        error_type=ConfigError,
    )

    required_properties: set[str] = set()
    for field in (request.property_name, request.x_field, request.y_field):
        if field is None:
            continue
        dependency = get_field(field).required_property
        if dependency is not None:
            required_properties.add(dependency)
    if request.kind == "pv":
        required_properties.add("mass_density")
    if request.kind == "ts":
        required_properties.add("specific_entropy")
    missing = sorted(required_properties - set(scientific_config.properties))
    if missing:
        raise ConfigError(
            "visualization requires emitted properties that are not requested: "
            + ", ".join(missing)
        )


def _available_fields(config: NormalizedConfig) -> set[str]:
    fields = {
        "temperature",
        "pressure",
        "phase",
        "fluid",
        *config.properties,
    }
    if config.mode in {"saturation_table", "vapor_mass_fraction_table"}:
        fields.add("vapor_mass_fraction")
    if config.mode == "saturation_table":
        fields.add("saturation_endpoint")
    if "mass_density" in config.properties:
        fields.add("specific_volume")
    return fields


def _validate_source_request(
    request: PlotRequest,
    plot_source: PlotSource,
) -> None:
    if request.kind == "property_heatmap" and plot_source.mode == "saturation_table":
        raise VisualizationError(
            "saturation_table does not support property_heatmap because it contains only "
            "x_vap=0 and x_vap=1 endpoint states. Use vapor_mass_fraction_table for "
            "quality-resolved maps."
        )
    if request.kind == "property_curves":
        if plot_source.mode == "property_table":
            if request.x_field not in {"temperature", "pressure"}:
                raise VisualizationError(
                    "property-table property-curves requires x: temperature or x: pressure"
                )
        elif request.x_field is not None:
            raise VisualizationError(
                f"{plot_source.mode} property-curves uses its mode-defined x-axis and rejects x"
            )
    available = _source_available_fields(plot_source)
    referenced = [
        request.property_name,
        request.x_field,
        request.y_field,
        request.group_by,
        *(exact_filter.field for exact_filter in request.filters),
        *(selection.field for selection in request.series),
        *(selection.field for selection in request.display_units),
    ]
    for field in referenced:
        if field is not None and field not in available:
            raise VisualizationError(
                f"visualization field {field!r} is not emitted by this dataset"
            )
    _validate_series_field(
        request,
        mode=plot_source.mode,
        saturation_coordinate=plot_source.saturation_coordinate,
        error_type=VisualizationError,
    )
    _validate_display_fields(
        request,
        mode=plot_source.mode,
        saturation_coordinate=plot_source.saturation_coordinate,
        error_type=VisualizationError,
    )
    required: set[str] = set()
    for field in (request.property_name, request.x_field, request.y_field):
        if field is None:
            continue
        dependency = get_field(field).required_property
        if dependency is not None:
            required.add(dependency)
    if request.kind == "pv":
        required.add("mass_density")
    if request.kind == "ts":
        required.add("specific_entropy")
    missing = sorted(required - available)
    if missing:
        raise VisualizationError(
            "visualization requires emitted properties that are absent: " + ", ".join(missing)
        )


def _source_available_fields(plot_source: PlotSource) -> set[str]:
    available = {"phase", "fluid"}
    for name in ("temperature", "pressure", "vapor_mass_fraction", "saturation_endpoint"):
        if get_field(name).column in plot_source.frame.columns:
            available.add(name)
    for name, definition in FIELD_REGISTRY.items():
        if definition.required_property == name and definition.column in plot_source.frame.columns:
            available.add(name)
    if "mass_density" in available:
        available.add("specific_volume")
    return available


def _config_saturation_coordinate(config: NormalizedConfig) -> str | None:
    if config.mode == "property_table":
        return None
    coordinates = [field for field in ("temperature", "pressure") if field in config.grid]
    return coordinates[0] if len(coordinates) == 1 else None


def _validate_series_field(
    request: PlotRequest,
    *,
    mode: str,
    saturation_coordinate: str | None,
    error_type: type[Exception],
) -> None:
    if not request.series:
        return
    expected: str | None
    if request.kind == "property_heatmap":
        expected = None
    elif request.kind == "property_curves":
        if mode == "property_table":
            expected = (
                "pressure"
                if request.x_field == "temperature"
                else "temperature"
                if request.x_field == "pressure"
                else None
            )
        elif mode == "saturation_table":
            expected = "saturation_endpoint"
        else:
            expected = saturation_coordinate
    elif request.kind == "xy":
        expected = request.group_by
    elif mode == "property_table":
        expected = "temperature" if request.kind == "pv" else "pressure"
    elif mode == "saturation_table":
        expected = "saturation_endpoint"
    else:
        expected = saturation_coordinate
    selected = request.series[0].field
    if expected is None:
        raise error_type(f"{request.kind} does not support series selection")
    if selected != expected:
        raise error_type(
            f"{request.kind} uses {expected!r} as its series field; "
            f"received series selection for {selected!r}"
        )


def _validate_display_fields(
    request: PlotRequest,
    *,
    mode: str,
    saturation_coordinate: str | None,
    error_type: type[Exception],
) -> None:
    if not request.display_units:
        return
    allowed: set[str] = set()
    if request.kind == "property_curves":
        if request.property_name is not None:
            allowed.add(request.property_name)
        if mode == "property_table" and request.x_field is not None:
            allowed.update(
                {
                    request.x_field,
                    "pressure" if request.x_field == "temperature" else "temperature",
                }
            )
        elif mode == "saturation_table":
            if saturation_coordinate is not None:
                allowed.add(saturation_coordinate)
        elif saturation_coordinate is not None:
            allowed.update({"vapor_mass_fraction", saturation_coordinate})
    elif request.kind == "property_heatmap":
        if request.property_name is not None:
            allowed.add(request.property_name)
        if mode == "property_table":
            allowed.update({"temperature", "pressure"})
        elif saturation_coordinate is not None:
            allowed.update({"vapor_mass_fraction", saturation_coordinate})
    elif request.kind == "xy":
        allowed.update(
            field
            for field in (request.x_field, request.y_field, request.group_by)
            if field is not None
        )
    elif request.kind == "pv":
        allowed.update({"specific_volume", "pressure"})
        allowed.add(
            "temperature"
            if mode == "property_table"
            else "saturation_endpoint"
            if mode == "saturation_table"
            else saturation_coordinate or ""
        )
    else:
        allowed.update({"specific_entropy", "temperature"})
        allowed.add(
            "pressure"
            if mode == "property_table"
            else "saturation_endpoint"
            if mode == "saturation_table"
            else saturation_coordinate or ""
        )
    allowed.discard("")
    invalid = sorted(
        selection.field for selection in request.display_units if selection.field not in allowed
    )
    if invalid:
        raise error_type(
            "display units were requested for fields not used by this plot: "
            f"{', '.join(invalid)}; available plotted fields: "
            f"{', '.join(sorted(allowed)) or 'none'}"
        )
