from __future__ import annotations

import os
import subprocess
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from carnopy.app.sampler_draft import SamplerDraft
from carnopy.sampling.canonical import canonical_sampler_key
from carnopy.sampling.models import (
    ExplicitSampler,
    GeomspaceSampler,
    LinspaceSampler,
    LogspaceSampler,
    StepspaceSampler,
)


@pytest.fixture(scope="module")
def application() -> QApplication:
    existing = QApplication.instance()
    return existing if isinstance(existing, QApplication) else QApplication([])


@pytest.mark.parametrize(
    ("payload", "target", "expected"),
    [
        (
            {"kind": "explicit", "values": [1.0, 2.0], "unit": "bar"},
            "Pa",
            ExplicitSampler(kind="explicit", values=[100_000.0, 200_000.0], unit="Pa"),
        ),
        (
            {"kind": "linspace", "start": 0.0, "stop": 100.0, "num": 5, "unit": "degC"},
            "K",
            LinspaceSampler(kind="linspace", start=273.15, stop=373.15, num=5, unit="K"),
        ),
        (
            {
                "kind": "stepspace",
                "start": 1.0,
                "stop": 3.0,
                "step": 1.0,
                "unit": "bar",
            },
            "kPa",
            StepspaceSampler(kind="stepspace", start=100.0, stop=300.0, step=100.0, unit="kPa"),
        ),
        (
            {"kind": "geomspace", "start": 1.0, "stop": 100.0, "num": 3, "unit": "bar"},
            "Pa",
            GeomspaceSampler(
                kind="geomspace", start=100_000.0, stop=10_000_000.0, num=3, unit="Pa"
            ),
        ),
        (
            {
                "kind": "logspace",
                "start_exp": 0.0,
                "stop_exp": 2.0,
                "num": 3,
                "base": 10.0,
                "unit": "bar",
            },
            "Pa",
            LogspaceSampler(
                kind="logspace",
                start_exp=5.0,
                stop_exp=7.0,
                num=3,
                base=10.0,
                unit="Pa",
            ),
        ),
    ],
)
def test_exact_unit_changes_preserve_canonical_sampler_key(
    application: QApplication,
    payload: dict[str, object],
    target: str,
    expected: object,
) -> None:
    del application
    axis = "temperature" if payload["unit"] == "degC" else "pressure"
    units = ["K", "degC"] if axis == "temperature" else ["Pa", "kPa", "MPa", "bar"]
    draft = SamplerDraft(axis)
    draft.load_payload(payload, available_units=units)
    anchor_key = canonical_sampler_key(axis, draft._sampler_model())

    assert draft.requestUnitChange(target)

    assert draft._sampler_model() == expected
    assert canonical_sampler_key(axis, draft._sampler_model()) == anchor_key


@pytest.mark.parametrize(
    ("payload", "target"),
    [
        (
            {"kind": "geomspace", "start": 280.0, "stop": 320.0, "num": 3, "unit": "K"},
            "degC",
        ),
        (
            {
                "kind": "logspace",
                "start_exp": 2.3,
                "stop_exp": 2.5,
                "num": 3,
                "base": 10.0,
                "unit": "K",
            },
            "degC",
        ),
    ],
)
def test_affine_geomspace_and_logspace_changes_are_atomic_refusals(
    application: QApplication,
    payload: dict[str, object],
    target: str,
) -> None:
    del application
    draft = SamplerDraft("temperature")
    draft.load_payload(payload, available_units=["K", "degC"])
    before = draft.raw_state()
    rejected: list[tuple[str, str]] = []
    draft.unitChangeRejected.connect(lambda field, message: rejected.append((field, message)))

    assert not draft.requestUnitChange(target)

    assert draft.raw_state() == before
    assert draft.get_valid()
    assert rejected[-1][0] == "dataset.grid.temperature.unit"
    assert "scale-only" in rejected[-1][1]


@pytest.mark.parametrize(
    ("axis", "payload", "units", "target"),
    [
        (
            "temperature",
            {"kind": "explicit", "values": [0.0072992700729927], "unit": "K"},
            ["K", "degC"],
            "degC",
        ),
        (
            "pressure",
            {
                "kind": "logspace",
                "start_exp": 0.123456789012345,
                "stop_exp": 2.23456789012345,
                "num": 5,
                "base": 7.0,
                "unit": "bar",
            },
            ["Pa", "kPa", "MPa", "bar"],
            "kPa",
        ),
    ],
)
def test_unrepresentable_exact_target_is_rejected_without_mutation(
    application: QApplication,
    axis: str,
    payload: dict[str, object],
    units: list[str],
    target: str,
) -> None:
    del application
    draft = SamplerDraft(axis)
    draft.load_payload(payload, available_units=units)
    before = draft.raw_state()
    changed: list[object] = []
    rejected: list[tuple[str, str]] = []
    draft.changed.connect(lambda: changed.append(object()))
    draft.unitChangeRejected.connect(lambda field, message: rejected.append((field, message)))

    assert not draft.requestUnitChange(target)

    assert draft.raw_state() == before
    assert draft.get_valid()
    assert changed == []
    assert rejected[-1][0] == f"dataset.grid.{axis}.unit"
    assert "canonical identity" in rejected[-1][1]


