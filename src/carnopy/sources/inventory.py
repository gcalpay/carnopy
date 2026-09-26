from __future__ import annotations

import re

from carnopy.config.normalize import canonical_json_bytes
from carnopy.provenance import sha256_bytes
from carnopy.sources.errors import SourceImportError
from carnopy.sources.evidence import (
    DatasetEvidence,
    EvidenceElement,
    EvidenceInventory,
    ImportDiagnostic,
    RecordEvidence,
)
from carnopy.sources.files import Checkpoint, checkpoint


def source_identity(domain: str, payload: dict[str, object]) -> str:
    return sha256_bytes(canonical_json_bytes({"domain": f"source-1/{domain}/v1", **payload}))


def identifier(node: EvidenceElement, name: str, *, required: bool = True) -> int | None:
    value = node.value(name)
    if value is None and not required:
        return None
    if value is None or not re.fullmatch(r"[+-]?[0-9]+", value) or len(value) > 20:
        raise SourceImportError("invalid_identifier", f"missing/invalid {name}")
    return int(value)


def indexed(nodes: tuple[EvidenceElement, ...], field: str) -> dict[int, EvidenceElement]:
    result: dict[int, EvidenceElement] = {}
    for node in nodes:
        key = identifier(node, field)
        assert key is not None
        if key in result:
            raise SourceImportError("duplicate_identifier", f"duplicate {field}={key}")
        result[key] = node
    return result


def component_number(node: EvidenceElement) -> int | None:
    reference = node.one("RegNum")
    return identifier(reference, "nOrgNum", required=False) if reference else None


_ASSESSMENTS = (
    ("CombinedUncertainty", "nCombUncertAssessNum"),
    ("PropUncertainty", "nUncertAssessNum"),
    ("VarUncertainty", "nUncertAssessNum"),
    ("CurveDev", "nCurveDevAssessNum"),
)


def _assessment_ids(definition: EvidenceElement) -> dict[str, frozenset[int]]:
    return {
        family: frozenset(indexed(definition.all(family), field)) for family, field in _ASSESSMENTS
    }


def _assessments(declared: dict[str, frozenset[int]], value: EvidenceElement) -> None:
    for family, field in _ASSESSMENTS:
        reported = indexed(value.all(family), field)
        if any(key not in declared[family] for key in reported):
            raise SourceImportError("broken_reference", f"undeclared {family} assessment")


def _validate_references(
    dataset: EvidenceElement,
    compounds: dict[int, EvidenceElement],
    samples: dict[int, dict[int, EvidenceElement]],
    alternate_references: dict[tuple[str, int], EvidenceElement],
    cancel: Checkpoint | None,
) -> tuple[int, ...]:
    numbers: list[int] = []
    components = dataset.all("Participant" if dataset.name == "ReactionData" else "Component")
    for node in components:
        number = component_number(node)
        if number is not None:
            if number not in compounds:
                raise SourceImportError("broken_reference", f"unknown component {number}")
            if number in numbers:
                raise SourceImportError("duplicate_identifier", f"repeated component {number}")
            numbers.append(number)
            sample = identifier(node, "nSampleNm", required=False)
            if sample is not None and sample not in samples[number]:
                raise SourceImportError("broken_reference", f"unknown sample {sample} for {number}")
    for node in dataset.walk():
        checkpoint(cancel)
        for key in ("nCompIndex", "nCASRNum"):
            if node.name == key:
                owner = EvidenceElement("reference", children=(node,))
                reference = identifier(owner, key)
                assert reference is not None
                if (key, reference) not in alternate_references:
                    raise SourceImportError("broken_reference", f"unknown {key}={reference}")
        if node.name == "RegNum":
            number = identifier(node, "nOrgNum", required=False)
            if number is not None and number not in compounds:
                raise SourceImportError("broken_reference", f"unknown dataset component {number}")
        if node.name in {
            "VariableID",
            "ConstraintID",
            "Property-MethodID",
            "PropPhaseID",
            "VarPhaseID",
            "ConstraintPhaseID",
        }:
            number = component_number(node)
            if number is not None and number not in numbers:
                raise SourceImportError(
                    "broken_reference", "reference is outside dataset components"
                )
    # Optional constraint numbers still have to be unique if supplied.
    declared_constraints = tuple(
        node for node in dataset.all("Constraint") if node.one("nConstraintNumber") is not None
    )
    indexed(declared_constraints, "nConstraintNumber")
    return tuple(numbers)


