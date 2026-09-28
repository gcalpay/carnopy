from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from dataclasses import FrozenInstanceError
from decimal import localcontext
from pathlib import Path
from xml.etree import ElementTree as ET

import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner

from carnopy import import_source, preview_source_import
from carnopy._execution import ExecutionCancelled, ExecutionControl
from carnopy.cli import app
from carnopy.inspection import inspect_source
from carnopy.sources.bundle import read_source_bundle
from carnopy.sources.errors import SourceImportError
from carnopy.sources.pipeline import run_source_import
from carnopy.sources.tables import table_schemas

FIXTURES = Path(__file__).parent / "fixtures" / "thermoml"
NS = {"t": "http://www.iupac.org/namespaces/ThermoML"}


def node(root, path):
    found = root.find(path, NS)
    assert found is not None
    return found


def add(parent, name, text=None):
    child = ET.SubElement(parent, "{" + NS["t"] + "}" + name)
    child.text = text
    return child


def settings(tmp_path, suffix="xml", selection=""):
    path = tmp_path / f"import-{suffix}.yaml"
    path.write_text(
        f"schema_version: 1\ndocument_type: source_import\nformat: thermoml_{suffix}\n{selection}"
    )
    return path


def xml_import(tmp_path, root, **kwargs):
    path = tmp_path / "source.xml"
    path.write_bytes(ET.tostring(root, encoding="utf-8"))
    return run_source_import(path, settings(tmp_path), output_root=tmp_path / "out", **kwargs)


def rows(result, name):
    return pq.read_table(result.output_directory / "data" / f"{name}.parquet").to_pylist()


@pytest.fixture
def root():
    return ET.fromstring((FIXTURES / "density.xml").read_bytes())


def test_xml_json_roundtrip_preserves_evidence_repetitions_and_science(tmp_path):
    results = [
        import_source(
            FIXTURES / f"density.{suffix}",
            config=settings(tmp_path, suffix),
            output_root=tmp_path / "out",
        )
        for suffix in ("xml", "json")
    ]
    projections = []
    for suffix, result in zip(("xml", "json"), results, strict=True):
        assert result.counts.total == result.counts.normalized == 3
        assert result.status == "completed_with_limitations"
        assert (result.output_directory / "source" / f"original.{suffix}").read_bytes() == (
            FIXTURES / f"density.{suffix}"
        ).read_bytes()
        assert (
            result.manifest_sha256 == hashlib.sha256(result.manifest_path.read_bytes()).hexdigest()
        )
        bundle = read_source_bundle(result.output_directory)
        assert bundle.manifest["runtime_versions"]["python"]
        assert bundle.manifest["runtime_versions"]["pyarrow"]
        assert (bundle.manifest["runtime_versions"]["defusedxml"] is None) == (suffix == "json")
        assert bundle.catalog["datasets"][0]["reported_number"] == "17"
        for artifact in result.artifacts:
            assert (
                hashlib.sha256((result.output_directory / artifact.path).read_bytes()).hexdigest()
                == artifact.sha256
            )
        observations, provenance = rows(result, "observations"), rows(result, "provenance")
        assert len({row["observation_id"] for row in observations}) == 3
        assert observations[0]["point_id"] != observations[1]["point_id"]
        assert observations[0]["value"] == observations[1]["value"] == 1000
        assert observations[0]["temperature_K"] == 298.15
        assert observations[0]["pressure_Pa"] == 100000
        assert observations[0]["data_origin"] == "experimental"
        assert observations[2]["data_origin"] == "unknown"
        assert observations[2]["composition_basis"] == "mole"
        assert observations[2]["composition_scope"] == "liquid"
        assert [x["fraction"] for x in observations[2]["composition"]] == [0.25, 0.75]
        assert [x["derived"] for x in observations[2]["composition"]] == [False, True]
        assert provenance[0]["reported_value"] == "1000.00"
        assert provenance[0]["reported_digits"] == "6"
        assert provenance[0]["observation_id"] == observations[0]["observation_id"]
        conversions = json.loads(provenance[2]["conversions_json"])
        assert conversions[-1]["input_fraction_decimal"] == "0.25"
        assert conversions[-1]["canonical_decimal"] == "0.75"
        uncertainty = rows(result, "uncertainties")[0]
        assert uncertainty["classification"] == "expanded"
        assert uncertainty["value"] == 0.5
        assert uncertainty["confidence_level"] == "95"
        assert uncertainty["coverage_factor"] is None
        assert uncertainty["standard_uncertainty"] is None
        projections.append(
            [
                (
                    r["value"],
                    r["temperature_K"],
                    r["pressure_Pa"],
                    r["phase"],
                    r["composition_basis"],
                )
                for r in observations
            ]
        )
        with pytest.raises(FrozenInstanceError):
            result.status = "completed"
        payload = result.as_dict()
        payload["counts"]["normalized"] = -1
        assert result.counts.normalized == 3
    assert projections[0] == projections[1]
    assert results[0].source_document_id != results[1].source_document_id
    duplicate = import_source(
        FIXTURES / "density.xml", config=settings(tmp_path), output_root=tmp_path / "out"
    )
    assert duplicate.output_directory != results[0].output_directory
    assert rows(duplicate, "observations") == rows(results[0], "observations")


