from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal
from typing import TypeAlias

from carnopy.domain.numbers import (
    binary64_from_decimal,
    canonical_decimal_context,
    decimal_from_binary64,
    stable_binary64,
    stable_number_text,
)
from carnopy.domain.units import AXIS_SI_UNITS, UnitDefinition, validate_axis_unit
from carnopy.sampling.models import (
    ExplicitSampler,
    GeomspaceSampler,
    LinspaceSampler,
    LogspaceSampler,
    Sampler,
    StepspaceSampler,
)

CanonicalFieldValue: TypeAlias = int | str | tuple[str, ...]


@dataclass(frozen=True)
class CanonicalSamplerKey:
    """Exact identity of one canonical SI sampler definition."""

    axis: str
    kind: str
    unit: str
    fields: tuple[tuple[str, CanonicalFieldValue], ...]


def canonicalize_sampler(axis: str, sampler: Sampler) -> Sampler:
    """Convert a valid declared sampler definition to deterministic SI."""

    definition = validate_axis_unit(axis, sampler.unit)
    _validate_supported_combination(axis, sampler, definition)
    context = canonical_decimal_context()
    scale = decimal_from_binary64(definition.scale)
    offset = decimal_from_binary64(definition.offset)
    unit = AXIS_SI_UNITS[axis]

    if isinstance(sampler, ExplicitSampler):
        values = [_to_si(context, value, scale, offset) for value in sampler.values]
        _validate_physical_coordinates(axis, values)
        return ExplicitSampler(kind="explicit", values=values, unit=unit)
    if isinstance(sampler, LinspaceSampler):
        start = _to_si(context, sampler.start, scale, offset)
        stop = _to_si(context, sampler.stop, scale, offset)
        _validate_physical_coordinates(axis, [start, stop])
        return LinspaceSampler(
            kind="linspace",
            start=start,
            stop=stop,
            num=sampler.num,
            unit=unit,
        )
    if isinstance(sampler, StepspaceSampler):
        start = _to_si(context, sampler.start, scale, offset)
        stop = _to_si(context, sampler.stop, scale, offset)
        step = _scale_only(context, sampler.step, scale)
        _validate_physical_coordinates(axis, [start, stop])
        return StepspaceSampler(
            kind="stepspace",
            start=start,
            stop=stop,
            step=step,
            unit=unit,
        )
    if isinstance(sampler, GeomspaceSampler):
        start = _to_si(context, sampler.start, scale, offset)
        stop = _to_si(context, sampler.stop, scale, offset)
        _validate_physical_coordinates(axis, [start, stop])
        return GeomspaceSampler(
            kind="geomspace",
            start=start,
            stop=stop,
            num=sampler.num,
            unit=unit,
        )
    if isinstance(sampler, LogspaceSampler):
        base = stable_binary64(sampler.base)
        shift = _logspace_shift(context, scale, base)
        start_exp = binary64_from_decimal(
            context.add(decimal_from_binary64(sampler.start_exp), shift)
        )
        stop_exp = binary64_from_decimal(
            context.add(decimal_from_binary64(sampler.stop_exp), shift)
        )
        return LogspaceSampler(
            kind="logspace",
            start_exp=start_exp,
            stop_exp=stop_exp,
            num=sampler.num,
            base=base,
            unit=unit,
        )
    raise TypeError(f"unsupported sampler type: {type(sampler).__name__}")


def canonical_sampler_key(axis: str, sampler: Sampler) -> CanonicalSamplerKey:
    """Return the exact canonical definition key for one declared sampler."""

    canonical = canonicalize_sampler(axis, sampler)
    if isinstance(canonical, ExplicitSampler):
        fields: tuple[tuple[str, CanonicalFieldValue], ...] = (
            ("values", tuple(stable_number_text(value) for value in canonical.values)),
        )
    elif isinstance(canonical, (LinspaceSampler, GeomspaceSampler)):
        fields = (
            ("start", stable_number_text(canonical.start)),
            ("stop", stable_number_text(canonical.stop)),
            ("num", canonical.num),
        )
    elif isinstance(canonical, StepspaceSampler):
        fields = (
            ("start", stable_number_text(canonical.start)),
            ("stop", stable_number_text(canonical.stop)),
            ("step", stable_number_text(canonical.step)),
        )
    elif isinstance(canonical, LogspaceSampler):
        fields = (
            ("start_exp", stable_number_text(canonical.start_exp)),
            ("stop_exp", stable_number_text(canonical.stop_exp)),
            ("num", canonical.num),
            ("base", stable_number_text(canonical.base)),
        )
    else:  # pragma: no cover - exhaustive type guard
        raise TypeError(f"unsupported sampler type: {type(canonical).__name__}")
    return CanonicalSamplerKey(
        axis=axis,
        kind=canonical.kind,
        unit=canonical.unit,
        fields=fields,
    )


