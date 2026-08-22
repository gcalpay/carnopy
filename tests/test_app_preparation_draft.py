from __future__ import annotations

import os
from typing import Any, cast

import pytest
import yaml

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from carnopy.app.preparation_draft import PreparationDraft
from carnopy.preparation.models import PreparationConfig
from carnopy.templates import template_text


def _payload() -> dict[str, Any]:
    value = yaml.safe_load(template_text(cast(Any, "preparation")))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _normalized(payload: dict[str, Any]) -> dict[str, Any]:
    return PreparationConfig.model_validate(payload).model_dump(
        mode="json",
        exclude_none=True,
    )


def _field(name: str, *, reference_dependent: bool = False) -> dict[str, object]:
    return {
        "name": name,
        "column": f"{name}_column",
        "unit": "K" if name == "temperature" else None,
        "source": "property",
        "reference_dependent": reference_dependent,
    }


def _profile(*, complete: bool = True) -> dict[str, object]:
    numeric_names = (
        ["temperature", "pressure", "mass_density", "specific_enthalpy"]
        if complete
        else ["pressure", "specific_enthalpy"]
    )
    derived = [
        {
            "name": name,
            "status": "ready" if complete or name != "specific_volume" else "unavailable",
            "available": complete or name != "specific_volume",
            "reason": (
                "Density is unavailable in this source."
                if not complete and name == "specific_volume"
                else ""
            ),
            "unit": "1",
        }
        for name in (
            "specific_volume",
            "reduced_temperature",
            "reduced_pressure",
            "compressibility_factor",
        )
    ]
    auxiliary_names = (
        ["fluid", "backend_model", "phase", "run_id", "case_id"] if complete else ["fluid"]
    )
    numeric = [
        _field(name, reference_dependent=name == "specific_enthalpy") for name in numeric_names
    ]
    return {
        "source_kind": "dataset_run",
        "completion": {"status": "completed", "partial": False},
        "available_models": ["heos"],
        "numeric_candidates": numeric,
        "target_candidates": list(numeric),
        "categorical_candidates": [_field("phase"), _field("fluid")],
        "auxiliary_candidates": [_field(name) for name in auxiliary_names],
        "observed_category_values": {
            "phase": ["gas", "liquid"],
            "fluid": ["Propane"],
        },
        "derived_features": derived,
        "model_holdout": {
            "available": False,
            "reason": "Model holdout scenarios require a model-sweep source.",
        },
        "reference_context": {"compatible": True, "reason": ""},
    }


def _capabilities(
    *,
    safetensors: bool,
    analysis: bool,
) -> dict[str, object]:
    return {
        "workflows": {
            "preparation": {
                "safetensors": {
                    "available": safetensors,
                    "guidance": "install ml",
                },
                "baseline_diagnostics": {
                    "available": analysis,
                    "guidance": "install analysis",
                },
            }
        }
    }


def test_preparation_role_draft_round_trips_and_preserves_deferred_sections() -> None:
    payload = _payload()
    payload["scenarios"] = [{"name": "all", "kind": "unsplit"}]
    payload["quality"] = {
        "matrix_diagnostics": {
            "correlation_threshold": 0.99,
            "near_constant_relative_spread": 1e-10,
        }
    }
    payload["outputs"] = {
        "formats": ["parquet"],
        "parquet": True,
        "arrays": {
            "formats": ["npy", "npz"],
            "dtype": "float64",
            "include_auxiliary": True,
        },
    }
    expected = _normalized(payload)
    draft = PreparationDraft()

    draft.load_payload(payload)

    assert draft.get_locally_valid()
    assert not draft.get_dirty()
    assert draft.payload() == expected
    assert draft.payload()["scenarios"] == expected["scenarios"]
    assert draft.payload()["quality"] == expected["quality"]
    assert draft.payload()["outputs"] == expected["outputs"]


