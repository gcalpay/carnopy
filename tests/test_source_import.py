from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from carnopy import ImportConfig, SourceImportError, preview_source_import
from carnopy.sources.preview import plan_source_import

FIXTURES = Path(__file__).parent / "fixtures" / "thermoml"
NS = {"t": "http://www.iupac.org/namespaces/ThermoML"}


def find(node: ET.Element, path: str) -> ET.Element:
    result = node.find(path, NS)
    assert result is not None
    return result


def config(tmp_path: Path, suffix: str = "xml", selection: str = "") -> Path:
    path = tmp_path / f"import-{suffix}.yaml"
    path.write_text(
        f"schema_version: 1\ndocument_type: source_import\nformat: thermoml_{suffix}\n{selection}",
        encoding="utf-8",
    )
    return path


def run_xml(tmp_path: Path, root: ET.Element):
    path = tmp_path / "source.xml"
    path.write_bytes(ET.tostring(root, encoding="utf-8"))
    return plan_source_import(path, config(tmp_path))


@pytest.fixture
def root() -> ET.Element:
    return ET.fromstring((FIXTURES / "density.xml").read_bytes())


def test_xml_json_preserve_equivalent_evidence_and_distinct_byte_identity(tmp_path: Path) -> None:
    plans = [
        plan_source_import(FIXTURES / f"density.{suffix}", config(tmp_path, suffix))
        for suffix in ("xml", "json")
    ]
    left, right = plans
    assert left.inventory.root == right.inventory.root
    assert left.preview.counts == right.preview.counts
    assert left.preview.counts.total == left.preview.counts.eligible == 3
    assert left.preview.source_document_id != right.preview.source_document_id
    assert left.preview.records[0].observation_id != right.preview.records[0].observation_id
    for plan in plans:
        assert plan.source.raw_bytes == plan.source.descriptor.path.read_bytes()
        assert plan.preview.source_document_id == hashlib.sha256(plan.source.raw_bytes).hexdigest()
        assert plan.preview.records[0].reported_value == "1000.00"
        assert plan.preview.records[0].reported_digits == "6"
        assert plan.inventory.publication_id == "doi:10.9999/carnopy.synthetic"
        property_node = dict(plan.inventory.datasets[0].properties)[1]
        assessment = property_node.one("CombinedUncertainty")
        assert assessment is not None
        assert assessment.value("nCombUncertLevOfConfid") == "95"
        assert assessment.value("nCombCoverageFactor") is None
        assert plan.preview.records[0].point_id != plan.preview.records[1].point_id
        assert "data_origin_unclassified" not in plan.preview.records[0].warnings


def test_preview_is_nonwriting_immutable_and_path_independent(tmp_path: Path) -> None:
    source = tmp_path / "copied.xml"
    source.write_bytes((FIXTURES / "density.xml").read_bytes())
    settings = config(tmp_path)
    before = {path: path.read_bytes() for path in tmp_path.iterdir()}
    first = preview_source_import(source, config=settings)
    second = preview_source_import(FIXTURES / "density.xml", config=settings)
    assert first.request_id == second.request_id
    assert first.context_id == second.context_id
    assert first.source.path != second.source.path
    assert {path: path.read_bytes() for path in tmp_path.iterdir()} == before
    with pytest.raises(FrozenInstanceError):
        first.status = "ready"  # type: ignore[misc]
    rendered = first.as_dict()
    rendered["records"][0]["reported_value"] = "tampered"
    assert first.records[0].reported_value == "1000.00"
    json.dumps(first.as_dict(), allow_nan=False)


