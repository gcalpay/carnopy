from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from carnopy.app.scene_contracts import (
    CategoricalSetFilter,
    NumericRangeFilter,
    SceneBoundTable,
    SceneContractError,
    SceneFieldProfile,
    SceneFileIdentity,
    SceneProfile,
    SceneSelectionDefaults,
    SceneSourceBinding,
    SceneTopologyAxis,
    SceneTopologyEvidence,
)
from carnopy.app.scene_draft import SceneDraft


@pytest.fixture(scope="module")
def application() -> QApplication:
    existing = QApplication.instance()
    return existing if isinstance(existing, QApplication) else QApplication([])


def _identity(path: str, *, sha256: str = "a" * 64) -> SceneFileIdentity:
    return SceneFileIdentity(
        path=path,
        sha256=sha256,
        device=10,
        inode=20,
        size=30,
        modified_ns=40,
    )


def _binding(*, revision: str = "b" * 64) -> SceneSourceBinding:
    return SceneSourceBinding(
        source_path="/workspace/run",
        source_kind="dataset",
        inspection_revision=revision,
        selected_table_id="dataset",
        tables=(
            SceneBoundTable(
                table_id="dataset",
                label="Dataset",
                source_format="parquet",
                artifact=_identity("/workspace/run/dataset.parquet"),
                metadata=_identity(
                    "/workspace/run/metadata.json",
                    sha256="c" * 64,
                ),
            ),
        ),
    )


def _numeric_field(
    field_id: str,
    column: str,
    label: str,
    unit: str,
    minimum: float,
    maximum: float,
    *,
    classification: str = "source_coordinate",
) -> SceneFieldProfile:
    return SceneFieldProfile(
        field_id=field_id,
        column=column,
        label=label,
        dtype="float64",
        kind="numeric",
        classification=classification,
        origin="table",
        unit=unit,
        unit_status="canonical",
        source_row_count=5,
        source_valid_count=5,
        value_count=5,
        missing_count=0,
        finite_count=5,
        minimum=minimum,
        maximum=maximum,
        varying=minimum != maximum,
        positive_domain=minimum > 0.0,
        axis_eligible=True,
        scalar_eligible=True,
        filter_kind="numeric_range",
    )


def _fields() -> tuple[SceneFieldProfile, ...]:
    return (
        _numeric_field("temperature", "temperature_K", "Temperature", "K", 300.0, 320.0),
        _numeric_field("pressure", "pressure_Pa", "Pressure", "Pa", 100_000.0, 250_000.0),
        _numeric_field(
            "specific_enthalpy",
            "specific_enthalpy_J_kg",
            "Specific enthalpy",
            "J/kg",
            240_000.0,
            430_000.0,
            classification="emitted_property",
        ),
        _numeric_field(
            "mass_density",
            "mass_density_kg_m3",
            "Mass density",
            "kg/m^3",
            2.0,
            12.0,
            classification="emitted_property",
        ),
        _numeric_field("constant", "constant", "Constant", "1", 1.0, 1.0),
        SceneFieldProfile(
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
            source_valid_count=5,
            value_count=5,
            missing_count=0,
            distinct_values=("gas", "liquid"),
            varying=True,
            axis_eligible=False,
            scalar_eligible=False,
            filter_kind="categorical_set",
            ineligible_reason="categorical fields cannot be scene coordinates or scalars",
        ),
    )


def _profile(
    *,
    binding: SceneSourceBinding | None = None,
    defaults: SceneSelectionDefaults | None = None,
    build_eligible: bool = True,
    ineligible_reason: str = "",
) -> SceneProfile:
    selected_binding = _binding() if binding is None else binding
    return SceneProfile(
        binding=selected_binding,
        source_row_count=5,
        fields=_fields(),
        topology=SceneTopologyEvidence(
            status="exact",
            axes=(
                SceneTopologyAxis(
                    field_id="temperature",
                    source_column="temperature_K",
                    unit="K",
                    levels=(320.0, 300.0),
                ),
                SceneTopologyAxis(
                    field_id="pressure",
                    source_column="pressure_Pa",
                    unit="Pa",
                    levels=(100_000.0, 250_000.0),
                ),
            ),
            context_fields=("fluid", "phase"),
        ),
        defaults=defaults
        or SceneSelectionDefaults(
            x_field="temperature",
            y_field="pressure",
            z_field="specific_enthalpy",
            scalar_field="mass_density",
        ),
        build_eligible=build_eligible,
        ineligible_reason=ineligible_reason,
    )