def test_basis_and_exact_conversion_are_independent_of_decimal_context(tmp_path, root):
    dataset = node(root, "t:PureOrMixtureData")
    node(
        dataset, "t:Property/t:Property-MethodID/t:PropertyGroup/t:VolumetricProp/t:ePropName"
    ).text = "Amount density, mol/m3"
    node(
        dataset, "t:Constraint/t:ConstraintID/t:ConstraintType/t:eTemperature"
    ).text = "Temperature, degC"
    node(
        dataset, "t:Constraint/t:nConstraintValue"
    ).text = "25.000000000000000000000000000000000000000000000000000000000123"
    with localcontext() as context:
        context.prec = 6
        result = xml_import(tmp_path, root)
    first = rows(result, "observations")[0]
    assert (first["quantity"], first["basis"], first["unit"]) == (
        "amount_density",
        "molar",
        "mol/m^3",
    )
    assert first["temperature_K"] == 298.15
    conversions = json.loads(rows(result, "provenance")[0]["conversions_json"])
    temperature = next(item for item in conversions if item["quantity"] == "temperature")
    assert (
        temperature["canonical_decimal"]
        == "298.150000000000000000000000000000000000000000000000000000000123"
    )
    assert temperature["offset"] == "273.15"


@pytest.mark.parametrize("basis", ["Mole fraction", "Mass fraction"])
def test_reported_binary_pair_is_not_rescaled(tmp_path, root, basis):
    dataset = root.findall("t:PureOrMixtureData", NS)[1]
    fraction = dataset.findall("t:Constraint", NS)[1]
    node(fraction, "t:ConstraintID/t:ConstraintType/t:eComponentComposition").text = basis
    node(fraction, "t:nConstraintValue").text = "0.333"
    node(fraction, "t:nConstrDigits").text = "3"
    other = copy.deepcopy(fraction)
    node(other, "t:ConstraintID/t:RegNum/t:nOrgNum").text = "2"
    node(other, "t:nConstraintValue").text = "0.666"
    dataset.append(other)
    result = xml_import(tmp_path, root)
    observed = rows(result, "observations")[-1]
    assert [item["fraction_decimal"] for item in observed["composition"]] == ["0.333", "0.666"]
    assert not any(item["derived"] for item in observed["composition"])
    assert observed["composition_basis"] == ("mole" if basis == "Mole fraction" else "mass")


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("Prediction", "predicted"),
        ("CriticalEvaluation", "critically_evaluated"),
        ("sMethodName", "unknown"),
    ],
)
def test_origin_is_explicit_and_does_not_claim_validation(tmp_path, root, kind, expected):
    family = node(
        root, "t:PureOrMixtureData/t:Property/t:Property-MethodID/t:PropertyGroup/t:VolumetricProp"
    )
    family.remove(node(family, "t:eMethodName"))
    add(family, kind, "Literature method" if kind == "sMethodName" else None)
    result = xml_import(tmp_path, root)
    assert rows(result, "observations")[0]["data_origin"] == expected
    assert read_source_bundle(result.output_directory).manifest["independently_validated"] is False