def test_only_co_reported_properties_share_point_identity(tmp_path: Path, root: ET.Element) -> None:
    dataset = find(root, "t:PureOrMixtureData")
    definition = copy.deepcopy(find(dataset, "t:Property"))
    find(definition, "t:nPropNumber").text = "2"
    find(
        definition, "t:Property-MethodID/t:PropertyGroup/t:VolumetricProp/t:ePropName"
    ).text = "Amount density, mol/m3"
    dataset.append(definition)
    point = find(dataset, "t:NumValues")
    value = copy.deepcopy(find(point, "t:PropertyValue"))
    find(value, "t:nPropNumber").text = "2"
    find(value, "t:nPropValue").text = "55500"
    point.append(value)
    records = run_xml(tmp_path, root).preview.records
    assert records[0].point_id == records[1].point_id
    assert records[0].observation_id != records[1].observation_id
    assert records[1].quantity == "amount_density"
    assert records[1].point_id != records[2].point_id


@pytest.mark.parametrize(
    "path",
    [
        "t:Compound",
        "t:PureOrMixtureData",
        "t:Compound/t:Sample",
        "t:PureOrMixtureData/t:Property",
        "t:PureOrMixtureData/t:Variable",
        "t:PureOrMixtureData/t:Constraint",
        "t:PureOrMixtureData/t:NumValues/t:PropertyValue",
        "t:PureOrMixtureData/t:NumValues/t:VariableValue",
        "t:PureOrMixtureData/t:Property/t:CombinedUncertainty",
    ],
)
def test_duplicate_identifiers_reject_document(tmp_path: Path, root: ET.Element, path: str) -> None:
    parent_path, _, child_path = path.rpartition("/")
    parent = find(root, parent_path) if parent_path else root
    parent.append(copy.deepcopy(find(parent, child_path)))
    with pytest.raises(SourceImportError, match="duplicate_identifier"):
        run_xml(tmp_path, root)


@pytest.mark.parametrize(
    "path",
    [
        "t:PureOrMixtureData/t:Component/t:RegNum/t:nOrgNum",
        "t:PureOrMixtureData/t:Component/t:nSampleNm",
        "t:PureOrMixtureData/t:NumValues/t:PropertyValue/t:nPropNumber",
        "t:PureOrMixtureData/t:NumValues/t:VariableValue/t:nVarNumber",
        "t:PureOrMixtureData/t:NumValues/t:PropertyValue/t:CombinedUncertainty/t:nCombUncertAssessNum",
    ],
)
def test_broken_references_reject_document(tmp_path: Path, root: ET.Element, path: str) -> None:
    find(root, path).text = "99"
    with pytest.raises(SourceImportError, match="broken_reference"):
        run_xml(tmp_path, root)


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ("NaN", "invalid_property_value"),
        ("INF", "invalid_property_value"),
        ("1e99999", "invalid_property_value"),
        ("1e-99999", "invalid_property_value"),
        ("", "invalid_property_value"),
        ("true", "invalid_property_value"),
    ],
)
def test_invalid_numbers_do_not_become_observations(
    tmp_path: Path, root: ET.Element, value: str, reason: str
) -> None:
    find(root, "t:PureOrMixtureData/t:NumValues/t:PropertyValue/t:nPropValue").text = value
    preview = run_xml(tmp_path, root).preview
    assert preview.counts.invalid == 1
    assert preview.counts.eligible == 2
    assert reason in preview.records[0].reasons


@pytest.mark.parametrize(
    ("target", "value", "status", "reason"),
    [
        ("nConstraintValue", "1.1", "invalid", "fraction_out_of_range"),
        ("nConstraintValue", "NaN", "invalid", "invalid_coordinate_value"),
        ("nConstrDigits", "0", "invalid", "invalid_coordinate_value"),
        (
            "ConstraintID/ConstraintType/eComponentComposition",
            "Volume fraction",
            "unsupported",
            "unsupported_coordinate_quantity_or_basis",
        ),
        ("ConstraintPhaseID/eConstraintPhase", "Gas", "invalid", "coordinate_phase_conflict"),
    ],
)
def test_binary_composition_diagnostics(
    tmp_path: Path, root: ET.Element, target: str, value: str, status: str, reason: str
) -> None:
    dataset = root.findall("t:PureOrMixtureData", NS)[1]
    composition = dataset.findall("t:Constraint", NS)[1]
    find(composition, "/".join("t:" + part for part in target.split("/"))).text = value
    record = run_xml(tmp_path, root).preview.records[-1]
    assert record.status == status
    assert reason in record.reasons


