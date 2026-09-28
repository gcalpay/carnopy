from __future__ import annotations

import math
from fractions import Fraction
from typing import Any

from carnopy.config.normalize import canonical_json_bytes
from carnopy.sources.eligibility import _number
from carnopy.sources.errors import SourceImportError
from carnopy.sources.evidence import EvidenceElement
from carnopy.sources.inventory import identifier, source_identity
from carnopy.sources.metadata import element_payload
from carnopy.sources.numbers import affine_decimal, decimal_text, project


def _json(value: object) -> str:
    return canonical_json_bytes(value).decode("utf-8")  # type: ignore[arg-type]


def _metadata_text(node: EvidenceElement, field: str) -> str | None:
    elements = node.all(field)
    if len(elements) != 1 or elements[0].children:
        return None
    return node.value(field)


def _magnitude(text: str | None, scale: str) -> tuple[float | None, str | None]:
    if text is None:
        return None, None
    value = _number(text)
    if value is None or value < 0:
        raise SourceImportError("invalid_uncertainty", "uncertainty must be finite and nonnegative")
    exact = affine_decimal(text, scale)
    return project(exact), decimal_text(exact)


def _standard(magnitude: float | None, exact: str | None, coverage: str | None) -> float | None:
    if magnitude is None or exact is None or coverage is None:
        return None
    factor = _number(coverage)
    if factor is None or factor <= 0:
        raise SourceImportError("invalid_uncertainty", "coverage factor must be positive")
    rational = Fraction(exact) / Fraction(factor)
    try:
        value = float(rational)
    except OverflowError as exc:
        raise SourceImportError("invalid_uncertainty", "standard uncertainty overflow") from exc
    if not math.isfinite(value) or (rational and not value):
        raise SourceImportError("invalid_uncertainty", "standard uncertainty is unrepresentable")
    return value


