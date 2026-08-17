from __future__ import annotations

import os
import subprocess
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from carnopy.app.scenario_draft import ScenarioDraft
from carnopy.preparation.models import ScenarioConfig

SCENARIOS = (
    {"name": "all", "kind": "unsplit"},
    {
        "name": "shuffle",
        "kind": "shuffle",
        "seed": 42,
        "partitions": {"train": 0.8, "test": 0.2},
    },
    {
        "name": "strata",
        "kind": "stratified_hash",
        "seed": 7,
        "partitions": {"train": 0.7, "validation": 0.1, "test": 0.2},
        "strata": {
            "categorical": ["phase"],
            "numeric_bins": {"temperature": [300.0]},
        },
    },
    {
        "name": "block",
        "kind": "coordinate_block",
        "holdouts": {"test": {"pressure": {"min": 1.0, "max": 2.0}}},
        "remainder": "train",
    },
    {
        "name": "range",
        "kind": "range_holdout",
        "field": "pressure",
        "holdouts": {"test": {"min": 1.0, "max": 2.0}},
        "remainder": "train",
    },
    {
        "name": "fluid",
        "kind": "leave_fluid_out",
        "holdouts": {"test": ["Propane"]},
        "remainder": "train",
    },
    {
        "name": "phase",
        "kind": "phase_holdout",
        "holdouts": {"test": ["gas"]},
        "remainder": "train",
    },
    {
        "name": "model",
        "kind": "model_holdout",
        "holdouts": {"test": ["pr"]},
        "remainder": "train",
        "transformations": [{"field": "pressure", "methods": ["log10", "standard"]}],
    },
)


def _normalized(payload: dict[str, object]) -> dict[str, object]:
    return ScenarioConfig.model_validate(payload).model_dump(
        mode="json",
        exclude_none=True,
    )


@pytest.mark.parametrize("payload", SCENARIOS)
def test_scenario_draft_round_trips_all_public_kinds(payload: dict[str, object]) -> None:
    draft = ScenarioDraft(field_choices=("temperature", "pressure"), payload=payload)

    assert draft.get_locally_valid()
    assert draft.payload() == _normalized(payload)


def test_scenario_models_project_nested_values_in_deterministic_order() -> None:
    draft = ScenarioDraft(payload=SCENARIOS[2])

    assert draft.partition_rows.rows() == (
        {"partition": "train", "ratio": 0.7},
        {"partition": "validation", "ratio": 0.1},
        {"partition": "test", "ratio": 0.2},
    )
    assert draft.strata_rows.rows() == ({"field": "phase"},)
    assert draft.numeric_bin_rows.rows() == (
        {
            "field": "temperature",
            "boundaries": [300.0],
            "summary": "300",
        },
    )

    holdout = ScenarioDraft(payload=SCENARIOS[3])
    assert holdout.holdout_rows.rows() == (
        {
            "partition": "test",
            "summary": "pressure: 1 … 2",
            "kind": "coordinate_block",
        },
    )


def test_kind_change_requires_confirmation_only_after_shape_state_exists() -> None:
    draft = ScenarioDraft()
    requests: list[str] = []
    draft.kind_change_requested.connect(requests.append)

    assert draft.request_kind_change("shuffle")
    assert draft.get_kind() == "shuffle"
    assert draft.get_seed_text() == "42"
    assert draft.partition_rows.rows() == (
        {"partition": "train", "ratio": 0.8},
        {"partition": "test", "ratio": 0.2},
    )

    assert not draft.request_kind_change("range_holdout")
    assert requests == ["range_holdout"]
    assert draft.get_kind() == "shuffle"
    assert not draft.apply_kind_change("range_holdout", False)
    assert draft.apply_kind_change("range_holdout", True)
    assert draft.get_kind() == "range_holdout"
    assert draft.get_seed_text() == "42"
    assert draft.get_remainder() == "train"
    assert draft.partition_rows.rows() == ()