@pytest.mark.parametrize("basis", ["Mole fraction", "Mass fraction"])
def test_composition_constraint_and_variable_have_same_eligibility(
    tmp_path: Path, root: ET.Element, basis: str
) -> None:
    dataset = root.findall("t:PureOrMixtureData", NS)[1]
    composition = dataset.findall("t:Constraint", NS)[1]
    find(composition, "t:ConstraintID/t:ConstraintType/t:eComponentComposition").text = basis
    original = run_xml(tmp_path, root).preview.records[-1]
    dataset.remove(composition)
    variable = ET.SubElement(dataset, "{" + NS["t"] + "}Variable")
    ET.SubElement(variable, "{" + NS["t"] + "}nVarNumber").text = "2"
    identity = find(composition, "t:ConstraintID")
    identity.tag = "{" + NS["t"] + "}VariableID"
    find(identity, "t:ConstraintType").tag = "{" + NS["t"] + "}VariableType"
    variable.append(identity)
    phase = find(composition, "t:ConstraintPhaseID")
    phase.tag = "{" + NS["t"] + "}VarPhaseID"
    find(phase, "t:eConstraintPhase").tag = "{" + NS["t"] + "}eVarPhase"
    variable.append(phase)
    point = find(dataset, "t:NumValues")
    reported = ET.SubElement(point, "{" + NS["t"] + "}VariableValue")
    for name, text in (("nVarNumber", "2"), ("nVarValue", "0.2500"), ("nVarDigits", "4")):
        ET.SubElement(reported, "{" + NS["t"] + "}" + name).text = text
    converted = run_xml(tmp_path, root).preview.records[-1]
    assert converted.status == original.status == "eligible"
    assert converted.warnings == original.warnings


@pytest.mark.parametrize(
    ("first", "second", "digits", "expected"),
    [
        ("0.2500", "0.7500", "4", "eligible"),
        ("0.333", "0.666", "3", "eligible"),
        ("0.333", "0.666", None, "invalid"),
        ("0.3", "0.5", "1", "invalid"),
    ],
)
def test_two_fractions_use_reported_precision_without_rescaling(
    tmp_path: Path, root: ET.Element, first: str, second: str, digits: str | None, expected: str
) -> None:
    dataset = root.findall("t:PureOrMixtureData", NS)[1]
    one = dataset.findall("t:Constraint", NS)[1]
    two = copy.deepcopy(one)
    find(two, "t:ConstraintID/t:RegNum/t:nOrgNum").text = "2"
    for node, value in ((one, first), (two, second)):
        find(node, "t:nConstraintValue").text = value
        precision = find(node, "t:nConstrDigits")
        if digits is None:
            node.remove(precision)
        else:
            precision.text = digits
    dataset.append(two)
    plan = run_xml(tmp_path, root)
    assert plan.preview.records[-1].status == expected
    constraints = plan.inventory.datasets[1].definition.all("Constraint")
    assert [node.value("nConstraintValue") for node in constraints[1:]] == [first, second]


def test_missing_coordinates_are_disclosed_without_invented_pressure(
    tmp_path: Path, root: ET.Element
) -> None:
    dataset = find(root, "t:PureOrMixtureData")
    dataset.remove(find(dataset, "t:Variable"))
    dataset.remove(find(dataset, "t:Constraint"))
    for point in dataset.findall("t:NumValues", NS):
        point.remove(find(point, "t:VariableValue"))
    result = run_xml(tmp_path, root).preview
    assert result.counts.eligible == 3
    assert "pressure_unavailable_for_comparison" in result.records[0].warnings
    assert "temperature_unavailable_for_comparison" in result.records[0].warnings