def _profiled_draft(application: QApplication) -> SceneDraft:
    del application
    draft = SceneDraft()
    assert draft.copy_binding(_binding())
    assert draft.accept_profile(_profile().model_dump(mode="json"))
    return draft


def test_binding_copy_and_profile_command_are_explicit_immutable_snapshots(
    application: QApplication,
) -> None:
    del application
    draft = SceneDraft()
    binding = _binding()

    assert draft.copy_binding(binding)
    copied = draft.binding_snapshot()
    submission = draft.create_profile_submission()

    assert copied == binding
    assert copied is not binding
    assert copied is not None and copied.tables[0] is not binding.tables[0]
    assert submission.binding == binding
    assert submission.binding is not copied
    assert submission.worker_payload() == {"binding": binding.model_dump(mode="json")}
    assert draft.get_can_profile()
    assert not draft.get_profile_available()
    assert not draft.get_can_build()
    assert "Profile" in draft.get_issue()

    replacement = _binding(revision="d" * 64)
    assert draft.copy_binding(replacement)
    assert submission.binding == binding
    assert draft.binding_snapshot() == replacement
    assert not draft.get_profile_available()


def test_profile_applies_exact_topology_first_defaults_and_qml_safe_models(
    application: QApplication,
) -> None:
    draft = _profiled_draft(application)

    assert (
        draft.get_x_field(),
        draft.get_y_field(),
        draft.get_z_field(),
        draft.get_scalar_field(),
    ) == ("temperature", "pressure", "specific_enthalpy", "mass_density")
    assert draft.get_topology_status() == "exact"
    assert draft.get_topology_axis_fields() == ["temperature", "pressure"]
    assert draft.get_locally_valid()
    assert draft.get_can_build()
    assert draft.get_request_id().startswith("scene-")

    axis_items = {item.value: item for item in draft.axis_choices.items}
    scalar_items = {item.value: item for item in draft.scalar_choices.items}
    assert axis_items["temperature"].selected
    assert axis_items["phase"].compatible is False
    assert "categorical" in axis_items["phase"].issue
    assert axis_items["constant"].compatible is True
    assert "no varying" in axis_items["constant"].issue
    assert scalar_items["mass_density"].selected
    assert scalar_items[""].display == "None"

    filter_rows = {row["fieldId"]: row for row in draft.filter_rows.rows()}
    assert filter_rows["phase"]["availableValues"] == ["gas", "liquid"]
    assert filter_rows["phase"]["caseSensitive"] is True
    assert filter_rows["phase"]["active"] is False
    assert filter_rows["temperature"]["inclusive"] is True
    assert filter_rows["temperature"]["sourceMinimum"] == 300.0


def test_scene_edits_create_only_canonical_requests_when_explicitly_submitted(
    application: QApplication,
) -> None:
    draft = _profiled_draft(application)
    original_id = draft.get_request_id()
    messages: list[str] = []
    draft.message.connect(messages.append)

    assert draft.set_scalar_field("temperature")
    assert draft.set_categorical_filter("phase", ["liquid", "gas", "gas"])
    assert draft.set_numeric_filter("temperature", 300.0, 320.0)
    submission = draft.create_build_submission()

    assert submission.request.scalar_field == "temperature"
    assert submission.request.filters == (
        CategoricalSetFilter(field_id="phase", values=("gas", "liquid")),
        NumericRangeFilter(field_id="temperature", minimum=300.0, maximum=320.0),
    )
    assert submission.request_id == draft.get_request_id()
    assert submission.request_id != original_id
    assert submission.profile is not draft.profile_snapshot()

    submitted_request = submission.request
    assert draft.set_z_field("mass_density")
    assert submitted_request.z_field == "specific_enthalpy"
    assert draft.request_snapshot().z_field == "mass_density"

    before = draft.filters_snapshot()
    assert not draft.set_categorical_filter("phase", ["Gas"])
    assert not draft.set_numeric_filter("temperature", float("inf"), None)
    assert not draft.set_numeric_filter("temperature", True, None)
    assert draft.filters_snapshot() == before
    assert "unobserved exact" in messages[-3]
    assert messages[-2:]


