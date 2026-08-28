from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from carnopy.app.scene_contracts import (
    MAX_SCENE_BUNDLE_BYTES,
    MAX_SCENE_EDGES,
    MAX_SCENE_POINTS,
    MAX_SCENE_QUADS,
    CategoricalSetFilter,
    NumericRangeFilter,
    SceneBlockContext,
    SceneBoundControl,
    SceneBoundTable,
    SceneCapabilityBlocker,
    SceneContractError,
    SceneCounts,
    SceneFieldProfile,
    SceneFileIdentity,
    SceneGapSummary,
    SceneProfile,
    SceneRepresentationCapability,
    SceneRequest,
    SceneSelectionDefaults,
    SceneSourceBinding,
    SceneTopologyAxis,
    SceneTopologyEvidence,
    canonical_gap_summaries,
    scene_filters_match,
    validate_scene_defaults,
    validate_scene_limits,
    validate_scene_request,
)


def _file_identity(
    path: str = "/workspace/run/dataset.parquet",
    *,
    sha256: str = "a" * 64,
    device: int = 10,
    inode: int = 20,
    size: int = 30,
    modified_ns: int = 40,
) -> SceneFileIdentity:
    return SceneFileIdentity(
        path=path,
        sha256=sha256,
        device=device,
        inode=inode,
        size=size,
        modified_ns=modified_ns,
    )


def _binding(
    *,
    source_path: str = "/workspace/run",
    revision: str = "b" * 64,
    selected_sha256: str = "a" * 64,
    device: int = 10,
    reverse: bool = False,
) -> SceneSourceBinding:
    selected = SceneBoundTable(
        table_id="dataset",
        label="Dataset",
        source_format="parquet",
        artifact=_file_identity(sha256=selected_sha256, device=device),
        metadata=_file_identity(
            "/workspace/run/metadata.json",
            sha256="c" * 64,
            device=device,
            inode=21,
        ),
    )
    other = SceneBoundTable(
        table_id="other",
        label="Other",
        source_format="csv",
        artifact=_file_identity(
            "/workspace/run/other.csv",
            sha256="d" * 64,
            device=device,
            inode=22,
        ),
    )
    controls = (
        SceneBoundControl(
            name="report.json",
            artifact=_file_identity(
                "/workspace/run/report.json",
                sha256="e" * 64,
                device=device,
                inode=23,
            ),
        ),
        SceneBoundControl(
            name="metadata.json",
            artifact=_file_identity(
                "/workspace/run/metadata.json",
                sha256="c" * 64,
                device=device,
                inode=21,
            ),
        ),
    )
    return SceneSourceBinding(
        source_path=source_path,
        source_kind="dataset",
        inspection_revision=revision,
        selected_table_id="dataset",
        tables=(other, selected) if reverse else (selected, other),
        controls=controls,
    )


def _numeric_field(
    field_id: str,
    *,
    axis_eligible: bool = True,
    scalar_eligible: bool = True,
    filter_kind: str | None = "numeric_range",
    minimum: float = 1.0,
    maximum: float = 4.0,
    classification: str = "source_coordinate",
    ineligible_reason: str = "",
) -> SceneFieldProfile:
    return SceneFieldProfile(
        field_id=field_id,
        column=f"{field_id}_column",
        label=field_id.replace("_", " ").title(),
        dtype="float64",
        kind="numeric",
        classification=classification,
        origin="table",
        unit="1",
        unit_status="dimensionless",
        source_row_count=5,
        source_valid_count=4,
        value_count=3,
        missing_count=1,
        finite_count=3,
        minimum=minimum,
        maximum=maximum,
        varying=minimum != maximum,
        positive_domain=minimum > 0.0,
        axis_eligible=axis_eligible,
        scalar_eligible=scalar_eligible,
        filter_kind=filter_kind,
        ineligible_reason=ineligible_reason,
    )


def _categorical_field() -> SceneFieldProfile:
    return SceneFieldProfile(
        field_id="phase",
        column="phase",
        label="Phase",
        dtype="string",
        kind="categorical",
        classification="context",
        origin="table",
        unit=None,
        unit_status="unreported",
        source_row_count=5,
        source_valid_count=4,
        value_count=4,
        missing_count=0,
        distinct_values=("Liquid", "Gas", "Gas"),
        varying=True,
        axis_eligible=False,
        scalar_eligible=False,
        filter_kind="categorical_set",
    )


