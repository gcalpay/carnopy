from __future__ import annotations

import math
from decimal import Context, Decimal, Inexact
from typing import Any

from carnopy.sources.eligibility import _number
from carnopy.sources.errors import SourceImportError


def decimal_text(value: Decimal) -> str:
    """Exact, context-independent text; reported trailing zeros live in provenance."""
    if not value:
        return "0"
    sign, digits, exponent = value.as_tuple()
    assert isinstance(exponent, int)
    trimmed = list(digits)
    while trimmed[-1] == 0:
        trimmed.pop()
        exponent += 1
    return str(Decimal((sign, tuple(trimmed), exponent)))


def affine_decimal(text: str, scale: str = "1", offset: str = "0") -> Decimal:
    value = _number(text)
    if value is None:
        raise SourceImportError("invalid_numeric_evidence", "nonfinite or unrepresentable value")
    if not value:
        return Decimal(offset)
    # Unlike generated sampler values, evidence must not pass through .15g or a
    # fixed 50-digit context. Size precision to the exact reported operands.
    operands = (value, Decimal(scale), Decimal(offset))
    precision = (
        sum(len(item.as_tuple().digits) for item in operands)
        + sum(abs(int(item.as_tuple().exponent)) for item in operands if item)
        + 4
    )
    context = Context(prec=precision, traps=[Inexact])
    return context.add(context.multiply(value, operands[1]), operands[2])


def project(value: Decimal) -> float:
    result = float(value)
    if not math.isfinite(result) or (value and not result):
        raise SourceImportError("nonrepresentable_normalized_value", "binary64 projection failed")
    return result


def conversion(
    *,
    locator: str,
    quantity: str,
    reported_value: str,
    reported_digits: str | None,
    reported_unit: str,
    canonical_unit: str,
    scale: str = "1",
    offset: str = "0",
) -> dict[str, Any]:
    exact = affine_decimal(reported_value, scale, offset)
    binary64 = project(exact)
    return {
        "locator": locator,
        "quantity": quantity,
        "reported_value": reported_value,
        "reported_digits": reported_digits,
        "reported_unit": reported_unit,
        "canonical_unit": canonical_unit,
        "rule": "value * scale + offset",
        "scale": scale,
        "offset": offset,
        "canonical_decimal": decimal_text(exact),
        "binary64": binary64,
        "binary64_hex": binary64.hex(),
        "binary64_exact": Decimal.from_float(binary64) == exact,
    }