@pytest.mark.parametrize("case", ["standard", "expanded", "asymmetric", "negative", "unknown"])
def test_uncertainty_assessments_are_separate_and_do_not_erase_values(tmp_path, root, case):
    prop = node(root, "t:PureOrMixtureData/t:Property")
    declared = add(prop, "PropUncertainty")
    add(declared, "nUncertAssessNum", "2")
    add(declared, "nCoverageFactor", "2")
    reported = add(node(root, "t:PureOrMixtureData/t:NumValues/t:PropertyValue"), "PropUncertainty")
    add(reported, "nUncertAssessNum", "2")
    if case == "asymmetric":
        asym = add(reported, "AsymExpandUncert")
        add(asym, "nNegativeValue", "0.4")
        add(asym, "nPositiveValue", "0.6")
    else:
        add(
            reported,
            "nExpandUncertValue" if case == "expanded" else "nStdUncertValue",
            "-1" if case == "negative" else "0.4",
        )
    if case == "unknown":
        add(declared, "RelativeUncertainty", "percent")
    result = xml_import(tmp_path, root)
    assert result.counts.normalized == 3
    uncertainties = rows(result, "uncertainties")
    assert len(uncertainties) == 2
    original = next(row for row in uncertainties if row["combined"])
    selected = next(row for row in uncertainties if not row["combined"])
    assert original["standard_uncertainty"] is None
    if case == "asymmetric":
        assert selected["standard_uncertainty"] is None
        assert (selected["standard_lower"], selected["standard_upper"]) == (0.2, 0.3)
    elif case in {"negative", "unknown"}:
        assert selected["status"] == ("invalid" if case == "negative" else "unsupported")
        assert selected["standard_uncertainty"] is None
    else:
        assert selected["standard_uncertainty"] == (0.2 if case == "expanded" else 0.4)


@pytest.mark.parametrize(
    "malformed", ["duplicate_coverage", "nested_coverage", "duplicate_magnitude"]
)
def test_ambiguous_uncertainty_does_not_discard_interpretable_measurement(
    tmp_path, root, malformed
):
    declared = node(root, "t:PureOrMixtureData/t:Property/t:CombinedUncertainty")
    reported = node(root, "t:PureOrMixtureData/t:NumValues/t:PropertyValue/t:CombinedUncertainty")
    if malformed == "duplicate_coverage":
        add(declared, "nCombCoverageFactor", "2")
        add(declared, "nCombCoverageFactor", "3")
    elif malformed == "nested_coverage":
        add(add(declared, "nCombCoverageFactor"), "unknown", "2")
    else:
        add(reported, "nCombExpandUncertValue", "0.7")
    result = xml_import(tmp_path, root)
    assert result.counts.normalized == 3
    assessment = rows(result, "uncertainties")[0]
    assert assessment["status"] == "unsupported"
    assert assessment["standard_uncertainty"] is None
    assert "unsupported_uncertainty_qualifier" in dict(result.warning_counts)


def test_coordinate_uncertainty_uses_scale_and_attaches_to_its_point(tmp_path, root):
    dataset = node(root, "t:PureOrMixtureData")
    variable = node(dataset, "t:Variable")
    declared = add(variable, "VarUncertainty")
    add(declared, "nUncertAssessNum", "1")
    point = node(dataset, "t:NumValues")
    value = node(point, "t:VariableValue")
    uncertainty = add(value, "VarUncertainty")
    add(uncertainty, "nUncertAssessNum", "1")
    add(uncertainty, "nStdUncertValue", "0.02")
    duplicate = copy.deepcopy(node(dataset, "t:Property"))
    node(duplicate, "t:nPropNumber").text = "2"
    dataset.append(duplicate)
    duplicate_value = copy.deepcopy(node(point, "t:PropertyValue"))
    node(duplicate_value, "t:nPropNumber").text = "2"
    point.append(duplicate_value)
    constraint = node(dataset, "t:Constraint")
    node(constraint, "t:ConstraintID/t:ConstraintType/t:eTemperature").text = "Temperature, degC"
    node(constraint, "t:nConstraintValue").text = "25"
    add(add(constraint, "ConstrUncertainty"), "nStdUncertValue", "0.1")
    result = xml_import(tmp_path, root)
    observed = rows(result, "observations")
    assert observed[0]["point_id"] == observed[1]["point_id"]
    assert observed[0]["observation_id"] != observed[1]["observation_id"]
    variables = [row for row in rows(result, "uncertainties") if row["target_kind"] == "variable"]
    constraints = [
        row for row in rows(result, "uncertainties") if row["target_kind"] == "constraint"
    ]
    assert len(variables) == len(constraints) == 1
    assert variables[0]["standard_uncertainty"] == 20
    assert variables[0]["unit"] == "Pa"
    assert variables[0]["observation_id"] is None
    assert variables[0]["point_id"] == observed[0]["point_id"]
    assert constraints[0]["standard_uncertainty"] == 0.1
    assert constraints[0]["point_id"] is None


