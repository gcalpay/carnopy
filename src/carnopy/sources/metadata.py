from __future__ import annotations

from typing import Any

from carnopy.sources.evidence import DatasetEvidence, EvidenceElement
from carnopy.sources.inventory import component_number, identifier, source_identity

# Explicit measurement-method terms in the official ThermoML VolumetricProp
# enumeration. Free text and derived/calculated methods are not classified by
# guessing from their wording. Classification does not independently validate data.
MEASUREMENT_METHODS = frozenset(
    {
        "Pycnometric method",
        "X-ray diffraction",
        "Buoyancy - hydrostatic balance",
        "Buoyancy - magnetic float or magnetic suspension",
        "Buoyancy - hydrostatic balance with magnetic float",
        "Buoyancy - hydrostatic balance with magnetic suspension - one sinker",
        "Buoyancy - hydrostatic balance with magnetic suspension - two sinkers",
        "Vibrating tube method",
        "Isochoric PVT measurement",
        "Other PVT measurement",
        "Burnett expansion method",
        "Constant-volume piezometry",
        "Hydrostatic balance",
        "Bellows volumetry",
        "Resistive pulse heating",
        "Laser pulse heating",
        "Levitation methods",
        "Direct dilatometry",
    }
)


def element_payload(node: EvidenceElement) -> dict[str, Any]:
    return {
        "name": node.name,
        "text": node.text,
        "attributes": [list(item) for item in node.attributes],
        "children": [element_payload(child) for child in node.children],
    }


def property_family(definition: EvidenceElement) -> EvidenceElement | None:
    method = definition.one("Property-MethodID")
    group = method.one("PropertyGroup") if method else None
    return group.children[0] if group and len(group.children) == 1 else None


def data_origin(definition: EvidenceElement) -> tuple[str, str]:
    family = property_family(definition)
    if family is None:
        return "unknown", "method unavailable"
    choices = [
        child
        for child in family.children
        if child.name in {"eMethodName", "sMethodName", "Prediction", "CriticalEvaluation"}
    ]
    if len(choices) != 1:
        return "unknown", "method unavailable or ambiguous"
    method = choices[0]
    if method.name == "Prediction":
        return "predicted", "ThermoML Prediction"
    if method.name == "CriticalEvaluation":
        return "critically_evaluated", "ThermoML CriticalEvaluation"
    if method.name == "eMethodName" and method.text and method.text.strip() in MEASUREMENT_METHODS:
        return "experimental", "explicit ThermoML measurement-method term"
    return "unknown", "unqualified method; no origin inferred from free text"


def component_id(source_document_id: str, number: int) -> str:
    return source_identity(
        "component", {"source_document_id": source_document_id, "reported_number": number}
    )


def component_references(dataset: DatasetEvidence, source_document_id: str) -> list[dict[str, Any]]:
    result = []
    for node in dataset.definition.all("Component"):
        number = component_number(node)
        assert number is not None
        sample = identifier(node, "nSampleNm", required=False)
        result.append(
            {
                "component_id": component_id(source_document_id, number),
                "reported_number": str(number),
                "sample_number": None if sample is None else str(sample),
            }
        )
    return result
