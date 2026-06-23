from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from carnopy.config.models import CoolPropModel, Mode
from carnopy.config.outputs import OutputConfig
from carnopy.domain.properties import PROPERTY_REGISTRY
from carnopy.sampling.models import Sampler
from carnopy.visualization.requests import PlotFormat, PlotScale


class SweepBackendConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal["coolprop"]
    models: tuple[CoolPropModel, ...] = Field(min_length=2)
    reference_model: CoolPropModel

    @field_validator("models", mode="before")
    @classmethod
    def canonical_models(cls, models: object) -> object:
        if not isinstance(models, (list, tuple)):
            return models
        return tuple(str(model).strip().lower() for model in models)

    @field_validator("reference_model", mode="before")
    @classmethod
    def canonical_reference_model(cls, model: object) -> str:
        if not isinstance(model, str):
            raise ValueError("reference_model must be a string")
        return model.strip().lower()

    @model_validator(mode="after")
    def selected_reference(self) -> SweepBackendConfig:
        if len(set(self.models)) != len(self.models):
            raise ValueError("duplicate backend models are not allowed")
        if self.reference_model not in self.models:
            raise ValueError("reference_model must be one of backend.models")
        return self


class ComparisonPlotConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
    kind: Literal["property_comparison"]
    fluid: str
    property_name: str = Field(alias="property")
    x_field: Literal["temperature", "pressure", "vapor_mass_fraction"] = Field(alias="x")
    group_by: (
        Literal["temperature", "pressure", "vapor_mass_fraction", "saturation_endpoint"] | None
    ) = None
    filters: dict[str, float | str] = Field(default_factory=dict)
    models: tuple[CoolPropModel, ...] | None = None
    value_scale: PlotScale = "linear"
    format: PlotFormat | None = None

    @field_validator("fluid")
    @classmethod
    def non_empty_fluid(cls, fluid: str) -> str:
        cleaned = fluid.strip()
        if not cleaned:
            raise ValueError("comparison plot fluid must not be empty")
        return cleaned

    @field_validator("models", mode="before")
    @classmethod
    def canonical_models(cls, models: object) -> object:
        if models is None or not isinstance(models, (list, tuple)):
            return models
        return tuple(str(model).strip().lower() for model in models)

    @model_validator(mode="after")
    def valid_plot(self) -> ComparisonPlotConfig:
        if self.property_name not in PROPERTY_REGISTRY:
            raise ValueError(f"unsupported comparison property: {self.property_name}")
        if self.models is not None and len(set(self.models)) != len(self.models):
            raise ValueError("duplicate comparison plot models are not allowed")
        return self


class ComparisonPlotsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    format: PlotFormat = "png"
    plots: tuple[ComparisonPlotConfig, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_plot_names(self) -> ComparisonPlotsConfig:
        names = [plot.name for plot in self.plots]
        if len(set(names)) != len(names):
            raise ValueError("comparison plot names must be unique")
        return self


class ModelSweepConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    schema_version: Literal[2]
    document_type: Literal["model_sweep"]
    backend: SweepBackendConfig
    mode: Mode
    fluids: list[str] = Field(min_length=1)
    grid: dict[str, Sampler]
    properties: list[str] = Field(min_length=1)
    outputs: OutputConfig = Field(default_factory=OutputConfig)
    comparison_plots: ComparisonPlotsConfig | None = None

    @field_validator("fluids")
    @classmethod
    def unique_requested_fluids(cls, fluids: list[str]) -> list[str]:
        cleaned = [fluid.strip() for fluid in fluids]
        if any(not fluid for fluid in cleaned):
            raise ValueError("fluid names must not be empty")
        if len({fluid.casefold() for fluid in cleaned}) != len(cleaned):
            raise ValueError("duplicate requested fluid names are not allowed")
        return cleaned

    @field_validator("properties")
    @classmethod
    def known_unique_properties(cls, properties: list[str]) -> list[str]:
        if len(set(properties)) != len(properties):
            raise ValueError("duplicate requested properties are not allowed")
        unknown = sorted(set(properties) - PROPERTY_REGISTRY.keys())
        if unknown:
            raise ValueError(f"unsupported properties: {', '.join(unknown)}")
        return properties

    @model_validator(mode="before")
    @classmethod
    def reject_dataset_visualization(cls, payload: Any) -> Any:
        if isinstance(payload, dict) and "visualization" in payload:
            raise ValueError(
                "model_sweep rejects dataset visualization; use comparison_plots instead"
            )
        return payload

    @model_validator(mode="after")
    def mode_grid_contract(self) -> ModelSweepConfig:
        axes = set(self.grid)
        allowed = {"temperature", "pressure", "vapor_mass_fraction"}
        unknown = axes - allowed
        if unknown:
            raise ValueError(f"unsupported grid axes: {', '.join(sorted(unknown))}")
        if self.mode == "property_table" and axes != {"temperature", "pressure"}:
            raise ValueError("property_table requires exactly temperature and pressure grids")
        if self.mode == "saturation_table" and axes not in (
            {"temperature"},
            {"pressure"},
        ):
            raise ValueError("saturation_table requires exactly one of temperature or pressure")
        if self.mode == "vapor_mass_fraction_table" and axes not in (
            {"temperature", "vapor_mass_fraction"},
            {"pressure", "vapor_mass_fraction"},
        ):
            raise ValueError(
                "vapor_mass_fraction_table requires vapor_mass_fraction and "
                "exactly one of temperature or pressure"
            )
        if self.comparison_plots is not None:
            selected = set(self.backend.models)
            for plot in self.comparison_plots.plots:
                if plot.models is not None and not set(plot.models).issubset(selected):
                    raise ValueError(
                        f"comparison plot {plot.name!r} selects models outside backend.models"
                    )
        return self