def test_accounting_and_empty_tables_preserve_all_evidence(tmp_path, root):
    for prop in root.findall(
        "t:PureOrMixtureData/t:Property/t:Property-MethodID/t:PropertyGroup/t:VolumetricProp/t:ePropName",
        NS,
    ):
        prop.text = "Unsupported density units"
    result = xml_import(tmp_path, root)
    assert result.status == "no_eligible_observations"
    assert result.counts.unsupported == result.counts.total == 3
    assert result.counts.normalized == 0
    bundle = read_source_bundle(result.output_directory)
    assert len(bundle.catalog["records"]) == 3
    for name in ("observations", "provenance", "uncertainties"):
        table = pq.read_table(result.output_directory / "data" / f"{name}.parquet")
        assert len(table) == 0
        assert table.schema.equals(table_schemas()[name], check_metadata=True)


def test_selection_and_invalid_values_have_no_canonical_rows(tmp_path, root):
    node(root, "t:PureOrMixtureData/t:NumValues/t:PropertyValue/t:nPropValue").text = "NaN"
    source = tmp_path / "source.xml"
    source.write_bytes(ET.tostring(root))
    result = import_source(
        source,
        config=settings(tmp_path, selection="selections:\n  - dataset_index: 0\n"),
        output_root=tmp_path / "out",
    )
    assert result.counts.invalid == result.counts.unselected == result.counts.normalized == 1
    assert len(read_source_bundle(result.output_directory).catalog["records"]) == 3


@pytest.mark.parametrize("phase", ["source_import_normalization", "source_import_verification"])
def test_cancellation_leaves_no_bundle(tmp_path, phase):
    cancel = False

    def on_phase(name, cancellable):
        nonlocal cancel
        if name == phase:
            cancel = True

    control = ExecutionControl(lambda: cancel, on_phase, lambda done, total: None)
    with pytest.raises(ExecutionCancelled):
        run_source_import(
            FIXTURES / "density.xml",
            settings(tmp_path),
            output_root=tmp_path / "out",
            control=control,
        )
    assert not (tmp_path / "out").exists() or not list((tmp_path / "out").iterdir())


@pytest.mark.parametrize("changed", ["source", "config", "artifact"])
def test_changes_at_protected_handoff_prevent_publication(tmp_path, changed):
    source = tmp_path / "source.xml"
    source.write_bytes((FIXTURES / "density.xml").read_bytes())
    config = settings(tmp_path)

    def protect(name):
        path = (
            source
            if changed == "source"
            else config
            if changed == "config"
            else next((tmp_path / "out").glob(".*/report.json"))
        )
        path.write_bytes(path.read_bytes() + b" ")

    control = ExecutionControl(
        lambda: False, lambda name, cancel: None, lambda done, total: None, protect
    )
    with pytest.raises(Exception, match="changed"):
        run_source_import(source, config, output_root=tmp_path / "out", control=control)
    assert not list((tmp_path / "out").iterdir())


