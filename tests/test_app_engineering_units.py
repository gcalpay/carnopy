from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from carnopy.app.sampler_draft import SamplerDraft
from carnopy.sampling.canonical import canonical_sampler_key


@pytest.fixture(scope="module")
def application() -> QApplication:
    existing = QApplication.instance()
    return existing if isinstance(existing, QApplication) else QApplication([])


def test_atmospheric_pressure_toggles_preserve_full_declared_precision(
    application: QApplication,
) -> None:
    del application
    draft = SamplerDraft("pressure")
    draft.load_payload(
        {"kind": "explicit", "values": [101_325.0], "unit": "Pa"},
        available_units=["Pa", "hPa", "kPa", "MPa", "bar", "atm"],
    )
    anchor_key = canonical_sampler_key("pressure", draft._sampler_model())

    assert draft.requestUnitChange("bar")
    assert draft.text("values") == "1.01325"
    assert canonical_sampler_key("pressure", draft._sampler_model()) == anchor_key

    assert draft.requestUnitChange("atm")
    assert draft.text("values") == "1"
    assert canonical_sampler_key("pressure", draft._sampler_model()) == anchor_key


def test_property_starter_pressure_toggles_to_exact_atmospheres(
    application: QApplication,
) -> None:
    del application
    draft = SamplerDraft("pressure")
    draft.load_payload(
        {
            "kind": "linspace",
            "start": 101_325.0,
            "stop": 506_625.0,
            "num": 41,
            "unit": "Pa",
        },
        available_units=["Pa", "hPa", "kPa", "MPa", "bar", "atm"],
    )
    anchor_key = canonical_sampler_key("pressure", draft._sampler_model())

    assert draft.requestUnitChange("atm")
    assert draft.text("start") == "1"
    assert draft.text("stop") == "5"
    assert draft.text("num") == "41"
    assert canonical_sampler_key("pressure", draft._sampler_model()) == anchor_key
