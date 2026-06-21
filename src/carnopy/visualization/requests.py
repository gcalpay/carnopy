from __future__ import annotations

import hashlib
import json
import math
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator, model_validator

from carnopy.visualization.fields import get_field

PlotKindV2 = Literal[
    "property_curves",
    "property_heatmap",
    "xy",
    "pv",
    "ts",
]
PlotScale = Literal["linear", "log"]
PlotFormat = Literal["png", "pdf", "svg"]
SaturationCoordinate = Literal["pressure", "temperature"]
FilterValue = float | str


class ExactFilter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str
    value: FilterValue

    @field_validator("field")
    @classmethod
    def supported_filter_field(cls, field: str) -> str:
        definition = get_field(field)
        if not definition.filter_allowed:
            raise ValueError(f"field {field!r} is not supported for exact filters")
        return field

    @field_validator("value", mode="before")
    @classmethod
    def canonical_filter_value(cls, value: object, info: ValidationInfo) -> float | str:
        field = info.data.get("field")
        if not isinstance(field, str):
            return str(value)
        definition = get_field(field)
        if definition.kind == "numeric":
            try:
                return float(str(value))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"numeric filter {field!r} requires a number") from exc
        return str(value).strip().casefold()

    @model_validator(mode="after")
    def valid_filter_value(self) -> ExactFilter:
        definition = get_field(self.field)
        if definition.kind == "numeric":
            try:
                numeric = float(self.value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"numeric filter {self.field!r} requires a number") from exc
            if not math.isfinite(numeric):
                raise ValueError(f"numeric filter {self.field!r} requires a finite number")
        elif not str(self.value).strip():
            raise ValueError(f"categorical filter {self.field!r} requires a non-empty value")
        return self


class PlotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: PlotKindV2
    property_name: str | None = None
    x_field: str | None = None
    y_field: str | None = None
    group_by: str | None = None
    filters: tuple[ExactFilter, ...] = ()
    fluids: tuple[str, ...] = ()
    value_scale: PlotScale = "linear"
    color_scale: PlotScale = "linear"
    x_scale: PlotScale = "linear"
    y_scale: PlotScale = "linear"
    saturation_coordinate: SaturationCoordinate | None = None
    output_format: PlotFormat = "png"
    name: str | None = None

    @field_validator("property_name")
    @classmethod
    def supported_property(cls, property_name: str | None) -> str | None:
        if property_name is not None:
            definition = get_field(property_name)
            if definition.kind != "numeric" or definition.required_property is None:
                raise ValueError(f"{property_name!r} is not an emitted Carnopy property")
        return property_name

    @field_validator("x_field", "y_field")
    @classmethod
    def supported_axis_field(cls, field: str | None) -> str | None:
        if field is not None and not get_field(field).axis_allowed:
            raise ValueError(f"field {field!r} cannot be used as a numeric plot axis")
        return field

    @field_validator("group_by")
    @classmethod
    def supported_group_field(cls, field: str | None) -> str | None:
        if field is not None and not get_field(field).group_allowed:
            raise ValueError(f"field {field!r} cannot be used to group plot series")
        return field

    @model_validator(mode="after")
    def validate_kind_contract(self) -> PlotRequest:
        if self.kind == "property_curves":
            if self.property_name is None:
                raise ValueError("property_curves requires property_name")
            if self.y_field is not None or self.group_by is not None:
                raise ValueError("property_curves rejects y_field and group_by")
        elif self.kind == "property_heatmap":
            if self.property_name is None:
                raise ValueError("property_heatmap requires property_name")
            if any(value is not None for value in (self.x_field, self.y_field, self.group_by)):
                raise ValueError(
                    "property_heatmap uses mode-defined axes and rejects x_field/y_field/group_by"
                )
        elif self.kind == "xy":
            if self.x_field is None or self.y_field is None:
                raise ValueError("xy requires both x_field and y_field")
            if self.property_name is not None:
                raise ValueError("xy rejects property_name")
        elif any(
            value is not None
            for value in (
                self.property_name,
                self.x_field,
                self.y_field,
                self.group_by,
            )
        ):
            raise ValueError(
                f"{self.kind} uses fixed axes and rejects property_name/x_field/y_field/group_by"
            )
        if self.kind != "property_curves" and self.value_scale != "linear":
            raise ValueError("value_scale is valid only for property_curves")
        if self.kind != "property_heatmap" and self.color_scale != "linear":
            raise ValueError("color_scale is valid only for property_heatmap")
        if self.kind in {"property_curves", "property_heatmap"} and (
            self.x_scale != "linear" or self.y_scale != "linear"
        ):
            raise ValueError("x_scale/y_scale are valid only for xy, pv, and ts")
        return self

    def canonical_dict(self) -> dict[str, object]:
        value = self.model_dump(mode="json", exclude_none=True)
        value["fluids"] = sorted(self.fluids, key=str.casefold)
        value["filters"] = sorted(
            (item.model_dump(mode="json") for item in self.filters),
            key=lambda item: (str(item["field"]), str(item["value"])),
        )
        return value