def convert_sampler_unit(axis: str, sampler: Sampler, target_unit: str) -> Sampler:
    """Return an exact-key candidate expressed in ``target_unit``.

    This is a lightweight definition transformation.  It never materializes a
    sampling grid; callers must still compare canonical keys before accepting
    the returned representation.
    """

    target = validate_axis_unit(axis, target_unit)
    canonical = canonicalize_sampler(axis, sampler)
    context = canonical_decimal_context()
    scale = decimal_from_binary64(target.scale)
    offset = decimal_from_binary64(target.offset)

    if isinstance(canonical, ExplicitSampler):
        return ExplicitSampler(
            kind="explicit",
            values=[_from_si(context, value, scale, offset) for value in canonical.values],
            unit=target_unit,
        )
    if isinstance(canonical, LinspaceSampler):
        return LinspaceSampler(
            kind="linspace",
            start=_from_si(context, canonical.start, scale, offset),
            stop=_from_si(context, canonical.stop, scale, offset),
            num=canonical.num,
            unit=target_unit,
        )
    if isinstance(canonical, StepspaceSampler):
        return StepspaceSampler(
            kind="stepspace",
            start=_from_si(context, canonical.start, scale, offset),
            stop=_from_si(context, canonical.stop, scale, offset),
            step=_unscale(context, canonical.step, scale),
            unit=target_unit,
        )
    if isinstance(canonical, GeomspaceSampler):
        if target.offset != 0.0:
            raise ValueError("geomspace unit changes require scale-only units")
        return GeomspaceSampler(
            kind="geomspace",
            start=_from_si(context, canonical.start, scale, offset),
            stop=_from_si(context, canonical.stop, scale, offset),
            num=canonical.num,
            unit=target_unit,
        )
    if isinstance(canonical, LogspaceSampler):
        if target.offset != 0.0:
            raise ValueError("logspace unit changes require scale-only units")
        shift = _logspace_shift(context, scale, canonical.base)
        return LogspaceSampler(
            kind="logspace",
            start_exp=binary64_from_decimal(
                context.subtract(decimal_from_binary64(canonical.start_exp), shift)
            ),
            stop_exp=binary64_from_decimal(
                context.subtract(decimal_from_binary64(canonical.stop_exp), shift)
            ),
            num=canonical.num,
            base=canonical.base,
            unit=target_unit,
        )
    raise TypeError(f"unsupported sampler type: {type(canonical).__name__}")


def _validate_supported_combination(
    axis: str,
    sampler: Sampler,
    definition: UnitDefinition,
) -> None:
    if not isinstance(sampler, (GeomspaceSampler, LogspaceSampler)):
        return
    if definition.offset != 0.0:
        raise ValueError("geomspace/logspace temperature sampling requires unit K")
    if axis == "vapor_mass_fraction":
        raise ValueError("geomspace/logspace is unsupported for vapor_mass_fraction")


def _to_si(
    context: Context,
    value: float,
    scale: Decimal,
    offset: Decimal,
) -> float:
    declared = decimal_from_binary64(value)
    return binary64_from_decimal(context.add(context.multiply(declared, scale), offset))


def _scale_only(context: Context, value: float, scale: Decimal) -> float:
    return binary64_from_decimal(context.multiply(decimal_from_binary64(value), scale))


def _from_si(
    context: Context,
    value: float,
    scale: Decimal,
    offset: Decimal,
) -> float:
    return binary64_from_decimal(
        context.divide(context.subtract(decimal_from_binary64(value), offset), scale)
    )


def _unscale(context: Context, value: float, scale: Decimal) -> float:
    return binary64_from_decimal(context.divide(decimal_from_binary64(value), scale))


def _logspace_shift(context: Context, scale: Decimal, base: float) -> Decimal:
    if scale == Decimal(1):
        return Decimal(0)
    if scale <= 0:
        raise ValueError("logspace unit scale must be positive")
    decimal_base = decimal_from_binary64(base)
    return context.divide(context.ln(scale), context.ln(decimal_base))


def _validate_physical_coordinates(axis: str, values: list[float]) -> None:
    if axis == "temperature" and any(value <= 0.0 for value in values):
        raise ValueError("temperature values must be above absolute zero")
    if axis == "pressure" and any(value <= 0.0 for value in values):
        raise ValueError("pressure values must be greater than zero")
    if axis == "vapor_mass_fraction" and any(value < 0.0 or value > 1.0 for value in values):
        raise ValueError("vapor_mass_fraction values must be between 0 and 1")
