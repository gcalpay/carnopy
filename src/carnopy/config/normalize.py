from __future__ import annotations

import json
from typing import Any

from carnopy.backends.base import PropertyBackend
from carnopy.config.models import CarnopyConfig, NormalizedConfig
from carnopy.domain.failures import ConfigError
from carnopy.domain.numbers import stable_binary64
from carnopy.domain.units import AXIS_SI_UNITS
from carnopy.sampling.canonical import canonicalize_sampler
from carnopy.sampling.generate import materialize_sampler
from carnopy.sampling.models import Sampler
from carnopy.sampling.projection import (
    MAX_PROJECTED_ROWS,
    projected_row_count,
    sampler_point_count,
)

MAX_ROWS = MAX_PROJECTED_ROWS


def normalize_config(
    config: CarnopyConfig,
    backend: PropertyBackend,
) -> NormalizedConfig:
    if backend.name != config.backend.name or backend.model != config.backend.model:
        raise ConfigError(
            "configured backend does not match the initialized backend: "
            f"configured={config.backend.name}/{config.backend.model}, "
            f"initialized={backend.name}/{backend.model}"
        )
    unsupported_properties = backend.unsupported_properties(config.properties)
    if unsupported_properties:
        raise ConfigError(
            f"CoolProp model {config.backend.model} does not support properties: "
            f"{', '.join(unsupported_properties)}"
        )

    canonical_fluids: list[str] = []
    for requested in config.fluids:
        try:
            canonical_fluids.append(backend.canonicalize_fluid(requested))
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc
    if len(set(canonical_fluids)) != len(canonical_fluids):
        raise ConfigError("fluid aliases resolve to duplicate canonical fluids")
    requested_fluid_canonical_names = list(canonical_fluids)
    canonical_fluids.sort()

    canonical_grid: dict[str, Sampler] = {}
    sampler_counts: dict[str, int] = {}
    for axis, sampler in config.grid.items():
        try:
            canonical_sampler = canonicalize_sampler(axis, sampler)
            sampler_counts[axis] = sampler_point_count(canonical_sampler)
        except ValueError as exc:
            raise ConfigError(f"invalid {axis} sampler: {exc}") from exc
        canonical_grid[axis] = canonical_sampler

    projected_rows = projected_row_count(
        config.mode,
        len(canonical_fluids),
        sampler_counts.values(),
    )
    if projected_rows > MAX_ROWS:
        raise ConfigError(f"projected row count {projected_rows:,} exceeds limit {MAX_ROWS:,}")

    materialized_grid: dict[str, list[float]] = {}
    for axis, canonical_sampler in canonical_grid.items():
        try:
            si_values = materialize_sampler(canonical_sampler)
        except ValueError as exc:
            raise ConfigError(f"invalid {axis} sampler: {exc}") from exc
        stable_values = [stable_binary64(value) for value in si_values]
        if len(set(stable_values)) != len(stable_values):
            raise ConfigError(
                f"invalid {axis} sampler: values collapse to duplicates during "
                "canonical SI serialization"
            )
        materialized_grid[axis] = stable_values

    properties = sorted(config.properties)
    original_grid = {axis: sampler.model_dump(mode="json") for axis, sampler in config.grid.items()}
    return NormalizedConfig(
        schema_version=2,
        document_type="dataset",
        backend=config.backend,
        mode=config.mode,
        fluids=canonical_fluids,
        grid=materialized_grid,
        grid_units={axis: AXIS_SI_UNITS[axis] for axis in materialized_grid},
        properties=properties,
        projected_rows=projected_rows,
        requested_fluid_aliases=list(config.fluids),
        requested_fluid_canonical_names=requested_fluid_canonical_names,
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


def _stable_value(value: Any) -> Any:
    if isinstance(value, float):
        return stable_binary64(value)
    if isinstance(value, dict):
        return {str(key): _stable_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_stable_value(item) for item in value]
    return value
