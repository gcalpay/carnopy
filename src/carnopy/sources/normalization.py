from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from carnopy._execution import ExecutionControl
from carnopy.config.normalize import canonical_json_bytes
from carnopy.sources.eligibility import _COORDINATES, EligibilityCache, assess_record
from carnopy.sources.errors import SourceImportError
from carnopy.sources.evidence import DatasetEvidence, EvidenceElement, RecordEvidence
from carnopy.sources.inventory import component_number, identifier, source_identity
from carnopy.sources.metadata import (
    component_id,
    component_references,
    data_origin,
    element_payload,
)
from carnopy.sources.numbers import affine_decimal, conversion, decimal_text, project
from carnopy.sources.preview import SourceImportPlan, _selection
from carnopy.sources.uncertainty import uncertainty_rows

PHASES = {
    "Liquid": "liquid",
    "Gas": "vapour",
    "Fluid (supercritical or subcritical phases)": "fluid",
}
UNITS = {"mass_density": "kg/m^3", "amount_density": "mol/m^3"}


def json_text(value: Any) -> str:
    return canonical_json_bytes(value).decode("utf-8")


@dataclass
class NormalizedRecord:
    inventory: dict[str, Any]
    observation: dict[str, Any] | None
    provenance: dict[str, Any] | None
    uncertainties: list[dict[str, Any]]
    diagnostics: list[dict[str, Any]]


def diagnostic(
    record: RecordEvidence,
    code: str,
    *,
    normalized: bool,
    severity: str = "warning",
    locator: str | None = None,
    target_id: str | None = None,
) -> dict[str, Any]:
    location = locator or record.locator
    target = target_id or record.observation_id
    return {
        "diagnostic_id": source_identity(
            "diagnostic", {"target_id": target, "code": code, "locator": location}
        ),
        "dataset_id": record.dataset_id,
        "point_id": record.point_id,
        "source_record_id": record.observation_id,
        "observation_id": record.observation_id if normalized else None,
        "target_id": target,
        "locator": location,
        "severity": severity,
        "code": code,
        "message": code.replace("_", " "),
    }


def _target(
    record: RecordEvidence,
    target_id: str,
    kind: str,
    quantity: str,
    locator: str,
) -> dict[str, Any]:
    return {
        "dataset_id": record.dataset_id,
        "point_id": None if kind == "constraint" else record.point_id,
        "observation_id": record.observation_id if kind == "property" else None,
        "target_id": target_id,
        "target_kind": kind,
        "quantity": quantity,
        "locator": locator,
    }