def test_incomplete_or_duplicate_coordinates_never_gain_implicit_repair(
    application: QApplication,
) -> None:
    del application
    draft = SceneDraft()
    draft.copy_binding(_binding())
    profile = _profile(
        defaults=SceneSelectionDefaults(
            x_field="temperature",
            y_field="pressure",
            z_field=None,
            scalar_field="mass_density",
        )
    )

    assert draft.accept_profile(profile)
    assert draft.get_z_field() == ""
    assert not draft.get_locally_valid()
    assert "Z" in draft.get_issue()
    with pytest.raises(SceneContractError, match="Choose explicit"):
        draft.create_build_submission()

    assert draft.set_z_field("temperature")
    assert "distinct" in draft.get_issue()
    with pytest.raises(SceneContractError, match="distinct"):
        draft.create_build_submission()

    assert draft.set_z_field("specific_enthalpy")
    assert draft.get_locally_valid()
    assert not draft.set_x_field("phase")
    assert draft.get_x_field() == "temperature"


def test_profile_mismatch_or_ineligibility_is_explicit_and_non_destructive(
    application: QApplication,
) -> None:
    draft = _profiled_draft(application)
    accepted = draft.profile_snapshot()
    request = draft.request_snapshot()

    with pytest.raises(SceneContractError, match="binding disagrees"):
        draft.accept_profile(_profile(binding=_binding(revision="e" * 64)))

    assert draft.profile_snapshot() == accepted
    assert draft.request_snapshot() == request

    ineligible = _profile(
        build_eligible=False,
        ineligible_reason="the selected source has insufficient finite numeric fields",
    )
    assert draft.accept_profile(ineligible)
    assert draft.get_profile_available()
    assert not draft.get_can_build()
    assert draft.get_issue() == "the selected source has insufficient finite numeric fields"
    with pytest.raises(SceneContractError) as error:
        draft.create_build_submission()
    assert error.value.code == "invalid_scene_profile"


def test_filter_reset_and_new_binding_are_explicit_state_transitions(
    application: QApplication,
) -> None:
    draft = _profiled_draft(application)
    assert draft.set_numeric_filter("pressure", None, 200_000.0)
    assert draft.set_y_field("mass_density")
    assert draft.get_has_filters()

    assert draft.reset_to_profile_defaults()
    assert not draft.get_has_filters()
    assert draft.get_y_field() == "pressure"
    assert not draft.reset_to_profile_defaults()
    assert not draft.copy_binding(_binding())
    assert draft.get_profile_available()

    assert draft.copy_binding(_binding(revision="f" * 64))
    assert not draft.get_profile_available()
    assert draft.get_x_field() == ""
    assert draft.filters_snapshot() == ()
    assert draft.clear()
    assert not draft.get_binding_available()
    assert not draft.clear()


def test_scene_draft_import_and_edits_do_not_load_workers_or_heavy_modules() -> None:
    script = """
import sys
from PySide6.QtCore import QCoreApplication
from carnopy.app.scene_draft import SceneDraft

application = QCoreApplication.instance() or QCoreApplication([])
draft = SceneDraft()
blocked = (
    "CoolProp", "numpy", "pandas", "pyarrow", "matplotlib", "vtk",
    "carnopy.app.worker", "carnopy.app.request_coordinator", "carnopy.app.scene_build",
)
loaded = sorted(name for name in blocked if name in sys.modules)
raise SystemExit("unexpected imports: " + ", ".join(loaded) if loaded else 0)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
