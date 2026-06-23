from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from carnopy.config.outputs import OutputConfig
from carnopy.config.visualization import VisualizationConfig
from carnopy.domain.properties import PROPERTY_REGISTRY
from carnopy.sampling.models import Sampler

Mode = Literal["property_table", "saturation_table", "vapor_mass_fraction_table"]
CoolPropModel = Literal["heos", "pr", "srk"]


class BackendConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal["coolprop"]
    model: CoolPropModel

    @field_validator("model", mode="before")
    @classmethod
    def canonical_model(cls, model: object) -> str:
        if not isinstance(model, str):
            raise ValueError("backend model must be a string")
        return model.strip().lower()


class CarnopyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[2]
    document_type: Literal["dataset"]
    backend: BackendConfig
    mode: Mode
    fluids: list[str] = Field(min_length=1)
    grid: dict[str, Sampler]
    properties: list[str] = Field(min_length=1)
    outputs: OutputConfig = Field(default_factory=OutputConfig)
    visualization: VisualizationConfig | None = None

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

    @model_validator(mode="after")
    def mode_grid_contract(self) -> CarnopyConfig:
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
        return self


class NormalizedConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[2]
    document_type: Literal["dataset"]
    backend: BackendConfig
    mode: Mode
    fluids: list[str]
    grid: dict[str, list[float]]
    grid_units: dict[str, str]
    properties: list[str]
    projected_rows: int
    requested_fluid_aliases: list[str]
    requested_fluid_canonical_names: list[str]
    requested_property_order: list[str]
    original_grid: dict[str, Any]

    def executable_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "document_type": self.document_type,
            "backend": self.backend.model_dump(mode="json"),
            "mode": self.mode,
            "fluids": self.fluids,
            "grid": {
                axis: {"unit": self.grid_units[axis], "values": values}
                for axis, values in sorted(self.grid.items())
            },
            "properties": self.properties,
        }