def test_conflicting_constraint_and_variable_are_not_resolved_by_order(
    tmp_path: Path, root: ET.Element
) -> None:
    dataset = find(root, "t:PureOrMixtureData")
    constraint = find(dataset, "t:Constraint")
    term = find(constraint, "t:ConstraintID/t:ConstraintType/t:eTemperature")
    term.tag = "{" + NS["t"] + "}ePressure"
    term.text = "Pressure, Pa"
    find(constraint, "t:nConstraintValue").text = "100000"
    assert run_xml(tmp_path, root).preview.records[0].status == "eligible"
    find(constraint, "t:nConstraintValue").text = "100001"
    assert "conflicting_state_coordinates" in run_xml(tmp_path, root).preview.records[0].reasons


@pytest.mark.parametrize(
    ("definition", "group", "field"),
    [
        ("Constraint", "ConstraintPhaseID", "eConstraintPhase"),
        ("Variable", "VarPhaseID", "eVarPhase"),
    ],
)
def test_multiple_coordinate_phases_block_eligibility(
    tmp_path: Path, root: ET.Element, definition: str, group: str, field: str
) -> None:
    node = find(root, "t:PureOrMixtureData/t:" + definition)
    for label in ("Liquid", "Gas"):
        phase = ET.SubElement(node, "{" + NS["t"] + "}" + group)
        ET.SubElement(phase, "{" + NS["t"] + "}" + field).text = label
    result = run_xml(tmp_path, root).preview
    assert result.counts.unsupported == 2
    assert "unsupported_coordinate_phase" in result.records[0].reasons


@pytest.mark.parametrize("where", ["component", "composition"])
def test_unknown_component_reference_qualifier_blocks_eligibility(
    tmp_path: Path, root: ET.Element, where: str
) -> None:
    dataset = root.findall("t:PureOrMixtureData", NS)[1]
    reference = (
        find(dataset, "t:Component/t:RegNum")
        if where == "component"
        else find(dataset.findall("t:Constraint", NS)[1], "t:ConstraintID/t:RegNum")
    )
    ET.SubElement(reference, "{" + NS["t"] + "}UnknownIdentity").text = "ambiguous"
    record = run_xml(tmp_path, root).preview.records[-1]
    assert record.status == "unsupported"
    assert (
        "unsupported_component_identity"
        if where == "component"
        else "unsupported_coordinate_qualifier"
    ) in record.reasons


@pytest.mark.parametrize("where", ["point", "property", "dataset"])
def test_unknown_scientific_qualifiers_are_retained_but_ineligible(
    tmp_path: Path, root: ET.Element, where: str
) -> None:
    dataset = find(root, "t:PureOrMixtureData")
    node = (
        find(dataset, {"point": "t:NumValues", "property": "t:Property"}[where])
        if where != "dataset"
        else dataset
    )
    ET.SubElement(node, "{" + NS["t"] + "}UnknownScientificQualifier").text = "special"
    plan = run_xml(tmp_path, root)
    assert plan.preview.records[0].status == "unsupported"
    assert plan.preview.counts.total == 3
    assert b"UnknownScientificQualifier" in plan.source.raw_bytes


def test_reaction_content_is_counted_as_unsupported(tmp_path: Path, root: ET.Element) -> None:
    dataset = find(root, "t:PureOrMixtureData")
    dataset.tag = "{" + NS["t"] + "}ReactionData"
    find(dataset, "t:Component").tag = "{" + NS["t"] + "}Participant"
    find(dataset, "t:nPureOrMixtureDataNumber").tag = "{" + NS["t"] + "}nReactionDataNumber"
    result = run_xml(tmp_path, root).preview
    assert result.counts.total == 3
    assert result.counts.unsupported == 2
    assert result.counts.eligible == 1


def test_selections_account_for_all_records_and_reject_unknown_ids(tmp_path: Path) -> None:
    path = FIXTURES / "density.xml"
    settings = config(
        tmp_path, selection="selections:\n  - dataset_index: 1\n    property_numbers: [1]\n"
    )
    result = preview_source_import(path, config=settings)
    assert result.counts.total == 3
    assert result.counts.eligible == 1
    assert result.counts.unselected == 2
    settings.write_text(settings.read_text().replace("[1]", "[99]"))
    with pytest.raises(SourceImportError, match="invalid_selection"):
        preview_source_import(path, config=settings)