def _request(
    *,
    binding: SceneSourceBinding | None = None,
    x_field: str = "temperature",
    y_field: str = "pressure",
    z_field: str = "specific_enthalpy",
    scalar_field: str | None = None,
    filters: tuple[CategoricalSetFilter | NumericRangeFilter, ...] = (),
) -> SceneRequest:
    return SceneRequest(
        binding=_binding() if binding is None else binding,
        x_field=x_field,
        y_field=y_field,
        z_field=z_field,
        scalar_field=scalar_field,
        filters=filters,
    )


def _fields() -> tuple[SceneFieldProfile, ...]:
    return (
        _numeric_field("temperature"),
        _numeric_field("pressure", minimum=100_000.0, maximum=400_000.0),
        _numeric_field(
            "specific_enthalpy",
            minimum=-2.0,
            maximum=8.0,
            classification="emitted_property",
        ),
        _categorical_field(),
    )


def _profile(**changes: object) -> SceneProfile:
    payload: dict[str, object] = {
        "binding": _binding(),
        "source_row_count": 5,
        "fields": _fields(),
        "topology": SceneTopologyEvidence(
            status="exact",
            axes=(
                SceneTopologyAxis(
                    field_id="temperature",
                    source_column="temperature_column",
                    unit="1",
                    levels=(1.0, 2.0),
                ),
                SceneTopologyAxis(
                    field_id="pressure",
                    source_column="pressure_column",
                    unit="1",
                    levels=(100_000.0, 200_000.0),
                ),
            ),
            context_fields=("fluid", "phase"),
        ),
        "defaults": SceneSelectionDefaults(
            x_field="temperature",
            y_field="pressure",
            z_field="specific_enthalpy",
        ),
        "build_eligible": True,
    }
    payload.update(changes)
    return SceneProfile.model_validate(payload)


def test_source_binding_canonicalizes_tables_and_controls_without_retargeting() -> None:
    binding = _binding(reverse=True)

    assert [table.table_id for table in binding.tables] == ["dataset", "other"]
    assert [control.name for control in binding.controls] == ["metadata.json", "report.json"]
    assert binding.selected_table().artifact.sha256 == "a" * 64
    assert binding.identity_payload() == {
        "source_kind": "dataset",
        "inspection_revision": "b" * 64,
        "table_id": "dataset",
        "table_sha256": "a" * 64,
    }


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"source_path": "relative/run"}, "must be absolute"),
        ({"inspection_revision": "ABC"}, "64 lowercase hexadecimal"),
        ({"selected_table_id": "missing"}, "absent from the copied binding"),
        ({"tables": ()}, "at least one table"),
    ],
)
def test_source_binding_rejects_noncanonical_or_incomplete_identity(
    change: dict[str, object],
    match: str,
) -> None:
    payload = _binding().model_dump(mode="python")
    payload.update(change)

    with pytest.raises(ValidationError, match=match):
        SceneSourceBinding.model_validate(payload)


def test_source_binding_rejects_duplicate_table_and_control_ids() -> None:
    binding = _binding()
    payload = binding.model_dump(mode="python")
    payload["tables"] = (binding.tables[0], binding.tables[0])
    with pytest.raises(ValidationError, match="duplicate table IDs"):
        SceneSourceBinding.model_validate(payload)

    payload = binding.model_dump(mode="python")
    payload["controls"] = (binding.controls[0], binding.controls[0])
    with pytest.raises(ValidationError, match="duplicate control names"):
        SceneSourceBinding.model_validate(payload)


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"path": "relative.csv"}, "must be absolute"),
        ({"sha256": "A" * 64}, "lowercase hexadecimal"),
        ({"device": "10"}, "valid integer"),
        ({"inode": 0}, "greater than 0"),
    ],
)
def test_file_identity_rejects_noncanonical_values(
    change: dict[str, object],
    match: str,
) -> None:
    payload = _file_identity().model_dump(mode="python")
    payload.update(change)

    with pytest.raises(ValidationError, match=match):
        SceneFileIdentity.model_validate(payload)


