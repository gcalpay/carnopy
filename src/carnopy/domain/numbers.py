from __future__ import annotations

import math
from decimal import ROUND_HALF_EVEN, Context, Decimal

CANONICAL_DECIMAL_PRECISION = 50


def canonical_decimal_context() -> Context:
    """Return an isolated context for deterministic private calculations."""

    return Context(prec=CANONICAL_DECIMAL_PRECISION, rounding=ROUND_HALF_EVEN)


def stable_number_text(value: float) -> str:
    """Return Carnopy's canonical text for one finite binary64 value."""

    binary64 = float(value)
    if not math.isfinite(binary64):
        raise ValueError("canonical values must be finite")
    if binary64 == 0.0:
        return "0"
    return format(binary64, ".15g")


def stable_binary64(value: float) -> float:
    """Round one finite binary64 value through Carnopy's canonical text."""

    return float(stable_number_text(value))


def decimal_from_binary64(value: float) -> Decimal:
    """Construct Decimal only from stabilized binary64 decimal text."""

    return Decimal(stable_number_text(value))


def binary64_from_decimal(value: Decimal) -> float:
    """Return a finite Decimal result through binary64 and `.15g`."""

    if not value.is_finite():
        raise ValueError("canonical calculation produced a non-finite value")
    try:
        binary64 = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError("canonical calculation produced a non-finite value") from exc
    return stable_binary64(binary64)