def test_anchor_survives_invalid_text_and_updates_after_valid_non_unit_edit(
    application: QApplication,
) -> None:
    del application
    draft = SamplerDraft("pressure")
    draft.load_payload(
        {"kind": "explicit", "values": [1.0, 2.0], "unit": "bar"},
        available_units=["Pa", "bar"],
    )

    draft.set_text("values", "")
    invalid_state = draft.raw_state()
    assert not draft.requestUnitChange("Pa")
    assert draft.raw_state() == invalid_state

    draft.set_text("values", "3, 4")
    new_anchor = canonical_sampler_key("pressure", draft._sampler_model())
    assert draft.requestUnitChange("Pa")
    assert canonical_sampler_key("pressure", draft._sampler_model()) == new_anchor
    assert draft.text("values") == "300000, 400000"


def test_repeated_toggles_derive_from_one_anchor_and_normalize_negative_zero(
    application: QApplication,
) -> None:
    del application
    draft = SamplerDraft("temperature")
    draft.load_payload(
        {"kind": "linspace", "start": -0.0, "stop": 100.0, "num": 5, "unit": "degC"},
        available_units=["K", "degC"],
    )
    anchor = draft.raw_state()

    assert draft.requestUnitChange("K")
    assert draft.requestUnitChange("degC")

    assert draft.raw_state() == anchor
    assert draft.text("start") == "0"


def test_exact_unit_change_uses_shortest_identity_preserving_text(
    application: QApplication,
) -> None:
    del application
    draft = SamplerDraft("pressure")
    draft.load_payload(
        {"kind": "explicit", "values": [101_325.0], "unit": "Pa"},
        available_units=["Pa", "bar"],
    )
    anchor_key = canonical_sampler_key("pressure", draft._sampler_model())

    assert draft.requestUnitChange("bar")

    assert draft.text("values") == "1.01325"
    assert canonical_sampler_key("pressure", draft._sampler_model()) == anchor_key


def test_sampler_reports_stable_invalid_field_without_message_parsing(
    application: QApplication,
) -> None:
    del application
    draft = SamplerDraft("pressure")
    draft.load_payload(
        {"kind": "linspace", "start": 1.0, "stop": 2.0, "num": 3, "unit": "bar"},
        available_units=["Pa", "bar"],
    )

    draft.set_text("stop", "not-a-number")

    assert not draft.get_valid()
    assert draft.get_first_invalid_field() == "dataset.grid.pressure.stop"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"kind": "explicit", "values": [1.0, 2.0, 3.0], "unit": "bar"}, 3),
        ({"kind": "linspace", "start": 1.0, "stop": 5.0, "num": 5, "unit": "bar"}, 5),
        (
            {"kind": "stepspace", "start": 1.0, "stop": 5.0, "step": 1.0, "unit": "bar"},
            5,
        ),
        ({"kind": "geomspace", "start": 1.0, "stop": 100.0, "num": 7, "unit": "bar"}, 7),
        (
            {
                "kind": "logspace",
                "start_exp": 0.0,
                "stop_exp": 2.0,
                "num": 9,
                "base": 10.0,
                "unit": "bar",
            },
            9,
        ),
    ],
)
def test_sampler_exposes_exact_lightweight_point_count(
    application: QApplication,
    payload: dict[str, object],
    expected: int,
) -> None:
    del application
    draft = SamplerDraft("pressure")
    draft.load_payload(payload, available_units=["Pa", "bar"])

    assert draft.get_valid()
    assert draft.get_sample_count() == expected


def test_sampler_exposes_inclusive_intervals_and_linspace_spacing(
    application: QApplication,
) -> None:
    del application
    draft = SamplerDraft("temperature")
    draft.load_payload(
        {"kind": "linspace", "start": -50.0, "stop": 50.0, "num": 101, "unit": "degC"},
        available_units=["K", "degC"],
    )

    assert draft.get_sample_count() == 101
    assert draft.get_interval_count() == 100
    assert draft.get_spacing_text() == "1"

    draft.set_text("num", "100")

    assert draft.get_sample_count() == 100
    assert draft.get_interval_count() == 99
    assert draft.get_spacing_text() == "1.01010101010101"

    draft.set_kind("stepspace")
    draft.set_text("step", "1")

    assert draft.get_valid()
    assert draft.get_sample_count() == 101
    assert draft.get_interval_count() == 100
    assert draft.get_spacing_text() == ""


def test_unreachable_stepspace_is_locally_invalid_without_materialization(
    application: QApplication,
) -> None:
    del application
    draft = SamplerDraft("pressure")
    draft.load_payload(
        {"kind": "stepspace", "start": 1.0, "stop": 2.0, "step": 0.3, "unit": "bar"},
        available_units=["Pa", "bar"],
    )

    assert not draft.get_valid()
    assert draft.get_sample_count() == 0
    assert draft.get_first_invalid_field() == "dataset.grid.pressure.step"
    assert "not reachable" in draft.get_issue()


def test_point_count_notifies_when_valid_count_changes(
    application: QApplication,
) -> None:
    del application
    draft = SamplerDraft("pressure")
    draft.load_payload(
        {"kind": "linspace", "start": 1.0, "stop": 5.0, "num": 5, "unit": "bar"},
        available_units=["Pa", "bar"],
    )
    observed: list[int] = []
    draft.sample_count_changed.connect(lambda: observed.append(draft.get_sample_count()))

    draft.set_text("num", "7")

    assert observed == [7]
    assert draft.get_valid()


def test_sampler_unit_change_import_stays_lightweight() -> None:
    code = """
import sys
from carnopy.app.sampler_draft import SamplerDraft
draft = SamplerDraft("pressure")
draft.load_payload(
    {"kind": "explicit", "values": [1.0], "unit": "bar"},
    available_units=["Pa", "bar"],
)
assert draft.sampleCount == 1
assert draft.requestUnitChange("Pa")
for name in ("CoolProp", "numpy", "pandas", "pyarrow", "matplotlib"):
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
