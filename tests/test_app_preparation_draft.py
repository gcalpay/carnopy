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
        "numeric_candidates": numeric,
        "target_candidates": list(numeric),
        "categorical_candidates": [_field("phase"), _field("fluid")],
        "auxiliary_candidates": [_field(name) for name in auxiliary_names],
        "observed_category_values": {
            "phase": ["gas", "liquid"],
            "fluid": ["Propane"],
        },
        "derived_features": derived,
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