def test_preview_projection_is_bounded_without_truncating_accounting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("carnopy.sources.evidence.PREVIEW_RECORD_LIMIT", 1)
    result = preview_source_import(FIXTURES / "density.json", config=config(tmp_path, "json"))
    assert result.counts.total == 3
    assert len(result.records) == len(result.datasets) == 1
    assert result.omitted_records == 2
    assert result.omitted_datasets == 1


@pytest.mark.parametrize("suffix", ["xml", "json"])
def test_public_import_preview_remains_backend_free(tmp_path: Path, suffix: str) -> None:
    source = FIXTURES / f"density.{suffix}"
    settings = config(tmp_path, suffix)
    script = """
import importlib.abc, sys
class RejectScientificImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        blocked = {'CoolProp', 'numpy', 'pandas', 'pyarrow', 'matplotlib', 'PySide6'}
        if fullname.split('.')[0] in blocked:
            raise AssertionError('unexpected heavy import: ' + fullname)
sys.meta_path.insert(0, RejectScientificImports())
from carnopy import (
    ImportConfig, ImportPreview, ImportSelection, SourceImportError, preview_source_import,
)
result = preview_source_import(sys.argv[1], config=sys.argv[2])
assert result.counts.eligible == 3
"""
    subprocess.run(
        [sys.executable, "-c", script, str(source), str(settings)],
        check=True,
        capture_output=True,
        text=True,
    )


def test_import_config_rejects_paths_and_duplicate_selections() -> None:
    from pydantic import ValidationError

    base = {"schema_version": 1, "document_type": "source_import", "format": "thermoml_xml"}
    for addition in (
        {"source": "/tmp/data.xml"},
        {"schema_version": True},
        {"selections": [{"dataset_index": 0}, {"dataset_index": 0}]},
    ):
        with pytest.raises(ValidationError):
            ImportConfig.model_validate({**base, **addition})


def test_alternate_component_identifiers_are_inventoried_as_unsupported(
    tmp_path: Path, root: ET.Element
) -> None:
    for parent in root.iter():
        for child in list(parent):
            if child.tag == "{" + NS["t"] + "}RegNum" and find(child, "t:nOrgNum").text == "1":
                parent.remove(child)
                ET.SubElement(parent, "{" + NS["t"] + "}nCompIndex").text = "100"
    result = run_xml(tmp_path, root).preview
    assert result.counts.total == result.counts.unsupported == 3
    assert result.datasets[0].component_count == 1
    find(root, "t:PureOrMixtureData/t:Component/t:nCompIndex").text = "999"
    with pytest.raises(SourceImportError, match="broken_reference"):
        run_xml(tmp_path, root)


def test_ternary_records_remain_unsupported_with_complete_accounting(
    tmp_path: Path, root: ET.Element
) -> None:
    compound = copy.deepcopy(root.findall("t:Compound", NS)[1])
    find(compound, "t:RegNum/t:nOrgNum").text = "3"
    root.append(compound)
    dataset = root.findall("t:PureOrMixtureData", NS)[1]
    component = copy.deepcopy(find(dataset, "t:Component"))
    find(component, "t:RegNum/t:nOrgNum").text = "3"
    dataset.append(component)
    result = run_xml(tmp_path, root).preview
    assert result.counts.total == 3
    assert result.counts.unsupported == 1
    assert "unsupported_component_count" in result.records[-1].reasons


def test_missing_variable_value_does_not_receive_a_default(
    tmp_path: Path, root: ET.Element
) -> None:
    point = find(root, "t:PureOrMixtureData/t:NumValues")
    point.remove(find(point, "t:VariableValue"))
    result = run_xml(tmp_path, root).preview
    assert result.counts.invalid == 1
    assert "missing_variable_value" in result.records[0].reasons


