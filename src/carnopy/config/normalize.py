from __future__ import annotations

import json
import math
from typing import Any

from carnopy.backends.base import PropertyBackend
from carnopy.config.models import CarnopyConfig, NormalizedConfig
from carnopy.domain.failures import ConfigError
from carnopy.domain.units import AXIS_SI_UNITS, convert_axis_values_to_si, validate_axis_unit
from carnopy.sampling.generate import materialize_sampler
from carnopy.sampling.models import GeomspaceSampler, LogspaceSampler

MAX_ROWS = 1_000_000


def normalize_config(
    config: CarnopyConfig,
    backend: PropertyBackend,
) -> NormalizedConfig:
    canonical_fluids: list[str] = []
    for requested in config.fluids:
        try:
            canonical_fluids.append(backend.canonicalize_fluid(requested))
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc
    if len(set(canonical_fluids)) != len(canonical_fluids):
        raise ConfigError("fluid aliases resolve to duplicate canonical fluids")
    canonical_fluids.sort()

    materialized_grid: dict[str, list[float]] = {}
    for axis, sampler in config.grid.items():
        try:
            validate_axis_unit(axis, sampler.unit)
            if isinstance(sampler, (GeomspaceSampler, LogspaceSampler)):
                if sampler.unit == "degC":
                    raise ValueError("geomspace/logspace temperature sampling requires unit K")
                if axis == "vapor_mass_fraction":
                    raise ValueError("geomspace/logspace is unsupported for vapor_mass_fraction")
            declared_values = materialize_sampler(sampler)
            si_values = convert_axis_values_to_si(axis, sampler.unit, declared_values)
        except ValueError as exc:
            raise ConfigError(f"invalid {axis} sampler: {exc}") from exc
        stable_values = [_stable_float(value) for value in si_values]
        if len(set(stable_values)) != len(stable_values):
            raise ConfigError(
                f"invalid {axis} sampler: values collapse to duplicates during "
                "canonical SI serialization"
            )
        materialized_grid[axis] = stable_values

    properties = sorted(config.properties)
    projected_rows = _projected_rows(config.mode, canonical_fluids, materialized_grid)
    if projected_rows > MAX_ROWS:
        raise ConfigError(f"projected row count {projected_rows:,} exceeds limit {MAX_ROWS:,}")

    original_grid = {axis: sampler.model_dump(mode="json") for axis, sampler in config.grid.items()}
    return NormalizedConfig(
        schema_version=1,
        backend="coolprop",
        mode=config.mode,
        fluids=canonical_fluids,
        grid=materialized_grid,
        grid_units={axis: AXIS_SI_UNITS[axis] for axis in materialized_grid},
        properties=properties,
        projected_rows=projected_rows,
        requested_fluid_aliases=list(config.fluids),
        requested_property_order=list(config.properties),
        original_grid=original_grid,
    )


def canonical_json_bytes(value: dict[str, object]) -> bytes:
    stable = _stable_value(value)
    text = json.dumps(
        stable,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return (text + "\n").encode("utf-8")


def _projected_rows(
    mode: str,
    fluids: list[str],
    grid: dict[str, list[float]],
) -> int:
    rows = len(fluids)
    for values in grid.values():
        rows *= len(values)
    if mode == "saturation_table":
        rows *= 2
    return rows


def _stable_float(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("canonical values must be finite")
    if value == 0.0:
        return 0.0
    return float(format(value, ".15g"))


def _stable_value(value: Any) -> Any:
    if isinstance(value, float):
        return _stable_float(value)
    if isinstance(value, dict):
        return {str(key): _stable_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_stable_value(item) for item in value]
    return value
