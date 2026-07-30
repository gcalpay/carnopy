from __future__ import annotations

import math
from collections.abc import Iterable

from carnopy.domain.numbers import (
    binary64_from_decimal,
    canonical_decimal_context,
    decimal_from_binary64,
)
from carnopy.sampling.models import (
    ExplicitSampler,
    GeomspaceSampler,
    LinspaceSampler,
    LogspaceSampler,
    Sampler,
    StepspaceSampler,
)

MAX_PROJECTED_ROWS = 1_000_000
STEPSPACE_RTOL = 1e-12
STEPSPACE_ATOL = 1e-12


def sampler_point_count(sampler: Sampler) -> int:
    """Return the exact number of points without materializing a numeric grid."""

    if isinstance(sampler, ExplicitSampler):
        return len(sampler.values)
    if isinstance(sampler, (LinspaceSampler, GeomspaceSampler, LogspaceSampler)):
        return sampler.num
    if isinstance(sampler, StepspaceSampler):
        return stepspace_point_count(sampler)
    raise TypeError(f"unsupported sampler type: {type(sampler).__name__}")


def linspace_spacing(sampler: LinspaceSampler) -> float:
    """Return the signed declared-unit spacing without materializing a grid."""

    context = canonical_decimal_context()
    span = context.subtract(
        decimal_from_binary64(sampler.stop),
        decimal_from_binary64(sampler.start),
    )
    return binary64_from_decimal(context.divide(span, context.create_decimal(sampler.num - 1)))


def stepspace_point_count(sampler: StepspaceSampler) -> int:
    """Count an inclusive stepspace using production reachability semantics."""

    raw_steps = (sampler.stop - sampler.start) / sampler.step
    if not math.isfinite(raw_steps):
        raise ValueError("stepspace stop is not reachable by a finite number of steps")
    step_count = round(raw_steps)
    if step_count < 1 or not math.isclose(
        raw_steps,
        step_count,
        rel_tol=STEPSPACE_RTOL,
        abs_tol=STEPSPACE_ATOL,
    ):
        raise ValueError("stepspace stop is not reachable by an integer number of steps")
    return step_count + 1


def projected_row_count(
    mode: str,
    fluid_count: int,
    sampler_counts: Iterable[int],
) -> int:
    """Project final rows from exact counts without importing scientific arrays."""

    if fluid_count < 0:
        raise ValueError("fluid count cannot be negative")
    rows = fluid_count
    for count in sampler_counts:
        if count < 0:
            raise ValueError("sampler count cannot be negative")
        rows *= count
    if mode == "saturation_table":
        rows *= 2
    return rows