def request_id(requests: tuple[PlotRequest, ...]) -> str:
    payload: dict[str, object] = {"plots": [request.canonical_dict() for request in requests]}
    digest = hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()
    return f"viz-{digest}"


def property_plot_request(
    *,
    property_name: str,
    kind: Literal["property_curves", "property_heatmap"],
    fluids: tuple[str, ...],
    x_field: str | None = None,
    filters: tuple[ExactFilter, ...] = (),
    value_scale: PlotScale = "linear",
    color_scale: PlotScale = "linear",
    saturation_coordinate: SaturationCoordinate | None = None,
    output_format: PlotFormat = "png",
) -> PlotRequest:
    return PlotRequest(
        kind=kind,
        property_name=property_name,
        x_field=x_field,
        filters=filters,
        fluids=fluids,
        value_scale=value_scale,
        color_scale=color_scale,
        saturation_coordinate=saturation_coordinate,
        output_format=output_format,
    )


def normalize_public_plot_kind(value: str) -> PlotKindV2:
    normalized = value.strip().replace("-", "_")
    if normalized in {"property_curves", "property_heatmap", "xy", "pv", "ts"}:
        return cast(PlotKindV2, normalized)
    if normalized == "contour":
        raise ValueError(
            "Contour plots interpolate between sampled states and are not supported.\n"
            "Use property-heatmap for a non-interpolated sampled property map."
        )
    if normalized == "curves":
        raise ValueError(
            "Plot kind 'curves' was replaced by 'property-curves'. Use --kind property-curves."
        )
    if normalized == "heatmap":
        raise ValueError("Plot kind 'heatmap' is ambiguous. Use --kind property-heatmap.")
    raise ValueError("plot kind must be one of: property-curves, property-heatmap, xy, pv, ts")


def xy_plot_request(
    *,
    x_field: str,
    y_field: str,
    group_by: str | None,
    fluids: tuple[str, ...],
    filters: tuple[ExactFilter, ...] = (),
    x_scale: PlotScale = "linear",
    y_scale: PlotScale = "linear",
    saturation_coordinate: SaturationCoordinate | None = None,
    output_format: PlotFormat = "png",
) -> PlotRequest:
    return PlotRequest(
        kind="xy",
        x_field=x_field,
        y_field=y_field,
        group_by=group_by,
        filters=filters,
        fluids=fluids,
        x_scale=x_scale,
        y_scale=y_scale,
        saturation_coordinate=saturation_coordinate,
        output_format=output_format,
    )


def thermodynamic_diagram_request(
    *,
    kind: Literal["pv", "ts"],
    fluids: tuple[str, ...],
    filters: tuple[ExactFilter, ...] = (),
    x_scale: PlotScale = "linear",
    y_scale: PlotScale = "linear",
    saturation_coordinate: SaturationCoordinate | None = None,
    output_format: PlotFormat = "png",
) -> PlotRequest:
    return PlotRequest(
        kind=kind,
        filters=filters,
        fluids=fluids,
        x_scale=x_scale,
        y_scale=y_scale,
        saturation_coordinate=saturation_coordinate,
        output_format=output_format,
    )


def parse_exact_filter(value: str) -> ExactFilter:
    field, separator, raw_value = value.partition("=")
    if not separator or not field.strip() or not raw_value.strip():
        raise ValueError("filters must use FIELD=VALUE")
    definition = get_field(field.strip())
    parsed: FilterValue
    if definition.kind == "numeric":
        try:
            parsed = float(raw_value)
        except ValueError as exc:
            raise ValueError(f"numeric filter {field.strip()!r} requires a number") from exc
    else:
        parsed = raw_value.strip()
    return ExactFilter(field=field.strip(), value=parsed)


def _canonical_json_bytes(value: dict[str, object]) -> bytes:
    stable = _stable_value(value)
    text = json.dumps(
        stable,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return (text + "\n").encode("utf-8")


def _stable_value(value: object) -> object:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("visualization request values must be finite")
        if value == 0.0:
            return 0.0
        return float(format(value, ".15g"))
    if isinstance(value, dict):
        return {str(key): _stable_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_stable_value(item) for item in value]
    return value
