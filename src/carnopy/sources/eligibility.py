from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Literal

from carnopy.sources.evidence import DatasetEvidence, EvidenceElement, RecordEvidence
from carnopy.sources.inventory import component_number, identifier
from carnopy.sources.metadata import data_origin

RecordStatus = Literal["eligible", "unsupported", "invalid", "unselected"]
_DENSITIES = {"Mass density, kg/m3": "mass_density", "Amount density, mol/m3": "amount_density"}
_PHASES = {"Liquid", "Gas", "Fluid (supercritical or subcritical phases)"}
_DATASET_FIELDS = {
    "nPureOrMixtureDataNumber",
    "Component",
    "PhaseID",
    "Property",
    "Variable",
    "Constraint",
    "eExpPurpose",
    "sCompiler",
    "sContributor",
    "dateDateAdded",
}
_PROPERTY_FIELDS = {
    "nPropNumber",
    "Property-MethodID",
    "PropPhaseID",
    "ePresentation",
    "CombinedUncertainty",
    "PropUncertainty",
    "PropRepeatability",
    "PropDeviceSpec",
    "CurveDev",
}
_VALUE_FIELDS = {
    "nPropNumber",
    "nPropValue",
    "nPropDigits",
    "CombinedUncertainty",
    "PropUncertainty",
    "PropRepeatability",
    "nPropDeviceSpecValue",
    "CurveDev",
}
_COORDINATES: dict[str, tuple[str, str, str]] = {
    "Temperature, K": ("temperature", "1", "0"),
    "Temperature, degC": ("temperature", "1", "273.15"),
    "Pressure, Pa": ("pressure", "1", "0"),
    "Pressure, kPa": ("pressure", "1000", "0"),
    "Pressure, MPa": ("pressure", "1000000", "0"),
    "Pressure, bar": ("pressure", "100000", "0"),
    "Pressure, atm": ("pressure", "101325", "0"),
}


@dataclass(frozen=True, slots=True)
class Eligibility:
    status: RecordStatus
    quantity: str | None
    reported_quantity: str | None
    phase: str | None
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]


def _unknown(node: EvidenceElement, allowed: set[str]) -> bool:
    return bool(node.attributes or not node.child_names <= allowed)


def _number(value: str | None) -> Decimal | None:
    if value is None or not re.fullmatch(
        r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?", value
    ):
        return None
    try:
        result = Decimal(value)
        projected = float(result)
    except (InvalidOperation, ValueError, OverflowError):
        return None
    if not result.is_finite() or not math.isfinite(projected) or (result and not projected):
        return None
    return result


def _precision(node: EvidenceElement, field: str) -> int | None:
    text = node.value(field)
    if text is None:
        return -1 if node.one(field) is not None else None
    if not re.fullmatch(r"[0-9]{1,4}", text) or not 1 <= int(text) <= 1024:
        return -1
    return int(text)


def _phase(node: EvidenceElement, group: str, field: str) -> str | None:
    values = node.all(group)
    if len(values) != 1:
        return None
    return values[0].value(field)


def _property(node: EvidenceElement) -> tuple[str | None, bool]:
    method = node.one("Property-MethodID")
    group = method.one("PropertyGroup") if method else None
    family = group.children[0] if group and len(group.children) == 1 else None
    name = family.value("ePropName") if family else None
    unknown = (
        method is None
        or group is None
        or family is None
        or _unknown(method, {"PropertyGroup"})
        or family.name != "VolumetricProp"
        or _unknown(
            family, {"ePropName", "eMethodName", "sMethodName", "Prediction", "CriticalEvaluation"}
        )
        or sum(
            len(family.all(field))
            for field in ("eMethodName", "sMethodName", "Prediction", "CriticalEvaluation")
        )
        > 1
    )
    return name, unknown


@dataclass(frozen=True)
class _DefinitionAssessment:
    quantity: str | None
    reported: str | None
    phase: str | None
    unsupported: tuple[str, ...]
    invalid: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass
class EligibilityCache:
    """One dataset's definitions and only the currently visited point's context."""

    properties: dict[int, EvidenceElement]
    variables: dict[int, EvidenceElement]
    definitions: dict[int, _DefinitionAssessment] = field(default_factory=dict)
    point_index: int = -1
    contexts: dict[str | None, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = field(
        default_factory=dict
    )


def _definition_assessment(
    dataset: DatasetEvidence, definition: EvidenceElement
) -> _DefinitionAssessment:
    reported, unqualified_property = _property(definition)
    quantity = _DENSITIES.get(reported or "")
    phase = _phase(definition, "PropPhaseID", "ePropPhase")
    unsupported: list[str] = []
    invalid: list[str] = []
    origin, _ = data_origin(definition)
    warnings = ["data_origin_unclassified"] if origin == "unknown" else []
    if origin in {"predicted", "critically_evaluated"}:
        warnings.append(f"data_origin_{origin}")
    if dataset.kind != "PureOrMixtureData":
        unsupported.append("unsupported_dataset_kind")
    if not 1 <= len(dataset.component_numbers) <= 2:
        unsupported.append("unsupported_component_count")
    if len(dataset.component_numbers) != len(dataset.definition.all("Component")):
        unsupported.append("unsupported_component_identity")
    if unqualified_property or quantity is None:
        unsupported.append("unsupported_property")
    if definition.value("ePresentation") != "Direct value, X":
        unsupported.append("unsupported_presentation")
    if (
        _unknown(dataset.definition, _DATASET_FIELDS)
        or _unknown(definition, _PROPERTY_FIELDS)
        or definition.has_attributes
    ):
        unsupported.append("unsupported_scientific_qualifier")
    phases = {node.value("ePhase") for node in dataset.definition.all("PhaseID")[:2]}
    if len(dataset.definition.all("PhaseID")) > 1 or len(definition.all("PropPhaseID")) > 1:
        unsupported.append("equilibrium_not_supported")
    if phase is None:
        warnings.append("property_phase_unavailable")
    elif phase not in _PHASES:
        unsupported.append("unsupported_phase")
    elif phases and phase not in phases:
        invalid.append("phase_conflict")
    for node in definition.all("PropPhaseID")[:2]:
        if _unknown(node, {"ePropPhase"}) or not node.value("ePropPhase"):
            unsupported.append("unsupported_phase_qualifier")
    for node in dataset.definition.all("PhaseID")[:2]:
        if _unknown(node, {"ePhase"}) or not node.value("ePhase"):
            unsupported.append("unsupported_phase_qualifier")
    for node in dataset.definition.all("Component")[:3]:
        if _unknown(node, {"RegNum", "nSampleNm"}):
            unsupported.append("unsupported_component_qualifier")
        reference = node.one("RegNum")
        if reference is not None and _unknown(reference, {"nOrgNum"}):
            unsupported.append("unsupported_component_identity")
    return _DefinitionAssessment(
        quantity, reported, phase, tuple(unsupported), tuple(invalid), tuple(warnings)
    )


def assess_record(
    dataset: DatasetEvidence, record: RecordEvidence, *, cache: EligibilityCache
) -> Eligibility:
    if record.property_number not in cache.definitions:
        cache.definitions[record.property_number] = _definition_assessment(
            dataset,
            cache.properties[record.property_number],
        )
    base = cache.definitions[record.property_number]
    quantity, reported, phase = base.quantity, base.reported, base.phase
    unsupported, invalid, warnings = list(base.unsupported), list(base.invalid), list(base.warnings)
    if (
        _unknown(record.value, _VALUE_FIELDS)
        or record.point_qualifiers
        or record.value.has_attributes
    ):
        unsupported.append("unsupported_scientific_qualifier")
    if _number(record.value.value("nPropValue")) is None:
        invalid.append("invalid_property_value")
    if _precision(record.value, "nPropDigits") == -1:
        invalid.append("invalid_reported_precision")
    if record.value.value("nPropDigits") is None:
        warnings.append("property_precision_unavailable")
    if not record.value.all("CombinedUncertainty") and not record.value.all("PropUncertainty"):
        warnings.append("property_uncertainty_unavailable")
    else:
        warnings.append("property_uncertainty_not_qualified")
    if cache.point_index != record.point_index:
        cache.contexts.clear()
        cache.point_index = record.point_index
    if not unsupported:
        if phase not in cache.contexts:
            unsupported_context: list[str] = []
            invalid_context: list[str] = []
            warning_context: list[str] = []
            _context(
                dataset,
                record,
                phase,
                cache.variables,
                unsupported_context,
                invalid_context,
                warning_context,
            )
            cache.contexts[phase] = (
                tuple(unsupported_context),
                tuple(invalid_context),
                tuple(warning_context),
            )
        issues = cache.contexts[phase]
        unsupported.extend(issues[0])
        invalid.extend(issues[1])
        warnings.extend(issues[2])
    # Unsupported semantics take precedence over value checks that rely on them.
    status: RecordStatus = "unsupported" if unsupported else "invalid" if invalid else "eligible"
    return Eligibility(
        status,
        quantity,
        reported,
        phase,
        tuple(dict.fromkeys(unsupported + invalid)),
        tuple(dict.fromkeys(warnings)),
    )


def _context(
    dataset: DatasetEvidence,
    record: RecordEvidence,
    phase: str | None,
    variables: dict[int, EvidenceElement],
    unsupported: list[str],
    invalid: list[str],
    warnings: list[str],
) -> None:
    values = {identifier(node, "nVarNumber"): node for node in record.variables}
    if len(values) != len(variables):
        invalid.append("missing_variable_value")
        return
    entries: list[tuple[EvidenceElement, EvidenceElement, bool]] = [
        (definition, values[number], False)
        for number, definition in variables.items()
        if number in values
    ]
    entries += [(node, node, True) for node in dataset.definition.all("Constraint")]
    states: dict[str, Fraction] = {}
    fractions: dict[tuple[str, str | None], dict[int, tuple[Decimal, int | None]]] = {}
    for definition, value, constraint in entries:
        kind = "Constraint" if constraint else "Variable"
        identity = definition.one(f"{kind}ID")
        type_node = identity.one(f"{kind}Type") if identity else None
        terms = type_node.children if type_node else ()
        if len(terms) != 1 or identity is None:
            unsupported.append("unsupported_coordinate_definition")
            continue
        allowed = (
            {
                "nConstraintNumber",
                "ConstraintID",
                "ConstraintPhaseID",
                "nConstraintValue",
                "nConstrDigits",
                "ConstrUncertainty",
                "ConstrRepeatability",
                "ConstrDeviceSpec",
            }
            if constraint
            else {
                "nVarNumber",
                "VariableID",
                "VarPhaseID",
                "VarUncertainty",
                "VarRepeatability",
                "VarDeviceSpec",
            }
        )
        reference = identity.one("RegNum")
        if (
            _unknown(definition, allowed)
            or _unknown(identity, {f"{kind}Type", "RegNum"})
            or (reference is not None and _unknown(reference, {"nOrgNum"}))
            or definition.has_attributes
            or value.has_attributes
        ):
            unsupported.append("unsupported_coordinate_qualifier")
        if not constraint and _unknown(
            value,
            {
                "nVarNumber",
                "nVarValue",
                "nVarDigits",
                "VarUncertainty",
                "VarRepeatability",
                "nVarDeviceSpecValue",
            },
        ):
            unsupported.append("unsupported_coordinate_qualifier")
        term = terms[0]
        label = term.text.strip() if term.text else ""
        number = _number(value.value("nConstraintValue" if constraint else "nVarValue"))
        digits = _precision(value, "nConstrDigits" if constraint else "nVarDigits")
        if number is None or digits == -1:
            invalid.append("invalid_coordinate_value")
            continue
        phase_group = "ConstraintPhaseID" if constraint else "VarPhaseID"
        phase_field = "eConstraintPhase" if constraint else "eVarPhase"
        coordinate_phase = _phase(definition, phase_group, phase_field)
        if len(definition.all(phase_group)) > 1 or any(
            _unknown(node, {phase_field}) or not node.value(phase_field)
            for node in definition.all(phase_group)
        ):
            unsupported.append("unsupported_coordinate_phase")
        if coordinate_phase is not None and coordinate_phase not in _PHASES:
            unsupported.append("unsupported_coordinate_phase")
        if coordinate_phase is not None and phase is not None and coordinate_phase != phase:
            invalid.append("coordinate_phase_conflict")
        if term.name == "eComponentComposition" and label in {"Mole fraction", "Mass fraction"}:
            component = component_number(identity)
            if component not in dataset.component_numbers:
                invalid.append("missing_composition_component")
                continue
            assert component is not None
            if not 0 <= number <= 1:
                invalid.append("fraction_out_of_range")
                continue
            group = fractions.setdefault((label, coordinate_phase), {})
            if component in group and group[component][0] != number:
                invalid.append("conflicting_composition")
            elif component in group:
                precisions = [item for item in (group[component][1], digits) if item is not None]
                digits = max(precisions) if precisions else None
            group[component] = (number, digits)
        elif label in _COORDINATES and term.name in {"eTemperature", "ePressure"}:
            axis, scale, offset = _COORDINATES[label]
            if term.name != ("eTemperature" if axis == "temperature" else "ePressure"):
                invalid.append("coordinate_quantity_conflict")
                continue
            if component_number(identity) is not None:
                unsupported.append("component_specific_coordinate")
            si = Fraction(number) * Fraction(scale) + Fraction(offset)
            try:
                projected = float(si)
                if not math.isfinite(projected) or (si and not projected):
                    invalid.append("nonrepresentable_normalized_coordinate")
            except OverflowError:
                invalid.append("nonrepresentable_normalized_coordinate")
            if axis in states and states[axis] != si:
                invalid.append("conflicting_state_coordinates")
            states[axis] = si
        else:
            unsupported.append("unsupported_coordinate_quantity_or_basis")
    for axis in ("temperature", "pressure"):
        if axis not in states:
            warnings.append(f"{axis}_unavailable_for_comparison")
    if len(dataset.component_numbers) == 2 and not fractions:
        invalid.append("missing_binary_composition")
    if len(fractions) > 1:
        unsupported.append("multiple_composition_bases_or_scopes")
    for (_basis, scope), group in fractions.items():
        if scope is None:
            warnings.append("composition_scope_unavailable")
        if len(group) == 1 and len(dataset.component_numbers) == 2:
            warnings.append("binary_complement_required")
            continue
        total = sum((Fraction(number) for number, _ in group.values()), Fraction(0))
        radius = Fraction(0)
        for number, digits in group.values():
            if digits is None:
                radius = Fraction(0)
                break
            radius += Fraction(10) ** (number.adjusted() - digits + 1) / 2
        if abs(total - 1) > radius:
            invalid.append("composition_sum_not_unity")
        elif total != 1:
            warnings.append("rounded_composition_retained")