def test_preparation_role_edits_are_explicit_ordered_and_dirty() -> None:
    draft = PreparationDraft()
    draft.load_payload(_payload())
    messages: list[str] = []
    draft.message.connect(messages.append)

    assert not draft.set_role_selected("target", "temperature", True)
    assert messages == ["Already selected for an incompatible Preparation role."]
    assert draft.set_role_selected("numeric", "temperature", False)
    assert draft.set_role_selected("target", "temperature", True)
    assert draft.set_role_selected("auxiliary", "case_id", False)
    assert draft.set_allow_partial_sweep(True)
    assert draft.set_category_mode("phase", "explicit")
    assert draft.set_explicit_categories("phase", "gas, liquid")
    assert not draft.set_explicit_categories("phase", "gas, gas")
    assert messages[-1] == "Explicit categories must be unique."
    assert not draft.set_explicit_categories("phase", "gas, , liquid")
    assert messages[-1] == "Explicit categories must not contain blank values."
    assert draft.explicit_categories_text("phase") == "gas, liquid"
    assert not draft.set_category_mode("phase", "observed")
    assert "Confirm replacing" in messages[-1]
    assert draft.set_category_mode("phase", "observed", True)

    value = draft.payload()
    assert value["source_policy"] == {"allow_partial_sweep": True}
    assert value["features"]["numeric"] == ["pressure", "mass_density"]
    assert value["targets"] == ["specific_enthalpy", "temperature"]
    assert value["auxiliary"] == ["fluid", "backend_model", "phase", "run_id"]
    assert value["categorical_features"][0]["categories"] == "observed"
    assert draft.observed_categories("phase") == []
    assert draft.get_dirty()
    draft.mark_baseline()
    assert not draft.get_dirty()


def test_source_profile_updates_choices_without_dirtying_or_rewriting_yaml() -> None:
    draft = PreparationDraft()
    draft.load_payload(_payload())
    baseline = draft.payload()
    changes: list[str] = []
    profiles: list[str] = []
    draft.changed.connect(lambda: changes.append("changed"))
    draft.profile_changed.connect(lambda: profiles.append("profile"))

    assert draft.apply_source_profile(_profile(complete=False))

    assert changes == []
    assert profiles == ["profile"]
    assert draft.payload() == baseline
    assert not draft.get_dirty()
    assert draft.get_locally_valid()
    assert "temperature" in draft.get_source_issue()
    temperature = next(item for item in draft.numeric_choices.items if item.value == "temperature")
    volume = next(item for item in draft.derived_choices.items if item.value == "specific_volume")
    assert temperature.selected and not temperature.compatible
    assert volume.selected and not volume.compatible
    assert not draft.set_role_selected("numeric", "mass_density", True)
    assert draft.payload() == baseline
    assert not draft.apply_source_profile(_profile(complete=False))
    assert profiles == ["profile"]


def test_profile_candidates_expose_roles_categories_and_reference_context() -> None:
    draft = PreparationDraft()
    draft.load_payload(_payload())
    profile = _profile()
    draft.apply_source_profile(profile)

    assert draft.get_profile_available()
    assert draft.get_source_kind() == "dataset_run"
    assert draft.get_source_issue() == ""
    assert draft.observed_categories("phase") == ["gas", "liquid"]
    temperature = next(item for item in draft.numeric_choices.items if item.value == "temperature")
    assert temperature.label == "temperature_column"
    assert temperature.unit == "K"
    assert all(item.compatible for item in draft.categorical_choices.items)

    incompatible = dict(profile)
    incompatible["reference_context"] = {
        "compatible": False,
        "reason": "Reference contexts disagree.",
    }
    draft.apply_source_profile(incompatible)
    assert draft.get_source_issue() == "Reference contexts disagree."


def test_partial_sweep_policy_is_source_blocking_but_remains_saveable_yaml() -> None:
    draft = PreparationDraft()
    draft.load_payload(_payload())
    profile = _profile()
    profile["source_kind"] = "model_sweep"
    profile["completion"] = {"status": "partial", "partial": True}

    draft.apply_source_profile(profile)

    assert "partial" in draft.get_source_issue().casefold()
    assert draft.get_locally_valid()
    assert not draft.get_dirty()
    assert draft.set_allow_partial_sweep(True)
    assert draft.get_source_issue() == ""
    assert draft.get_locally_valid()
    assert draft.get_dirty()


def test_invalid_local_roles_keep_raw_dirty_state_and_stable_focus() -> None:
    draft = PreparationDraft()
    draft.load_payload(_payload())

    assert draft.set_role_selected("target", "specific_enthalpy", False)
    assert not draft.get_locally_valid()
    assert draft.get_dirty()
    assert draft.get_first_invalid_field() == "preparation.targets"
    with pytest.raises(ValueError, match="invalid ML Preparation draft"):
        draft.mark_baseline()

    assert draft.set_role_selected("target", "specific_enthalpy", True)
    assert draft.get_locally_valid()
    assert not draft.get_dirty()