def _coordinates(
    dataset: DatasetEvidence,
    record: RecordEvidence,
    source_document_id: str,
) -> tuple[dict[str, float], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    variables = dict(dataset.variables)
    entries: list[tuple[EvidenceElement, EvidenceElement, bool, int]] = []
    for node in record.variables:
        number = identifier(node, "nVarNumber")
        assert number is not None
        entries.append((variables[number], node, False, number))
    entries.extend(
        (node, node, True, index) for index, node in enumerate(dataset.definition.all("Constraint"))
    )
    states: dict[str, float] = {}
    lineage: list[dict[str, Any]] = []
    uncertainties: list[dict[str, Any]] = []
    fractions: dict[int, tuple[str, float]] = {}
    composition_basis = None
    composition_scope = None
    for definition, value, constraint, number in entries:
        kind = "Constraint" if constraint else "Variable"
        identity = definition.one(f"{kind}ID")
        assert identity is not None
        type_node = identity.one(f"{kind}Type")
        assert type_node is not None
        term = type_node.children[0]
        label = (term.text or "").strip()
        text = value.value("nConstraintValue" if constraint else "nVarValue")
        assert text is not None
        digits = value.value("nConstrDigits" if constraint else "nVarDigits")
        location = (
            f"dataset[{dataset.index}]/Constraint[{number}]"
            if constraint
            else f"dataset[{dataset.index}]/NumValues[{record.point_index}]/VariableValue[{number}]"
        )
        target_id = source_identity(
            "constraint" if constraint else "variable-value",
            {
                "owner_id": dataset.dataset_id if constraint else record.point_id,
                "number": number,
            },
        )
        phase_group, phase_field = (
            ("ConstraintPhaseID", "eConstraintPhase") if constraint else ("VarPhaseID", "eVarPhase")
        )
        phase_node = definition.one(phase_group)
        phase = phase_node.value(phase_field) if phase_node else None
        if label in _COORDINATES:
            quantity, scale, offset = _COORDINATES[label]
            unit = "K" if quantity == "temperature" else "Pa"
            reported_unit = label.split(", ", 1)[1]
        else:
            quantity = "mole_fraction" if label == "Mole fraction" else "mass_fraction"
            scale, offset, unit, reported_unit = "1", "0", "1", "1"
            composition_basis = "mole" if label == "Mole fraction" else "mass"
            composition_scope = PHASES.get(phase or "", "unknown")
        converted = conversion(
            locator=location,
            quantity=quantity,
            reported_value=text,
            reported_digits=digits,
            reported_unit=reported_unit,
            canonical_unit=unit,
            scale=scale,
            offset=offset,
        )
        converted.update(
            target_id=target_id,
            reported_quantity=label,
            reported_phase=phase,
            scope="constraint" if constraint else "variable",
            definition_json=json_text(element_payload(definition)),
            reported_json=json_text(element_payload(value)),
        )
        lineage.append(converted)
        if quantity in {"temperature", "pressure"}:
            states[quantity] = converted["binary64"]
        else:
            component = component_number(identity)
            assert component is not None
            converted["component_id"] = component_id(source_document_id, component)
            fractions[component] = (converted["canonical_decimal"], converted["binary64"])
        uncertainties.extend(
            uncertainty_rows(
                definition,
                value,
                target=_target(
                    record,
                    target_id,
                    "constraint" if constraint else "variable",
                    quantity,
                    location,
                ),
                families=("ConstrUncertainty",) if constraint else ("VarUncertainty",),
                unit=unit,
                reported_unit=reported_unit,
                scale=scale,
            )
        )
    derived_component = None
    if len(dataset.component_numbers) == 2 and len(fractions) == 1:
        supplied = next(iter(fractions))
        derived_component = next(
            number for number in dataset.component_numbers if number != supplied
        )
        original = fractions[supplied][0]
        complement = affine_decimal(original, "-1", "1")
        fractions[derived_component] = (decimal_text(complement), project(complement))
        lineage.append(
            {
                "quantity": "composition",
                "rule": "binary complement: 1 - supplied_fraction",
                "component_id": component_id(source_document_id, derived_component),
                "input_component_id": component_id(source_document_id, supplied),
                "input_fraction_decimal": original,
                "basis": composition_basis,
                "scope": composition_scope,
                "canonical_decimal": decimal_text(complement),
                "binary64": project(complement),
                "binary64_hex": project(complement).hex(),
            }
        )
    composition = {
        "composition_basis": composition_basis,
        "composition_scope": composition_scope,
        "composition": [
            {
                "component_id": component_id(source_document_id, number),
                "fraction": fractions[number][1],
                "fraction_decimal": fractions[number][0],
                "derived": number == derived_component,
            }
            for number in dataset.component_numbers
            if number in fractions
        ],
    }
    return states, lineage, uncertainties, composition


def normalize_records(
    plan: SourceImportPlan,
    *,
    control: ExecutionControl | None = None,
) -> Iterator[NormalizedRecord]:
    selected = _selection(plan.config.model, plan.inventory)
    ordinal = 0
    for dataset in plan.inventory.datasets:
        properties = dict(dataset.properties)
        cache = EligibilityCache(properties, dict(dataset.variables))
        constraint_uncertainties: set[str] = set()
        point_uncertainties: set[str] = set()
        point_index = -1
        for record in dataset.records:
            if control:
                control.checkpoint(ordinal, plan.preview.counts.total)
            if point_index != record.point_index:
                point_uncertainties.clear()
                point_index = record.point_index
            assessed = assess_record(dataset, record, cache=cache)
            is_selected = record.property_number in selected.get(dataset.index, set())
            status: str = assessed.status if is_selected else "unselected"
            reasons, warnings = list(assessed.reasons), list(assessed.warnings)
            origin, origin_rule = data_origin(properties[record.property_number])
            observation = provenance = None
            uncertainties: list[dict[str, Any]] = []
            if status == "eligible":
                try:
                    quantity = assessed.quantity
                    assert quantity is not None
                    unit = UNITS[quantity]
                    text = record.value.value("nPropValue")
                    assert text is not None
                    property_conversion = conversion(
                        locator=record.locator,
                        quantity=quantity,
                        reported_value=text,
                        reported_digits=record.value.value("nPropDigits"),
                        reported_unit=(assessed.reported_quantity or "").split(", ", 1)[1],
                        canonical_unit=unit,
                    )
                    states, lineage, coordinates_uncertainty, composition = _coordinates(
                        dataset, record, plan.inventory.source_document_id
                    )
                    observation = {
                        "source_document_id": plan.inventory.source_document_id,
                        "publication_id": plan.inventory.publication_id,
                        "dataset_id": dataset.dataset_id,
                        "point_id": record.point_id,
                        "observation_id": record.observation_id,
                        "property_id": source_identity(
                            "property",
                            {
                                "dataset_id": dataset.dataset_id,
                                "property_number": record.property_number,
                            },
                        ),
                        "source_order": ordinal,
                        "dataset_index": dataset.index,
                        "point_index": record.point_index,
                        "property_number": str(record.property_number),
                        "quantity": quantity,
                        "unit": unit,
                        "basis": "mass" if quantity == "mass_density" else "molar",
                        "value": property_conversion["binary64"],
                        "value_decimal": property_conversion["canonical_decimal"],
                        "temperature_K": states.get("temperature"),
                        "pressure_Pa": states.get("pressure"),
                        "phase": PHASES.get(assessed.phase or "", "unknown"),
                        "reported_phase": assessed.phase,
                        "data_origin": origin,
                        "components": component_references(
                            dataset, plan.inventory.source_document_id
                        ),
                        **composition,
                    }
                    provenance = {
                        "observation_id": record.observation_id,
                        "source_document_id": plan.inventory.source_document_id,
                        "locator": record.locator,
                        "reported_dataset_number": None
                        if dataset.reported_number is None
                        else str(dataset.reported_number),
                        "reported_property_number": str(record.property_number),
                        "reported_quantity": assessed.reported_quantity,
                        "reported_value": text,
                        "reported_digits": record.value.value("nPropDigits"),
                        "reported_unit": property_conversion["reported_unit"],
                        "reported_basis": observation["basis"],
                        "origin_rule": origin_rule,
                        "conversions_json": json_text([property_conversion, *lineage]),
                        "reported_property_json": json_text(element_payload(record.value)),
                    }
                    uncertainties = uncertainty_rows(
                        properties[record.property_number],
                        record.value,
                        target=_target(
                            record, record.observation_id, "property", quantity, record.locator
                        ),
                        families=("CombinedUncertainty", "PropUncertainty"),
                        unit=unit,
                        reported_unit=property_conversion["reported_unit"],
                    )
                    # Variable evidence is attached once to its original point;
                    # constraint evidence once to its dataset, not to every property.
                    for row in coordinates_uncertainty:
                        seen = (
                            constraint_uncertainties
                            if row["target_kind"] == "constraint"
                            else point_uncertainties
                        )
                        if row["uncertainty_id"] not in seen:
                            uncertainties.append(row)
                            seen.add(row["uncertainty_id"])
                    warnings = [
                        item
                        for item in warnings
                        if item
                        not in {"property_uncertainty_not_qualified", "binary_complement_required"}
                    ]
                    status = "normalized"
                except SourceImportError as exc:
                    status, observation, provenance, uncertainties = "invalid", None, None, []
                    reasons.append(exc.code)
            diagnostics = [
                diagnostic(record, code, normalized=observation is not None, severity="error")
                for code in reasons
            ]
            diagnostics.extend(
                diagnostic(record, code, normalized=observation is not None) for code in warnings
            )
            for row in uncertainties:
                issue = row["issue"]
                if (
                    issue is None
                    and row["classification"] == "expanded"
                    and row["coverage_factor"] is None
                ):
                    issue = "coverage_factor_unavailable"
                if issue:
                    warnings.append(issue)
                    diagnostics.append(
                        diagnostic(
                            record,
                            issue,
                            normalized=True,
                            locator=row["locator"],
                            target_id=row["target_id"],
                        )
                    )
            yield NormalizedRecord(
                {
                    "source_record_id": record.observation_id,
                    "observation_id": record.observation_id if observation is not None else None,
                    "dataset_id": dataset.dataset_id,
                    "point_id": record.point_id,
                    "dataset_index": dataset.index,
                    "point_index": record.point_index,
                    "property_number": str(record.property_number),
                    "source_order": ordinal,
                    "locator": record.locator,
                    "status": status,
                    "quantity": assessed.quantity,
                    "data_origin": origin,
                    "reasons": list(dict.fromkeys(reasons)),
                    "warnings": list(dict.fromkeys(warnings)),
                },
                observation,
                provenance,
                uncertainties,
                diagnostics,
            )
            ordinal += 1
    if control:
        control.checkpoint(ordinal, ordinal)