def test_late_cancellation_finishes_protected_bundle(tmp_path):
    cancel = False

    def protect(name):
        nonlocal cancel
        cancel = True

    control = ExecutionControl(
        lambda: cancel, lambda name, cancel: None, lambda done, total: None, protect
    )
    result = run_source_import(
        FIXTURES / "density.xml", settings(tmp_path), output_root=tmp_path / "out", control=control
    )
    assert result.output_directory.is_dir()
    read_source_bundle(result.output_directory)


def test_stale_preview_and_symlink_output_fail_before_writing(tmp_path):
    config = settings(tmp_path)
    preview = preview_source_import(FIXTURES / "density.xml", config=config)
    config.write_text(config.read_text() + "# changed\n")
    with pytest.raises(SourceImportError):
        run_source_import(
            FIXTURES / "density.xml", config, output_root=tmp_path / "out", accepted_preview=preview
        )
    assert not (tmp_path / "out").exists()
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real", target_is_directory=True)
    with pytest.raises(SourceImportError, match="unsafe_bundle_path"):
        run_source_import(FIXTURES / "density.xml", config, output_root=tmp_path / "link")
    assert not list((tmp_path / "real").iterdir())


@pytest.mark.parametrize(
    "corruption",
    ["hash", "kind", "version", "path", "schema", "count", "join", "identity", "report"],
)
def test_reader_rejects_corrupted_bundles(tmp_path, corruption):
    result = import_source(
        FIXTURES / "density.xml", config=settings(tmp_path), output_root=tmp_path / "out"
    )
    manifest = json.loads(result.manifest_path.read_bytes())
    if corruption == "hash":
        (result.output_directory / "report.json").write_text("{}")
    elif corruption == "kind":
        manifest["bundle_kind"] = "future_kind"
    elif corruption == "version":
        manifest["schema_version"] = 999
    elif corruption == "path":
        manifest["artifact_hashes"]["../outside"] = "0" * 64
    elif corruption == "schema":
        manifest["tables"]["observations"]["columns"] = []
    elif corruption == "count":
        manifest["tables"]["observations"]["row_count"] = 999
    elif corruption == "identity":
        del manifest["context_id"]
    elif corruption == "report":
        path = result.output_directory / "report.json"
        report = json.loads(path.read_bytes())
        report["diagnostics_preview"] = "malformed"
        path.write_text(json.dumps(report))
        manifest["artifact_hashes"]["report.json"] = hashlib.sha256(path.read_bytes()).hexdigest()
    else:
        path = result.output_directory / "catalog.json"
        catalog = json.loads(path.read_bytes())
        catalog["records"][0]["point_id"] = "broken"
        path.write_text(json.dumps(catalog))
        manifest["artifact_hashes"]["catalog.json"] = hashlib.sha256(path.read_bytes()).hexdigest()
    result.manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(SourceImportError):
        read_source_bundle(result.output_directory)


def test_cli_preview_import_and_offline_inspection(tmp_path):
    runner = CliRunner()
    config = tmp_path / "import.yaml"
    assert runner.invoke(app, ["init", "source_import", str(config)]).exit_code == 0
    args = [
        "import",
        str(FIXTURES / "density.xml"),
        "--config",
        str(config),
        "--out",
        str(tmp_path / "out"),
        "--json",
    ]
    preview = runner.invoke(app, [*args, "--preview"])
    assert preview.exit_code == 0, preview.output
    assert json.loads(preview.stdout)["counts"]["eligible"] == 3
    assert not (tmp_path / "out").exists()
    completed = runner.invoke(app, args)
    assert completed.exit_code == 0, completed.output
    payload = json.loads(completed.stdout)
    original = Path(payload["output_directory"])
    moved = tmp_path / "moved"
    original.rename(moved)
    inspected = runner.invoke(app, ["inspect", str(moved), "--format", "json"])
    assert inspected.exit_code == 0, inspected.output
    assert json.loads(inspected.stdout)["source_kind"] == "imported_source"
    assert json.loads(inspected.stdout)["counts"]["normalized"] == 3
    assert "Records:" in inspect_source(moved).format_text()
    failed = runner.invoke(app, ["import", "missing.xml", "--config", str(config), "--json"])
    assert failed.exit_code == 2
    assert json.loads(failed.stdout)["status"] == "failed"