def test_clear_removes_document_state_but_retains_source_projection() -> None:
    draft = PreparationDraft()
    draft.apply_source_profile(_profile())
    draft.load_payload(_payload())

    draft.clear()

    assert not draft.get_locally_valid()
    assert not draft.get_dirty()
    assert draft.get_profile_available()
    assert draft.get_source_kind() == "dataset_run"


def test_committed_scenarios_round_trip_with_concise_ordered_summaries() -> None:
    payload = _payload()
    payload["scenarios"] = [
        {"name": "all", "kind": "unsplit"},
        {
            "name": "random",
            "kind": "shuffle",
            "seed": 42,
            "partitions": {"test": 0.15, "train": 0.7, "validation": 0.15},
        },
        {
            "name": "fluid-test",
            "kind": "leave_fluid_out",
            "holdouts": {"test": ["Propane"]},
            "remainder": "train",
            "transformations": [{"field": "pressure", "methods": ["standard"]}],
        },
    ]
    draft = PreparationDraft()

    draft.load_payload(payload)

    assert draft.scenarios_model.rows() == (
        {"name": "all", "kind": "unsplit", "summary": "Unsplit · All partition"},
        {
            "name": "random",
            "kind": "shuffle",
            "summary": ("Shuffle · Train 70% · Validation 15% · Test 15% · Seed 42"),
        },
        {
            "name": "fluid-test",
            "kind": "leave_fluid_out",
            "summary": "Leave Fluid Out · Holdouts Test · 1 transformation",
        },
    )
    assert draft.scenario_payloads() == tuple(_normalized(payload)["scenarios"])
    assert draft.payload() == _normalized(payload)
    assert not draft.get_dirty()


def test_scenario_editor_is_transient_until_explicit_commit_or_cancel() -> None:
    draft = PreparationDraft()
    draft.load_payload(_payload())
    committed = draft.payload()
    document_changes: list[str] = []
    dirty_changes: list[str] = []
    active_changes: list[str] = []
    messages: list[str] = []
    draft.changed.connect(lambda: document_changes.append("changed"))
    draft.dirty_changed.connect(lambda: dirty_changes.append("dirty"))
    draft.active_scenario_draft_changed.connect(lambda: active_changes.append("active"))
    draft.message.connect(messages.append)

    assert draft.begin_add_scenario()
    assert draft.get_has_active_scenario_edit()
    assert draft.get_active_scenario_row() == -1
    assert active_changes == ["active"]
    active = draft.get_active_scenario_draft()
    assert active is not None
    assert active.set_name("not a slug")
    assert draft.payload() == committed
    assert not draft.get_dirty()
    assert document_changes == []
    assert dirty_changes == []

    assert not draft.commit_scenario()
    assert messages and "safe slugs" in messages[-1]
    assert draft.get_has_active_scenario_edit()
    assert active.set_name("evaluation")
    assert draft.commit_scenario()
    assert not draft.get_has_active_scenario_edit()
    assert active_changes == ["active", "active"]
    assert document_changes == ["changed"]
    assert dirty_changes == ["dirty"]
    assert draft.get_dirty()
    assert [item["name"] for item in draft.scenario_payloads()] == ["evaluation"]

    draft.mark_baseline()
    document_changes.clear()
    dirty_changes.clear()
    assert draft.begin_edit_scenario(0)
    active = draft.get_active_scenario_draft()
    assert active is not None
    assert active.set_name("temporary")
    assert not draft.get_dirty()
    assert draft.cancel_scenario()
    assert document_changes == []
    assert dirty_changes == []
    assert not draft.get_dirty()
    assert draft.scenario_payloads()[0]["name"] == "evaluation"


def test_identical_scenario_commit_closes_editor_without_dirtying_document() -> None:
    payload = _payload()
    payload["scenarios"] = [{"name": "all", "kind": "unsplit"}]
    draft = PreparationDraft()
    draft.load_payload(payload)
    document_changes: list[str] = []
    draft.changed.connect(lambda: document_changes.append("changed"))

    assert draft.begin_edit_scenario(0)
    assert draft.commit_scenario()

    assert not draft.get_has_active_scenario_edit()
    assert not draft.get_dirty()
    assert document_changes == []