def uncertainty_rows(
    definition: EvidenceElement,
    value: EvidenceElement,
    *,
    target: dict[str, Any],
    families: tuple[str, ...],
    unit: str,
    reported_unit: str,
    scale: str = "1",
) -> list[dict[str, Any]]:
    """Keep individual assessments and bounds; never infer k from confidence.

    ThermoML's qualified uncertainty elements express absolute magnitudes in
    their target's units. Relative/unknown extensions remain raw, unsupported
    assessments rather than being interpreted as absolute values.
    """
    rows: list[dict[str, Any]] = []
    for family in families:
        combined = family == "CombinedUncertainty"
        constrained = family == "ConstrUncertainty"
        id_field = "nCombUncertAssessNum" if combined else "nUncertAssessNum"
        definitions = (
            {}
            if constrained
            else {identifier(node, id_field): node for node in definition.all(family)}
        )
        for index, reported in enumerate(value.all(family)):
            number = index if constrained else identifier(reported, id_field)
            declared = reported if constrained else definitions[number]
            coverage_field = "nCombCoverageFactor" if combined else "nCoverageFactor"
            confidence_field = "nCombUncertLevOfConfid" if combined else "nUncertLevOfConfid"
            evaluator_field = "sCombUncertEvaluator" if combined else "sUncertEvaluator"
            metadata_fields = {
                id_field,
                coverage_field,
                confidence_field,
                evaluator_field,
                "sCombUncertEvalMethod" if combined else "sUncertEvalMethod",
            }
            if combined:
                metadata_fields.add("eCombUncertEvalMethod")
            magnitude_fields = {
                "nCombStdUncertValue" if combined else "nStdUncertValue": ("standard", False),
                "nCombExpandUncertValue" if combined else "nExpandUncertValue": ("expanded", False),
            }
            if family != "VarUncertainty" and not constrained:
                magnitude_fields.update(
                    {
                        "AsymCombStdUncert" if combined else "AsymStdUncert": ("standard", True),
                        "AsymCombExpandUncert" if combined else "AsymExpandUncert": (
                            "expanded",
                            True,
                        ),
                    }
                )
            allowed_definition = metadata_fields | (set(magnitude_fields) if constrained else set())
            allowed_value = allowed_definition if constrained else {id_field, *magnitude_fields}
            ambiguous = any(
                len(node.all(field)) > 1
                for node, fields in ((declared, allowed_definition), (reported, allowed_value))
                for field in fields
            ) or any(child.children for child in declared.children if child.name in metadata_fields)
            unsupported = (
                declared.has_attributes
                or reported.has_attributes
                or not declared.child_names <= allowed_definition
                or not reported.child_names <= allowed_value
                or ambiguous
            )
            present = [field for field in magnitude_fields if reported.all(field)]
            # Even an empty/unsupported assessment remains a row with original evidence.
            for field in present or [""]:
                kind, asymmetric = magnitude_fields.get(field, ("unavailable", False))
                locator = f"{target['locator']}/{family}[{number}]" + (f"/{field}" if field else "")
                coverage = _metadata_text(declared, coverage_field)
                confidence = _metadata_text(declared, confidence_field)
                method = [
                    child.text
                    for child in declared.children
                    if child.name
                    in {"sUncertEvalMethod", "sCombUncertEvalMethod", "eCombUncertEvalMethod"}
                ]
                assessment_id = source_identity(
                    "uncertainty-assessment",
                    {
                        "target_id": target["target_id"],
                        "family": family,
                        "number": str(number),
                    },
                )
                row: dict[str, Any] = {
                    **target,
                    "uncertainty_id": source_identity(
                        "uncertainty",
                        {
                            "assessment_id": assessment_id,
                            "representation": field or "unavailable",
                        },
                    ),
                    "assessment_id": assessment_id,
                    "assessment_number": str(number),
                    "locator": locator,
                    "family": family,
                    "classification": kind,
                    "combined": combined,
                    "asymmetric": asymmetric,
                    "basis": "absolute" if not unsupported else "unqualified",
                    "unit": unit,
                    "reported_unit": reported_unit,
                    "reported_value": None,
                    "reported_lower": None,
                    "reported_upper": None,
                    "canonical_decimal": None,
                    "lower_decimal": None,
                    "upper_decimal": None,
                    "value": None,
                    "lower": None,
                    "upper": None,
                    "standard_uncertainty": None,
                    "standard_lower": None,
                    "standard_upper": None,
                    "coverage_factor": coverage,
                    "confidence_level": confidence,
                    "evaluator": _metadata_text(declared, evaluator_field),
                    "method_json": _json(method),
                    "definition_json": _json(element_payload(declared)),
                    "reported_json": _json(element_payload(reported)),
                    "conversion_json": _json(
                        {"scale": scale, "offset": "0", "standard_rule": None}
                    ),
                    "status": "unsupported"
                    if unsupported
                    else "unavailable"
                    if not field
                    else "normalized",
                    "issue": "unsupported_uncertainty_qualifier"
                    if unsupported
                    else "uncertainty_magnitude_unavailable"
                    if not field
                    else None,
                }
                rows.append(row)
                if unsupported or not field:
                    continue
                try:
                    factor = _number(coverage) if coverage is not None else None
                    if coverage is not None and (factor is None or factor <= 0):
                        raise SourceImportError("invalid_uncertainty", "invalid coverage factor")
                    if confidence is not None:
                        level = _number(confidence)
                        if level is None or not 0 < level <= 100:
                            raise SourceImportError(
                                "invalid_uncertainty", "invalid confidence level"
                            )
                    if asymmetric:
                        bounds = reported.one(field)
                        assert bounds is not None
                        if not bounds.child_names <= {"nNegativeValue", "nPositiveValue"}:
                            row.update(
                                status="unsupported", issue="unsupported_uncertainty_qualifier"
                            )
                            continue
                        row["reported_lower"] = bounds.value("nNegativeValue")
                        row["reported_upper"] = bounds.value("nPositiveValue")
                        row["lower"], row["lower_decimal"] = _magnitude(
                            row["reported_lower"], scale
                        )
                        row["upper"], row["upper_decimal"] = _magnitude(
                            row["reported_upper"], scale
                        )
                        if row["lower"] is None or row["upper"] is None:
                            row.update(status="unavailable", issue="asymmetric_bound_unavailable")
                    else:
                        row["reported_value"] = reported.value(field)
                        row["value"], row["canonical_decimal"] = _magnitude(
                            row["reported_value"], scale
                        )
                        if row["value"] is None:
                            row.update(
                                status="unavailable", issue="uncertainty_magnitude_unavailable"
                            )
                    rule = (
                        "reported_standard"
                        if kind == "standard"
                        else "expanded / reported_coverage_factor"
                        if coverage is not None
                        else None
                    )
                    for suffix, exact_field in (
                        ("uncertainty", "canonical_decimal"),
                        ("lower", "lower_decimal"),
                        ("upper", "upper_decimal"),
                    ):
                        field_value = "value" if suffix == "uncertainty" else suffix
                        row[f"standard_{suffix}"] = (
                            row[field_value]
                            if kind == "standard"
                            else _standard(row[field_value], row[exact_field], coverage)
                        )
                    row["conversion_json"] = _json(
                        {
                            "scale": scale,
                            "offset": "0",
                            "standard_rule": rule,
                            "coverage_factor": coverage,
                        }
                    )
                except SourceImportError:
                    row.update(status="invalid", issue="invalid_uncertainty")
                    row["standard_uncertainty"] = row["standard_lower"] = row["standard_upper"] = (
                        None
                    )
    return rows