def test_destination_collision_never_overwrites_existing_directory(tmp_path):
    from carnopy.domain.failures import OutputError

    destination = None

    def protect(name):
        nonlocal destination
        staging = next((tmp_path / "out").iterdir())
        destination = staging.with_name(staging.name[1 : -len(".staging")])
        destination.mkdir()
        (destination / "human.txt").write_text("keep me")

    control = ExecutionControl(
        lambda: False, lambda name, cancel: None, lambda done, total: None, protect
    )
    with pytest.raises(OutputError, match="overwrite"):
        run_source_import(
            FIXTURES / "density.xml",
            settings(tmp_path),
            output_root=tmp_path / "out",
            control=control,
        )
    assert (destination / "human.txt").read_text() == "keep me"
    assert list((tmp_path / "out").iterdir()) == [destination]


def test_replaced_staging_is_not_published_or_deleted(tmp_path):
    def protect(name):
        staging = next((tmp_path / "out").iterdir())
        staging.rename(tmp_path / "displaced")
        staging.mkdir()
        (staging / "human.txt").write_text("keep me")

    control = ExecutionControl(
        lambda: False, lambda name, cancel: None, lambda done, total: None, protect
    )
    with pytest.raises(Exception, match=r"missing|replaced|source_read"):
        run_source_import(
            FIXTURES / "density.xml",
            settings(tmp_path),
            output_root=tmp_path / "out",
            control=control,
        )
    remaining = list((tmp_path / "out").iterdir())
    assert len(remaining) == 1
    assert (remaining[0] / "human.txt").read_text() == "keep me"


def test_table_limit_failure_cleans_staging(tmp_path, monkeypatch):
    from carnopy.domain.failures import OutputError
    from carnopy.sources import tables

    monkeypatch.setattr(tables, "MAX_TABLE_ROWS", 1)
    with pytest.raises(OutputError, match="resource limit"):
        run_source_import(
            FIXTURES / "density.xml", settings(tmp_path), output_root=tmp_path / "out"
        )
    assert not list((tmp_path / "out").iterdir())


def test_cli_no_eligible_outcome_is_a_finalized_audit(tmp_path, root):
    for prop in root.findall("t:PureOrMixtureData/t:NumValues/t:PropertyValue/t:nPropValue", NS):
        prop.text = "NaN"
    source = tmp_path / "invalid.xml"
    source.write_bytes(ET.tostring(root))
    result = CliRunner().invoke(
        app,
        [
            "import",
            str(source),
            "--config",
            str(settings(tmp_path)),
            "--out",
            str(tmp_path / "out"),
            "--json",
        ],
    )
    assert result.exit_code == 3, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "no_eligible_observations"
    assert read_source_bundle(payload["output_directory"]).manifest["counts"]["invalid"] == 3


def test_source_manifest_limits_do_not_restrict_legacy_preparation(tmp_path):
    import pyarrow as pa

    (tmp_path / "preparation.normalized.json").write_text("{}")
    (tmp_path / "diagnostics.json").write_text("{}")
    names = ("provenance", "diagnostics", "exclusions")
    for name in names:
        pq.write_table(pa.table({"case_id": [0]}), tmp_path / f"{name}.parquet")
    manifest = {
        "data_artifacts": {name: f"{name}.parquet" for name in names},
        "historical_metadata": "x" * (1024 * 1024),
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    assert "Source kind: preparation bundle" in inspect_source(tmp_path).format_text()


def test_import_and_help_do_not_load_backends(tmp_path):
    config = settings(tmp_path)
    script = """
import sys
from carnopy import ImportConfig, ImportResult, import_source
from carnopy.cli import app
from typer.testing import CliRunner
for args in (["--help"], ["import", "--help"], ["init", "--help"]):
    assert CliRunner().invoke(app, args).exit_code == 0
heavy = ("CoolProp", "numpy", "pandas", "pyarrow", "matplotlib")
assert not any(name in sys.modules for name in heavy)
result = import_source(sys.argv[1], config=sys.argv[2], output_root=sys.argv[3])
assert result.counts.normalized == 3
assert "CoolProp" not in sys.modules
"""
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(FIXTURES / "density.xml"),
            str(config),
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
