from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from carnopy.config.models import NormalizedConfig
from carnopy.config.visualization import VisualizationConfig
from carnopy.domain.failures import ConfigError
from carnopy.visualization.fields import get_field
from carnopy.visualization.requests import ExactFilter, PlotRequest, request_id


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
    ]
    for field in referenced:
        if field is not None and field not in available:
            raise ConfigError(
                f"visualization field {field!r} is not emitted by this dataset specification"
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
