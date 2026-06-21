from __future__ import annotations

import hashlib
import json
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from carnopy.visualization.fields import get_field

PlotKindV2 = Literal[
    "property_curves",
    "property_heatmap",
    "xy",
    "pv",
    "ts",
    "legacy_contour",
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
            if definition.required_property != property_name:
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
        property_kinds = {"property_curves", "property_heatmap", "legacy_contour"}
        if self.kind in property_kinds and self.property_name is None:
            raise ValueError(f"{self.kind} requires property_name")
        if self.kind == "xy" and (self.x_field is None or self.y_field is None):
            raise ValueError("xy requires both x_field and y_field")
        if self.kind in {"pv", "ts"} and any(
            value is not None for value in (self.property_name, self.x_field, self.y_field)
        ):
            raise ValueError(
                f"{self.kind} uses fixed axes and rejects property_name/x_field/y_field"
            )
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


def legacy_property_request(
    *,
    property_name: str,
    kind: Literal["curves", "contour"],
    fluids: tuple[str, ...],
    scale: PlotScale,
    coordinate: SaturationCoordinate | None,
) -> PlotRequest:
    return PlotRequest(
        kind="property_curves" if kind == "curves" else "legacy_contour",
        property_name=property_name,
        fluids=fluids,
        value_scale=scale if kind == "curves" else "linear",
        color_scale=scale if kind == "contour" else "linear",
        saturation_coordinate=coordinate,
    )


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
