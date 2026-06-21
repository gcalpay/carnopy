from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from carnopy.visualization.requests import (
    PlotFormat,
    PlotKindV2,
    PlotScale,
    normalize_public_plot_kind,
)

PLOT_NAME_PATTERN = r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$"


class VisualizationPlotConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )

    name: str = Field(pattern=PLOT_NAME_PATTERN)
    kind: PlotKindV2
    property_name: str | None = Field(default=None, alias="property")
    x_field: str | None = Field(default=None, alias="x")
    y_field: str | None = Field(default=None, alias="y")
    group_by: str | None = None
    filters: dict[str, float | str] = Field(default_factory=dict)
    fluids: tuple[str, ...] | None = None
    value_scale: PlotScale = "linear"
    color_scale: PlotScale = "linear"
    x_scale: PlotScale = "linear"
    y_scale: PlotScale = "linear"
    format: PlotFormat | None = None

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("visualization plot kind must be a string")
        return normalize_public_plot_kind(value)

    @field_validator("fluids")
    @classmethod
    def validate_fluids(cls, fluids: tuple[str, ...] | None) -> tuple[str, ...] | None:
        if fluids is None:
            return None
        cleaned = tuple(fluid.strip() for fluid in fluids)
        if not cleaned or any(not fluid for fluid in cleaned):
            raise ValueError("visualization fluids must contain non-empty names")
        if len({fluid.casefold() for fluid in cleaned}) != len(cleaned):
            raise ValueError("duplicate visualization fluid names are not allowed")
        return cleaned


class VisualizationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    format: PlotFormat = "png"
    fluids: tuple[str, ...] = ()
    filters: dict[str, float | str] = Field(default_factory=dict)
    plots: tuple[VisualizationPlotConfig, ...] = Field(min_length=1)

    @field_validator("fluids")
    @classmethod
    def validate_fluids(cls, fluids: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(fluid.strip() for fluid in fluids)
        if any(not fluid for fluid in cleaned):
            raise ValueError("visualization fluids must contain non-empty names")
        if len({fluid.casefold() for fluid in cleaned}) != len(cleaned):
            raise ValueError("duplicate visualization fluid names are not allowed")
        return cleaned

    @model_validator(mode="after")
    def unique_plot_names(self) -> VisualizationConfig:
        names = [plot.name for plot in self.plots]
        if len(set(names)) != len(names):
            raise ValueError("visualization plot names must be unique")
        return self