def test_field_profiles_preserve_dtype_classification_and_exact_category_case() -> None:
    numeric = _numeric_field("temperature")
    categorical = _categorical_field()

    assert numeric.dtype == "float64"
    assert numeric.classification == "source_coordinate"
    assert numeric.positive_domain
    assert categorical.distinct_values == ("Gas", "Liquid")
    assert categorical.filter_kind == "categorical_set"


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"source_valid_count": 6}, "exceeds its source row count"),
        ({"missing_count": 0}, "do not equal valid rows"),
        ({"finite_count": 4}, "exceeds its value count"),
        ({"minimum": 5.0}, "minimum exceeds"),
        ({"positive_domain": False}, "log-domain status disagrees"),
        ({"varying": False}, "variability disagrees"),
        ({"distinct_values": ("numeric",)}, "must not declare categorical"),
        ({"filter_kind": "categorical_set"}, "numeric-range filters"),
    ],
)
def test_numeric_field_profile_rejects_contradictory_evidence(
    change: dict[str, object],
    match: str,
) -> None:
    payload = _numeric_field("temperature").model_dump(mode="python")
    payload.update(change)

    with pytest.raises(ValidationError, match=match):
        SceneFieldProfile.model_validate(payload)


def test_categorical_field_profile_rejects_numeric_or_eligibility_claims() -> None:
    payload = _categorical_field().model_dump(mode="python")
    payload["axis_eligible"] = True
    with pytest.raises(ValidationError, match="only numeric"):
        SceneFieldProfile.model_validate(payload)

    payload = _categorical_field().model_dump(mode="python")
    payload["minimum"] = 1.0
    with pytest.raises(ValidationError, match="must not declare numeric ranges"):
        SceneFieldProfile.model_validate(payload)


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"unit": None}, "dimensionless scene fields require unit"),
        ({"unit_status": "unreported"}, "unreported units must not declare"),
        (
            {"classification": "recorded_transform"},
            "require transformed-unit status",
        ),
    ],
)
def test_numeric_field_profile_rejects_contradictory_unit_metadata(
    change: dict[str, object],
    match: str,
) -> None:
    payload = _numeric_field("temperature").model_dump(mode="python")
    payload.update(change)

    with pytest.raises(ValidationError, match=match):
        SceneFieldProfile.model_validate(payload)


def test_scene_profile_locks_binding_fields_topology_and_incomplete_defaults() -> None:
    profile = _profile(defaults=SceneSelectionDefaults(x_field="temperature"))

    assert profile.scene_profile_schema_version == 1
    assert profile.binding.selected_table_id == "dataset"
    assert [field.field_id for field in profile.fields] == [
        "temperature",
        "pressure",
        "specific_enthalpy",
        "phase",
    ]
    assert not profile.defaults.complete
    assert profile.build_eligible


@pytest.mark.parametrize(
    ("change", "match"),
    [
        (
            {"fields": (_numeric_field("temperature"), _numeric_field("temperature"))},
            "duplicate field IDs",
        ),
        (
            {"fields": (_numeric_field("temperature"),)},
            "absent from the field profile",
        ),
        (
            {
                "fields": (
                    _numeric_field("temperature", classification="emitted_property"),
                    *_fields()[1:],
                )
            },
            "must be classified source coordinates",
        ),
        (
            {"defaults": SceneSelectionDefaults(x_field="missing")},
            "is unavailable",
        ),
        (
            {
                "fields": _fields()[:2],
                "defaults": SceneSelectionDefaults(
                    x_field="temperature",
                    y_field="pressure",
                ),
            },
            "three axis fields",
        ),
        (
            {"build_eligible": False},
            "require an explicit reason",
        ),
        (
            {"ineligible_reason": "blocked"},
            "must not declare a blocker",
        ),
    ],
)
def test_scene_profile_rejects_contradictory_contracts(
    change: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValidationError, match=match):
        _profile(**change)