def test_range_coordinate_and_categorical_holdout_editing() -> None:
    range_draft = ScenarioDraft(payload=SCENARIOS[4])
    assert range_draft.set_range_holdout("validation", "3", "4.5")
    assert not range_draft.set_range_holdout("validation", "5", "4")
    assert range_draft.remove_holdout("test")
    assert range_draft.payload()["holdouts"] == {"validation": {"min": 3.0, "max": 4.5}}

    block = ScenarioDraft(payload=SCENARIOS[3])
    assert block.set_coordinate_holdout("test", "temperature", "300", "320")
    assert block.remove_coordinate_field("test", "pressure")
    assert block.payload()["holdouts"] == {"test": {"temperature": {"min": 300.0, "max": 320.0}}}

    categorical = ScenarioDraft(payload=SCENARIOS[5])
    assert categorical.set_categorical_holdout("validation", "Butane, Isopentane")
    assert not categorical.set_categorical_holdout("validation", "Butane, Butane")
    assert categorical.payload()["holdouts"]["validation"] == [
        "Butane",
        "Isopentane",
    ]


def test_strata_and_transformations_preserve_order_and_reject_duplicates() -> None:
    draft = ScenarioDraft(payload=SCENARIOS[2])
    assert draft.set_strata_categorical("phase, fluid")
    assert not draft.set_strata_categorical("phase, phase")
    assert draft.set_numeric_bins("pressure", "100000, 200000, 300000")
    assert not draft.set_numeric_bins("pressure", "200000, 100000")

    assert draft.add_transformation("pressure", "log10, standard")
    assert draft.add_transformation("temperature", "robust")
    assert not draft.add_transformation("pressure", "log10, standard")
    assert not draft.add_transformation("pressure", "standard, standard")
    assert draft.move_transformation(1, 0)

    assert draft.payload()["transformations"] == [
        {"field": "temperature", "methods": ["robust"]},
        {"field": "pressure", "methods": ["log10", "standard"]},
    ]
    assert draft.remove_transformation(0)
    assert draft.transformation_rows.rows() == (
        {
            "field": "pressure",
            "methods": ["log10", "standard"],
            "summary": "pressure · log10 → standard",
        },
    )


def test_invalid_scalar_state_remains_visible_with_stable_focus() -> None:
    draft = ScenarioDraft(payload=SCENARIOS[1])

    assert draft.set_seed_text("not-an-integer")

    assert not draft.get_locally_valid()
    assert "integer" in draft.get_issue()
    assert draft.get_first_invalid_field() == "preparation.scenario.active.seed"
    assert draft.get_first_invalid_row() == -1

    assert draft.set_seed_text("42")
    assert draft.set_partition("train", "-0.2")
    assert not draft.get_locally_valid()
    assert draft.get_first_invalid_field() == "preparation.scenario.active.partitions"
    assert draft.get_first_invalid_row() == 0


def test_source_field_choices_do_not_mutate_or_hide_imported_configuration() -> None:
    draft = ScenarioDraft(
        field_choices=("temperature",),
        payload={
            "name": "legacy-range",
            "kind": "range_holdout",
            "field": "legacy_pressure",
            "holdouts": {"test": {"min": 1.0, "max": 2.0}},
            "remainder": "train",
            "transformations": [{"field": "legacy_density", "methods": ["standard"]}],
        },
    )
    changes: list[None] = []
    contexts: list[None] = []
    draft.changed.connect(lambda: changes.append(None))
    draft.field_choices_changed.connect(lambda: contexts.append(None))
    baseline = draft.payload()

    assert draft.get_field_choices() == [
        "temperature",
        "legacy_pressure",
        "legacy_density",
    ]
    assert draft.set_field_choices(("temperature", "mass_density"))
    assert changes == []
    assert contexts == [None]
    assert draft.payload() == baseline
    assert "legacy_pressure" in draft.get_field_choices()


def test_detached_payload_does_not_share_nested_scenario_state() -> None:
    draft = ScenarioDraft(payload=SCENARIOS[7])

    detached = draft.detached_payload()
    detached["holdouts"]["test"].append("srk")
    detached["transformations"][0]["methods"].append("robust")

    assert draft.payload() == _normalized(SCENARIOS[7])


def test_scenario_draft_import_is_qtcore_only_and_scientifically_isolated() -> None:
    code = """
import sys
import carnopy.app.scenario_draft
for name in (
    "PySide6.QtWidgets", "CoolProp", "numpy", "pandas", "pyarrow", "matplotlib",
    "carnopy.cli", "carnopy.pipeline", "carnopy.preparation.models",
    "carnopy.preparation.scenarios",
):
    if name in sys.modules:
        raise SystemExit(name)
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