def build_inventory(
    root: EvidenceElement,
    source_hash: str,
    *,
    cancel: Checkpoint | None = None,
) -> EvidenceInventory:
    compounds: dict[int, EvidenceElement] = {}
    samples: dict[int, dict[int, EvidenceElement]] = {}
    alternate_references: dict[tuple[str, int], EvidenceElement] = {}
    for compound in root.all("Compound"):
        checkpoint(cancel)
        has_alternative = False
        regnum = compound.one("RegNum")
        for field, owner in (("nCompIndex", compound), ("nCASRNum", regnum)):
            key = identifier(owner, field, required=False) if owner else None
            if key is not None:
                has_alternative = True
                if (field, key) in alternate_references:
                    raise SourceImportError("duplicate_identifier", f"ambiguous {field}={key}")
                alternate_references[(field, key)] = compound
        number = component_number(compound)
        if number is None:
            if not has_alternative:
                raise SourceImportError(
                    "invalid_identifier", "Compound has no supported identity locator"
                )
            indexed(compound.all("Sample"), "nSampleNm")
            continue
        if number in compounds:
            raise SourceImportError("duplicate_identifier", f"duplicate Compound {number}")
        compounds[number] = compound
        samples[number] = indexed(compound.all("Sample"), "nSampleNm")
    root.one("Version")
    citation = root.one("Citation")
    doi = citation.value("sDOI") if citation else None
    if doi:
        doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi, flags=re.I).lower()
        if not re.fullmatch(r"10\.[0-9]{4,9}/[^\s]+", doi):
            doi = None
    publication = f"doi:{doi}" if doi else f"document:{source_hash}"
    diagnostics = [
        ImportDiagnostic(
            "not_independently_validated",
            "DataReport",
            "Parsing and preview eligibility are not independent scientific validation.",
        )
    ]
    if not doi:
        diagnostics.append(
            ImportDiagnostic(
                "publication_grouping_unavailable",
                "Citation",
                "No recognized DOI; document grouping does not prove publication independence.",
            )
        )
    known_root = {
        "Version",
        "Citation",
        "Compound",
        "PureOrMixtureData",
        "ReactionData",
        "THERMOML_MD5_CHECKSUM",
    }
    for child in root.children:
        if child.name not in known_root:
            if any(node.name == "PropertyValue" for node in child.walk()):
                raise SourceImportError(
                    "unsupported_structure", "property values outside a known dataset"
                )
            diagnostics.append(
                ImportDiagnostic(
                    "unsupported_metadata",
                    child.name,
                    "Content retained in original evidence only.",
                )
            )
    datasets: list[DatasetEvidence] = []
    declared: set[tuple[str, int]] = set()
    for node in root.children:
        if node.name not in {"PureOrMixtureData", "ReactionData"}:
            continue
        checkpoint(cancel)
        index = len(datasets)
        field = (
            "nPureOrMixtureDataNumber"
            if node.name == "PureOrMixtureData"
            else "nReactionDataNumber"
        )
        number = identifier(node, field, required=False)
        if number is not None:
            if (node.name, number) in declared:
                raise SourceImportError(
                    "duplicate_identifier", f"duplicate dataset number {number}"
                )
            declared.add((node.name, number))
        components = _validate_references(node, compounds, samples, alternate_references, cancel)
        properties = indexed(node.all("Property"), "nPropNumber")
        variables = indexed(node.all("Variable"), "nVarNumber")
        property_assessments = {key: _assessment_ids(value) for key, value in properties.items()}
        variable_assessments = {key: _assessment_ids(value) for key, value in variables.items()}
        dataset_id = source_identity(
            "dataset",
            {
                "source_document_id": source_hash,
                "kind": node.name,
                "dataset_index": index,
            },
        )
        records: list[RecordEvidence] = []
        for point_index, point in enumerate(node.all("NumValues")):
            checkpoint(cancel)
            point_variables = indexed(point.all("VariableValue"), "nVarNumber")
            point_properties = indexed(point.all("PropertyValue"), "nPropNumber")
            if any(key not in variables for key in point_variables) or any(
                key not in properties for key in point_properties
            ):
                raise SourceImportError(
                    "broken_reference", "point uses undeclared property/variable"
                )
            point_id = source_identity(
                "point", {"dataset_id": dataset_id, "point_index": point_index}
            )
            for key, value in point_variables.items():
                _assessments(variable_assessments[key], value)
            point_values = tuple(point_variables.values())
            qualifiers = tuple(
                child
                for child in point.children
                if child.name not in {"VariableValue", "PropertyValue"}
            )
            for key, value in point_properties.items():
                checkpoint(cancel)
                _assessments(property_assessments[key], value)
                records.append(
                    RecordEvidence(
                        index,
                        point_index,
                        key,
                        dataset_id,
                        point_id,
                        source_identity(
                            "observation", {"point_id": point_id, "property_number": key}
                        ),
                        value,
                        point_values,
                        qualifiers,
                    )
                )
        nested_count = sum(child.name == "PropertyValue" for child in node.walk())
        if nested_count != len(records):
            raise SourceImportError("unsupported_structure", "unaccounted nested property values")
        definition = EvidenceElement(
            node.name,
            node.text,
            tuple(child for child in node.children if child.name != "NumValues"),
            node.attributes,
        )
        datasets.append(
            DatasetEvidence(
                index,
                number,
                dataset_id,
                node.name,
                definition,
                components,
                tuple(properties.items()),
                tuple(variables.items()),
                tuple(records),
            )
        )
    return EvidenceInventory(
        source_hash,
        publication,
        root,
        tuple(compounds.items()),
        tuple(datasets),
        tuple(diagnostics),
    )