def test_filters_are_exact_deduplicated_and_canonical() -> None:
    categorical = CategoricalSetFilter(
        field_id="phase",
        values=("Liquid", "Gas", "Liquid", " gas "),
    )
    numeric = NumericRangeFilter(field_id="temperature", minimum=-0.0, maximum=10)

    assert categorical.values == (" gas ", "Gas", "Liquid")
    assert numeric.minimum == 0.0
    assert numeric.maximum == 10.0


def test_filters_are_inclusive_or_within_a_field_and_and_across_fields() -> None:
    filters = (
        CategoricalSetFilter(field_id="phase", values=("Gas", "Liquid")),
        NumericRangeFilter(field_id="temperature", minimum=1.0, maximum=2.0),
    )

    assert scene_filters_match(filters, {"phase": "Gas", "temperature": 1.0})
    assert scene_filters_match(filters, {"phase": "Liquid", "temperature": 2.0})
    assert not scene_filters_match(filters, {"phase": "gas", "temperature": 1.5})
    assert not scene_filters_match(filters, {"phase": "Gas", "temperature": 2.0000000001})
    assert not scene_filters_match(filters, {"phase": "Gas", "temperature": "1.5"})
    assert not scene_filters_match(filters, {"phase": "Gas"})


@pytest.mark.parametrize(
    ("factory", "match"),
    [
        (
            lambda: CategoricalSetFilter(field_id="phase", values=()),
            "at least one value",
        ),
        (
            lambda: CategoricalSetFilter(field_id="phase", values=(1,)),
            "only exact strings",
        ),
        (
            lambda: NumericRangeFilter(field_id="temperature", minimum=None, maximum=None),
            "at least one bound",
        ),
        (
            lambda: NumericRangeFilter(field_id="temperature", minimum=2.0, maximum=1.0),
            "minimum exceeds",
        ),
        (
            lambda: NumericRangeFilter(field_id="temperature", minimum="1"),
            "explicit real number",
        ),
        (
            lambda: NumericRangeFilter(field_id="temperature", minimum=True),
            "explicit real number",
        ),
        (
            lambda: NumericRangeFilter(field_id="temperature", minimum=float("inf")),
            "must be finite",
        ),
        (
            lambda: NumericRangeFilter(field_id="temperature", minimum=2**53 + 1),
            "not exactly representable",
        ),
    ],
)
def test_filters_reject_coercion_and_invalid_domains(factory: object, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        factory()  # type: ignore[operator]


def test_request_allows_scalar_axis_reuse_but_requires_distinct_coordinates() -> None:
    request = _request(scalar_field="temperature")

    assert request.scalar_field == request.x_field

    with pytest.raises(ValidationError, match="must be distinct"):
        _request(z_field="temperature")


def test_request_canonicalizes_filter_order_and_rejects_duplicate_fields() -> None:
    phase = CategoricalSetFilter(field_id="phase", values=("Gas",))
    temperature = NumericRangeFilter(field_id="temperature", minimum=1.0)

    request = _request(filters=(temperature, phase))

    assert [filter_value.field_id for filter_value in request.filters] == [
        "phase",
        "temperature",
    ]
    with pytest.raises(ValidationError, match="multiple filters"):
        _request(filters=(temperature, NumericRangeFilter(field_id="temperature", maximum=2.0)))


def test_request_rejects_presentation_fields_instead_of_hashing_them() -> None:
    payload = _request().model_dump(mode="python")

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SceneRequest.model_validate({**payload, "representation": "surface"})
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SceneRequest.model_validate({**payload, "x_scale": "log"})
    assert set(_request().canonical_payload()) == {
        "scene_request_schema_version",
        "source",
        "coordinates",
        "scalar",
        "filters",
    }


def test_request_identity_is_canonical_and_excludes_operational_file_identity() -> None:
    filters = (
        NumericRangeFilter(field_id="temperature", minimum=1.0, maximum=4.0),
        CategoricalSetFilter(field_id="phase", values=("Liquid", "Gas")),
    )
    request = _request(binding=_binding(reverse=True), filters=filters)
    reordered = _request(binding=_binding(), filters=tuple(reversed(filters)))
    relocated = _request(
        binding=_binding(source_path="/different/copy", device=999),
        filters=filters,
    )

    assert request.request_id == reordered.request_id == relocated.request_id
    assert request.request_id.startswith("scene-")
    assert len(request.request_id) == len("scene-") + 64
    assert (
        _request().request_id
        == "scene-ec7cee3b9a5cae88906fd23936527a685b3bc795061951396e01305d53c9e28b"
    )
    assert _request(scalar_field="temperature").request_id != _request().request_id
    assert _request(binding=_binding(revision="f" * 64)).request_id != _request().request_id
    assert _request(binding=_binding(selected_sha256="f" * 64)).request_id != _request().request_id


def test_request_validation_uses_profile_eligibility_and_exact_categories() -> None:
    request = _request(
        scalar_field="temperature",
        filters=(
            CategoricalSetFilter(field_id="phase", values=("Gas",)),
            NumericRangeFilter(field_id="pressure", minimum=100_000.0),
        ),
    )

    assert validate_scene_request(request, _fields()) is request

    with pytest.raises(SceneContractError, match="unobserved exact values") as error:
        validate_scene_request(
            _request(filters=(CategoricalSetFilter(field_id="phase", values=("gas",)),)),
            _fields(),
        )
    assert error.value.code == "invalid_scene_request"


def test_request_validation_rejects_unknown_ineligible_and_wrong_filter_fields() -> None:
    with pytest.raises(SceneContractError, match="is unavailable"):
        validate_scene_request(_request(z_field="unknown"), _fields())

    fields = (
        *_fields()[:2],
        _numeric_field(
            "specific_enthalpy",
            axis_eligible=False,
            classification="emitted_property",
            ineligible_reason="conversion is not lossless",
        ),
        _fields()[3],
    )
    with pytest.raises(SceneContractError, match="not axis eligible") as error:
        validate_scene_request(_request(), fields)
    assert error.value.details["reason"] == "conversion is not lossless"

    with pytest.raises(SceneContractError, match="filter kind"):
        validate_scene_request(
            _request(filters=(NumericRangeFilter(field_id="phase", minimum=1.0),)),
            _fields(),
        )


def test_profile_defaults_may_be_incomplete_but_selected_axes_are_distinct_and_varying() -> None:
    incomplete = SceneSelectionDefaults(x_field="temperature", y_field="pressure")
    complete = SceneSelectionDefaults(
        x_field="temperature",
        y_field="pressure",
        z_field="specific_enthalpy",
    )

    assert not incomplete.complete
    assert complete.complete
    assert validate_scene_defaults(complete, _fields()) is complete

    with pytest.raises(ValidationError, match="must be distinct"):
        SceneSelectionDefaults(x_field="temperature", y_field="temperature")

    constant = _numeric_field("constant", minimum=1.0, maximum=1.0)
    with pytest.raises(SceneContractError, match="not a varying axis"):
        validate_scene_defaults(SceneSelectionDefaults(x_field="constant"), (constant,))


def test_topology_preserves_exact_original_level_order_and_context_order() -> None:
    evidence = SceneTopologyEvidence(
        status="exact",
        axes=(
            SceneTopologyAxis(
                field_id="temperature",
                source_column="temperature_K",
                unit="K",
                levels=(300.0, 280.0, 310.0),
            ),
        ),
        context_fields=("phase", "fluid"),
    )

    assert evidence.axes[0].levels == (300.0, 280.0, 310.0)
    assert evidence.context_fields == ("fluid", "phase")


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        (
            {
                "status": "exact",
                "axes": [
                    {
                        "field_id": "temperature",
                        "source_column": "temperature_K",
                        "unit": "K",
                        "levels": [1.0, 1.0],
                    }
                ],
            },
            "duplicate exact levels",
        ),
        (
            {"status": "exact", "context_fields": ["fluid", "fluid"]},
            "must be unique",
        ),
        (
            {"status": "exact", "context_fields": ["arbitrary"]},
            "unknown scene topology context",
        ),
        (
            {"status": "unavailable"},
            "requires a code and reason",
        ),
        (
            {
                "status": "unavailable",
                "reason_code": "missing_metadata",
                "reason": "Sampler metadata is unavailable.",
                "axes": [
                    {
                        "field_id": "temperature",
                        "source_column": "temperature_K",
                        "unit": "K",
                        "levels": [1.0],
                    }
                ],
            },
            "must not declare exact axes",
        ),
    ],
)
def test_topology_rejects_ambiguous_or_contradictory_evidence(
    payload: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValidationError, match=match):
        SceneTopologyEvidence.model_validate(payload)