def test_state_conversion_cannot_overflow_silently(tmp_path: Path, root: ET.Element) -> None:
    find(root, "t:PureOrMixtureData/t:NumValues/t:VariableValue/t:nVarValue").text = "1e308"
    result = run_xml(tmp_path, root).preview
    assert result.counts.invalid == 1
    assert "nonrepresentable_normalized_coordinate" in result.records[0].reasons


def test_no_eligible_observations_is_an_explicit_preview_outcome(
    tmp_path: Path, root: ET.Element
) -> None:
    for dataset in root.findall("t:PureOrMixtureData", NS):
        find(
            dataset, "t:Property/t:Property-MethodID/t:PropertyGroup/t:VolumetricProp/t:ePropName"
        ).text = "Excess molar volume, m3/mol"
    result = run_xml(tmp_path, root).preview
    assert result.status == "no_eligible_observations"
    assert result.counts.total == result.counts.unsupported == 3
    assert result.counts.eligible == 0


def test_asymmetric_uncertainty_remains_reported_evidence(tmp_path: Path, root: ET.Element) -> None:
    value = find(root, "t:PureOrMixtureData/t:NumValues/t:PropertyValue/t:CombinedUncertainty")
    value.remove(find(value, "t:nCombExpandUncertValue"))
    asym = ET.SubElement(value, "{" + NS["t"] + "}AsymCombExpandUncert")
    ET.SubElement(asym, "{" + NS["t"] + "}nPositiveValue").text = "0.7"
    ET.SubElement(asym, "{" + NS["t"] + "}nNegativeValue").text = "0.5"
    plan = run_xml(tmp_path, root)
    reported = plan.inventory.datasets[0].records[0].value.one("CombinedUncertainty")
    assert reported is not None
    asymmetry = reported.one("AsymCombExpandUncert")
    assert asymmetry is not None
    assert asymmetry.value("nPositiveValue") == "0.7"
    assert asymmetry.value("nNegativeValue") == "0.5"
    assert reported.value("nCombStdUncertValue") is None
    assert "property_uncertainty_not_qualified" in plan.preview.records[0].warnings


@pytest.mark.parametrize(
    ("replacement", "expected"), [("null", "invalid"), ("0", "invalid"), ("6", "eligible")]
)
def test_json_reported_precision_is_validated(
    tmp_path: Path, replacement: str, expected: str
) -> None:
    source = tmp_path / "source.json"
    data = (
        (FIXTURES / "density.json")
        .read_bytes()
        .replace(b'"nPropDigits": 6', b'"nPropDigits": ' + replacement.encode(), 1)
    )
    source.write_bytes(data)
    result = preview_source_import(source, config=config(tmp_path, "json"))
    assert result.records[0].status == expected


def test_explicit_selection_remains_visible_in_a_bounded_preview(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("carnopy.sources.evidence.PREVIEW_RECORD_LIMIT", 1)
    settings = config(tmp_path, selection="selections:\n  - dataset_index: 1\n")
    result = preview_source_import(FIXTURES / "density.xml", config=settings)
    assert result.records[0].dataset_index == result.datasets[0].dataset_index == 1
    assert result.counts.eligible == 1
    assert result.counts.unselected == 2
    assert result.omitted_records == 2


@pytest.mark.parametrize(
    ("doi", "expected"),
    [("https://doi.org/10.9999/TEST", "doi:10.9999/test"), ("unregistered-looking citation", None)],
)
def test_publication_identity_does_not_invent_a_doi(
    tmp_path: Path, root: ET.Element, doi: str, expected: str | None
) -> None:
    find(root, "t:Citation/t:sDOI").text = doi
    result = run_xml(tmp_path, root).preview
    assert result.publication_id == (expected or f"document:{result.source_document_id}")
    if expected is None:
        assert "publication_grouping_unavailable" in {item.code for item in result.diagnostics}