def test_scenario_names_order_and_removal_are_committed_deterministically() -> None:
    payload = _payload()
    payload["scenarios"] = [
        {"name": "all", "kind": "unsplit"},
        {
            "name": "random",
            "kind": "shuffle",
            "seed": 42,
            "partitions": {"train": 0.8, "test": 0.2},
        },
    ]
    draft = PreparationDraft()
    draft.load_payload(payload)
    messages: list[str] = []
    draft.message.connect(messages.append)

    assert draft.begin_edit_scenario(0)
    active = draft.get_active_scenario_draft()
    assert active is not None
    assert active.set_name("random")
    assert not draft.commit_scenario()
    assert messages[-1] == "Preparation scenario names must be unique."
    assert draft.get_has_active_scenario_edit()
    assert not draft.remove_scenario(1)
    assert not draft.move_scenario(0, 1)
    assert draft.cancel_scenario()

    assert draft.move_scenario(1, 0)
    assert [item["name"] for item in draft.payload()["scenarios"]] == ["random", "all"]
    assert draft.remove_scenario(1)
    assert [item["name"] for item in draft.scenario_payloads()] == ["random"]
    assert draft.get_dirty()


def test_source_profile_refreshes_active_scenario_choices_without_document_change() -> None:
    draft = PreparationDraft()
    draft.load_payload(_payload())
    assert draft.begin_add_scenario()
    active = draft.get_active_scenario_draft()
    assert active is not None
    baseline = draft.payload()
    document_changes: list[str] = []
    draft.changed.connect(lambda: document_changes.append("changed"))
    profile = _profile()
    numeric = list(cast(list[dict[str, object]], profile["numeric_candidates"]))
    numeric.append(_field("source_only_numeric"))
    profile["numeric_candidates"] = numeric

    assert draft.apply_source_profile(profile)

    assert "source_only_numeric" in active.get_field_choices()
    assert draft.payload() == baseline
    assert not draft.get_dirty()
    assert document_changes == []


def test_clear_discards_active_scenario_without_committing_it() -> None:
    draft = PreparationDraft()
    draft.load_payload(_payload())
    active_changes: list[str] = []
    draft.active_scenario_draft_changed.connect(lambda: active_changes.append("active"))
    assert draft.begin_add_scenario()
    active = draft.get_active_scenario_draft()
    assert active is not None
    assert active.set_name("temporary")

    draft.clear()

    assert not draft.get_has_active_scenario_edit()
    assert draft.scenario_payloads() == ()
    assert active_changes == ["active", "active"]


def test_model_holdout_requires_compatible_bound_sweep_source_for_new_commit() -> None:
    draft = PreparationDraft()
    draft.load_payload(_payload())
    draft.apply_source_profile(_profile())
    messages: list[str] = []
    draft.message.connect(messages.append)

    assert not draft.get_model_holdout_available()
    assert "model-sweep source" in draft.get_model_holdout_issue().casefold()
    assert draft.begin_add_scenario()
    active = draft.get_active_scenario_draft()
    assert active is not None
    assert active.set_name("model-test")
    assert active.request_kind_change("model_holdout")
    assert active.set_categorical_holdout("test", "pr")

    assert not draft.commit_scenario()
    assert messages[-1] == "Model holdout scenarios require a model-sweep source."
    assert draft.get_has_active_scenario_edit()
    assert draft.scenario_payloads() == ()

    sweep_profile = _profile()
    sweep_profile["source_kind"] = "model_sweep"
    sweep_profile["available_models"] = ["heos", "pr"]
    sweep_profile["model_holdout"] = {"available": True, "reason": ""}
    assert draft.apply_source_profile(sweep_profile)
    assert draft.get_model_holdout_available()
    assert draft.commit_scenario()
    assert draft.get_source_issue() == ""
    assert draft.scenario_payloads()[0]["kind"] == "model_holdout"