def test_block_context_has_one_fixed_canonical_partition_key() -> None:
    context = SceneBlockContext(
        source_artifact="models/heos/run/dataset.parquet",
        source_run_id="run-1",
        fluid="Water",
        backend_model="heos",
        phase="gas",
        scenario="holdout",
        partition="test",
    )

    assert context.canonical_items() == (
        ("source_artifact", "models/heos/run/dataset.parquet"),
        ("source_run_id", "run-1"),
        ("fluid", "Water"),
        ("backend_model", "heos"),
        ("phase", "gas"),
        ("saturation_endpoint", None),
        ("scenario", "holdout"),
        ("partition", "test"),
    )
    with pytest.raises(ValidationError, match="must be declared together"):
        SceneBlockContext(
            source_artifact="dataset.parquet",
            source_run_id="run-1",
            scenario="holdout",
        )


def test_gap_and_capability_contracts_are_deterministic_and_all_block_explicit() -> None:
    gaps = canonical_gap_summaries(
        (
            SceneGapSummary(code="source_invalid", count=2, block_index=1),
            SceneGapSummary(code="filtered", count=3),
        )
    )
    blockers = (
        SceneCapabilityBlocker(
            code="no_valid_quads",
            message="Block 2 has no complete cell.",
            block_index=2,
        ),
        SceneCapabilityBlocker(
            code="no_valid_quads",
            message="Block 1 has no complete cell.",
            block_index=1,
        ),
    )
    capability = SceneRepresentationCapability(
        representation="surface",
        available=False,
        blockers=blockers,
    )

    assert [gap.code for gap in gaps] == ["filtered", "source_invalid"]
    assert [blocker.block_index for blocker in capability.blockers] == [1, 2]
    with pytest.raises(ValidationError, match="must not contain blockers"):
        SceneRepresentationCapability(
            representation="surface",
            available=True,
            blockers=blockers,
        )
    with pytest.raises(ValidationError, match="require at least one blocker"):
        SceneRepresentationCapability(representation="surface", available=False)


