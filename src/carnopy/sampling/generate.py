from __future__ import annotations

import math

import numpy as np

from carnopy.sampling.models import (
    ExplicitSampler,
    GeomspaceSampler,
    LinspaceSampler,
    LogspaceSampler,
    Sampler,
    StepspaceSampler,
)
from carnopy.sampling.projection import stepspace_point_count


def materialize_sampler(sampler: Sampler) -> list[float]:
    if isinstance(sampler, ExplicitSampler):
        values = list(sampler.values)
    elif isinstance(sampler, LinspaceSampler):
        values = np.linspace(sampler.start, sampler.stop, sampler.num).tolist()
    elif isinstance(sampler, StepspaceSampler):
        values = _materialize_stepspace(sampler)
    elif isinstance(sampler, GeomspaceSampler):
        values = np.geomspace(sampler.start, sampler.stop, sampler.num).tolist()
    elif isinstance(sampler, LogspaceSampler):
        values = np.logspace(
            sampler.start_exp,
            sampler.stop_exp,
            sampler.num,
            base=sampler.base,
        ).tolist()
    else:  # pragma: no cover - exhaustive type guard
        raise TypeError(f"unsupported sampler type: {type(sampler).__name__}")
    if len(set(values)) != len(values):
        raise ValueError("sampler materialized duplicate values")
    if any(not math.isfinite(value) for value in values):
        raise ValueError("sampler materialized non-finite values")
    return [0.0 if value == 0.0 else float(value) for value in values]


def _materialize_stepspace(sampler: StepspaceSampler) -> list[float]:
    point_count = stepspace_point_count(sampler)
    return [float(value) for value in np.linspace(sampler.start, sampler.stop, point_count)]