def test_imported_source_incompatible_scenarios_remain_clean_and_blocking() -> None:
    payload = _payload()
    payload["scenarios"] = [
        {
            "name": "model-test",
            "kind": "model_holdout",
            "holdouts": {"test": ["pr"]},
            "remainder": "train",
        },
        {
            "name": "fluid-test",
            "kind": "leave_fluid_out",
            "holdouts": {"test": ["n-Butane"]},
            "remainder": "train",
        },
    ]
    draft = PreparationDraft()
    draft.load_payload(payload)
    baseline = draft.payload()

    draft.apply_source_profile(_profile())

    assert "model-sweep source" in draft.get_source_issue().casefold()
    assert draft.payload() == baseline
    assert not draft.get_dirty()
    assert draft.begin_edit_scenario(0)
    assert draft.commit_scenario()
    assert not draft.get_has_active_scenario_edit()
    assert not draft.get_dirty()


@pytest.mark.parametrize(
    ("kind", "value", "expected_label"),
    [
        ("leave_fluid_out", "n-Butane", "fluid"),
        ("phase_holdout", "supercritical", "phase"),
    ],
)
def test_imported_unobserved_categorical_holdouts_remain_clean_and_blocking(
    kind: str,
    value: str,
    expected_label: str,
) -> None:
    payload = _payload()
    payload["scenarios"] = [
        {
            "name": "categorical-test",
            "kind": kind,
            "holdouts": {"test": [value]},
            "remainder": "train",
        }
    ]
    draft = PreparationDraft()
    draft.load_payload(payload)
    baseline = draft.payload()

    draft.apply_source_profile(_profile())

    issue = draft.get_source_issue()
    assert expected_label in issue.casefold()
    assert value in issue
    assert draft.payload() == baseline
    assert not draft.get_dirty()


def test_unavailable_bound_holdout_values_are_rejected_without_mutation() -> None:
    draft = PreparationDraft()
    draft.load_payload(_payload())
    sweep_profile = _profile()
    sweep_profile["source_kind"] = "model_sweep"
    sweep_profile["available_models"] = ["heos", "pr"]
    sweep_profile["model_holdout"] = {"available": True, "reason": ""}
    draft.apply_source_profile(sweep_profile)
    messages: list[str] = []
    draft.message.connect(messages.append)
    assert draft.begin_add_scenario()
    active = draft.get_active_scenario_draft()
    assert active is not None
    assert active.set_name("missing-model")
    assert active.request_kind_change("model_holdout")
    assert active.set_categorical_holdout("test", "srk")

    assert not draft.commit_scenario()

    assert "unavailable backend model holdout values: srk" in messages[-1].casefold()
    assert draft.scenario_payloads() == ()
    assert draft.get_has_active_scenario_edit()


def test_preparation_output_and_quality_settings_round_trip_completely() -> None:
    draft = PreparationDraft()
    draft.apply_capabilities(_capabilities(safetensors=True, analysis=True))
    draft.load_payload(_payload())

    assert draft.set_array_outputs_enabled(True)
    assert draft.set_array_format_selected("npy", True)
    assert draft.set_array_format_selected("safetensors", True)
    assert draft.set_array_dtype("float64")
    assert draft.set_include_auxiliary(True)
    assert draft.set_matrix_enabled(True)
    assert draft.set_correlation_threshold("0.98")
    assert draft.set_near_constant_spread("2e-10")
    assert draft.set_baseline_enabled(True)
    assert draft.set_baseline_model_selected("hist_gradient_boosting", True)
    assert draft.set_baseline_seed("7")
    assert draft.set_ridge_alpha("0.25")
    assert draft.set_histogram_iterations("250")

    value = draft.payload()
    assert value["outputs"] == {
        "formats": ["parquet"],
        "parquet": True,
        "arrays": {
            "formats": ["npy", "npz", "safetensors"],
            "dtype": "float64",
            "include_auxiliary": True,
        },
    }
    assert value["quality"] == {
        "matrix_diagnostics": {
            "correlation_threshold": 0.98,
            "near_constant_relative_spread": 2e-10,
        },
        "baseline_diagnostics": {
            "models": ["dummy_mean", "ridge", "hist_gradient_boosting"],
            "random_seed": 7,
            "ridge_alpha": 0.25,
            "histogram_max_iterations": 250,
        },
    }
    assert draft.get_dependency_issue() == ""
    assert draft.get_dirty()

    reloaded = PreparationDraft()
    reloaded.apply_capabilities(_capabilities(safetensors=True, analysis=True))
    reloaded.load_payload(value)
    assert reloaded.payload() == value
    assert not reloaded.get_dirty()