@pytest.mark.parametrize(
    ("measure", "limit"),
    [
        ("points", MAX_SCENE_POINTS),
        ("edges", MAX_SCENE_EDGES),
        ("quads", MAX_SCENE_QUADS),
        ("bundle_bytes", MAX_SCENE_BUNDLE_BYTES),
    ],
)
def test_scene_limits_accept_boundary_and_reject_one_over(measure: str, limit: int) -> None:
    values = {
        "points": MAX_SCENE_POINTS,
        "edges": MAX_SCENE_EDGES,
        "quads": MAX_SCENE_QUADS,
        "bundle_bytes": MAX_SCENE_BUNDLE_BYTES,
    }
    assert validate_scene_limits(SceneCounts(**values)).model_dump() == values

    values[measure] = limit + 1
    with pytest.raises(SceneContractError, match="exceeds limit") as error:
        validate_scene_limits(SceneCounts(**values))
    assert error.value.code == "scene_limit_exceeded"
    assert error.value.details == {"measure": measure, "actual": limit + 1, "limit": limit}


def test_scene_contract_error_has_stable_structured_payload() -> None:
    error = SceneContractError(
        "invalid_scene_request",
        "Three distinct axes are required.",
        details={"field_id": "temperature"},
    )

    assert error.as_payload() == {
        "code": "invalid_scene_request",
        "message": "Three distinct axes are required.",
        "details": {"field_id": "temperature"},
    }


def test_scene_contract_import_is_lightweight() -> None:
    script = """
import json
import sys
import carnopy.app.scene_contracts
blocked = [
    name for name in ("numpy", "pandas", "pyarrow", "CoolProp", "matplotlib", "vtk")
    if name in sys.modules
]
print(json.dumps(blocked))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == "[]"