def test_imported_unavailable_optional_requests_remain_visible_and_saveable() -> None:
    payload = _payload()
    payload["outputs"] = {
        "formats": ["parquet"],
        "arrays": {"formats": ["safetensors"], "dtype": "float32"},
    }
    payload["quality"] = {"baseline_diagnostics": {"models": ["ridge"]}}
    draft = PreparationDraft()
    draft.apply_capabilities(_capabilities(safetensors=False, analysis=False))
    dependency_notifications: list[str] = []
    draft.capability_changed.connect(lambda: dependency_notifications.append("dependency"))

    draft.load_payload(payload)

    assert dependency_notifications == ["dependency"]
    assert draft.get_locally_valid()
    assert not draft.get_dirty()
    assert draft.payload() == _normalized(payload)
    assert draft.get_dependency_issue() == "install ml"
    safetensors = next(
        item for item in draft.array_format_choices.items if item.value == "safetensors"
    )
    ridge = next(item for item in draft.baseline_model_choices.items if item.value == "ridge")
    assert safetensors.selected and not safetensors.compatible
    assert ridge.selected and not ridge.compatible

    assert draft.set_array_format_selected("safetensors", False)
    assert draft.get_dependency_issue() == "install analysis"
    assert draft.set_baseline_enabled(False)
    assert draft.get_dependency_issue() == ""
    assert draft.get_locally_valid()


def test_unavailable_optional_features_cannot_be_newly_selected() -> None:
    draft = PreparationDraft()
    draft.apply_capabilities(_capabilities(safetensors=False, analysis=False))
    draft.load_payload(_payload())
    messages: list[str] = []
    draft.message.connect(messages.append)

    assert not draft.get_baseline_available()
    assert draft.get_baseline_guidance() == "install analysis"
    assert not draft.set_array_format_selected("safetensors", True)
    assert messages == ["install ml"]
    assert not draft.set_baseline_enabled(True)
    assert messages == ["install ml", "install analysis"]
    assert draft.set_array_outputs_enabled(True)
    assert draft.payload()["outputs"]["arrays"]["formats"] == ["npz"]


def test_capability_refresh_changes_dependency_projection_without_dirtying_yaml() -> None:
    payload = _payload()
    payload["outputs"] = {
        "formats": ["parquet"],
        "arrays": {"formats": ["safetensors"], "dtype": "float32"},
    }
    draft = PreparationDraft()
    draft.apply_capabilities(_capabilities(safetensors=False, analysis=False))
    draft.load_payload(payload)
    baseline = draft.payload()
    changes: list[str] = []
    capabilities: list[str] = []
    draft.changed.connect(lambda: changes.append("changed"))
    draft.capability_changed.connect(lambda: capabilities.append("capability"))

    assert draft.apply_capabilities(_capabilities(safetensors=True, analysis=False))

    assert changes == []
    assert capabilities == ["capability"]
    assert draft.get_baseline_guidance() == "install analysis"
    assert draft.get_dependency_issue() == ""
    assert draft.payload() == baseline
    assert not draft.get_dirty()
    assert not draft.apply_capabilities(_capabilities(safetensors=True, analysis=False))


@pytest.mark.parametrize(
    ("setter", "value", "field"),
    [
        ("set_correlation_threshold", "1.1", "preparation.quality.matrix_diagnostics"),
        ("set_near_constant_spread", "0", "preparation.quality.matrix_diagnostics"),
        ("set_ridge_alpha", "nan", "preparation.quality.baseline_diagnostics"),
        ("set_histogram_iterations", "0", "preparation.quality.baseline_diagnostics"),
    ],
)
def test_invalid_quality_text_preserves_dirty_state_and_stable_focus(
    setter: str,
    value: str,
    field: str,
) -> None:
    payload = _payload()
    payload["quality"] = {
        "matrix_diagnostics": {},
        "baseline_diagnostics": {"models": ["dummy_mean", "ridge"]},
    }
    draft = PreparationDraft()
    draft.apply_capabilities(_capabilities(safetensors=True, analysis=True))
    draft.load_payload(payload)

    assert getattr(draft, setter)(value)
    assert not draft.get_locally_valid()
    assert draft.get_dirty()
    assert draft.get_first_invalid_field() == field
