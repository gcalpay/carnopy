from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent

from carnopy.app.draft_models import COMPATIBLE_ROLE as DRAFT_COMPATIBLE_ROLE
from carnopy.app.field_ids import (
    PLOT_NAME,
    VISUALIZATION_FILTERS,
    VISUALIZATION_PLOTS,
)
from carnopy.app.visualization_draft import (
    COMPATIBLE_ROLE,
    ISSUE_ROLE,
    VisualizationDraft,
)


@pytest.fixture(scope="module")
def application() -> QCoreApplication:
    existing = QCoreApplication.instance()
    app = existing if isinstance(existing, QCoreApplication) else QCoreApplication([])
    yield app
    if type(app) is QCoreApplication:
        app.quit()
        app.deleteLater()
        QCoreApplication.sendPostedEvents(app, QEvent.Type.DeferredDelete)


def capabilities() -> dict[str, Any]:
    return {
        "fluids": [
            {"name": "Propane", "aliases": ["R290"]},
            {"name": "Cyclopentane", "aliases": []},
        ],
        "visualization": {
            "plot_kinds": ["property_curves", "property_heatmap", "xy", "pv", "ts"],
            "formats": ["png", "pdf", "svg"],
            "scales": ["linear", "log"],
            "kind_contracts": {
                "property_curves": {
                    "required": ["property"],
                    "applicable": [
                        "property",
                        "x",
                        "filters",
                        "series",
                        "display_units",
                        "fluids",
                        "value_scale",
                        "format",
                    ],
                },
                "property_heatmap": {
                    "required": ["property"],
                    "applicable": [
                        "property",
                        "filters",
                        "display_units",
                        "fluids",
                        "color_scale",
                        "format",
                    ],
                },
                "xy": {
                    "required": ["x", "y"],
                    "applicable": [
                        "x",
                        "y",
                        "group_by",
                        "filters",
                        "series",
                        "display_units",
                        "fluids",
                        "x_scale",
                        "y_scale",
                        "format",
                    ],
                },
                "pv": {
                    "required": [],
                    "applicable": [
                        "filters",
                        "series",
                        "display_units",
                        "fluids",
                        "x_scale",
                        "y_scale",
                        "format",
                    ],
                },
                "ts": {
                    "required": [],
                    "applicable": [
                        "filters",
                        "series",
                        "display_units",
                        "fluids",
                        "x_scale",
                        "y_scale",
                        "format",
                    ],
                },
            },
            "fields": [
                {
                    "name": "temperature",
                    "kind": "numeric",
                    "axis_allowed": True,
                    "group_allowed": True,
                    "filter_allowed": True,
                },
                {
                    "name": "pressure",
                    "kind": "numeric",
                    "axis_allowed": True,
                    "group_allowed": True,
                    "filter_allowed": True,
                },
                {
                    "name": "phase",
                    "kind": "categorical",
                    "axis_allowed": False,
                    "group_allowed": True,
                    "filter_allowed": True,
                },
                {
                    "name": "fluid",
                    "kind": "categorical",
                    "axis_allowed": False,
                    "group_allowed": False,
                    "filter_allowed": False,
                },
                {
                    "name": "mass_density",
                    "kind": "numeric",
                    "axis_allowed": True,
                    "group_allowed": False,
                    "filter_allowed": False,
                },
                {
                    "name": "specific_entropy",
                    "kind": "numeric",
                    "axis_allowed": True,
                    "group_allowed": False,
                    "filter_allowed": False,
                },
                {
                    "name": "specific_volume",
                    "kind": "numeric",
                    "axis_allowed": True,
                    "group_allowed": False,
                    "filter_allowed": False,
                },
            ],
            "display_units": {
                "temperature": ["K", "degC"],
                "pressure": ["Pa", "bar"],
                "specific_entropy": ["J/(kg*K)", "kJ/(kg*K)"],
            },
            "categorical_values": {"phase": ["gas", "liquid"]},
        },
    }


def dataset(*, properties: list[str] | None = None) -> dict[str, object]:
    return {
        "mode": "property_table",
        "fluids": ["R290", "Cyclopentane"],
        "grid": {"temperature": {}, "pressure": {}},
        "properties": properties or ["mass_density", "specific_entropy"],
    }


def curves(name: str = "density-curves") -> dict[str, object]:
    return {
        "name": name,
        "kind": "property_curves",
        "property": "mass_density",
        "x": "temperature",
    }


def configured_draft(value: object) -> VisualizationDraft:
    draft = VisualizationDraft()
    draft.apply_capabilities(capabilities())
    draft.set_dataset_context(dataset())
    draft.load_visualization(value)
    return draft


def test_complete_visualization_round_trips_and_starts_clean(
    application: QCoreApplication,
) -> None:
    del application
    visualization = {
        "format": "svg",
        "fluids": ["Propane"],
        "filters": {"phase": "gas"},
        "plots": [
            curves(),
            {"name": "density-map", "kind": "property_heatmap", "property": "mass_density"},
            {
                "name": "entropy-density",
                "kind": "xy",
                "x": "specific_entropy",
                "y": "mass_density",
            },
            {"name": "pressure-volume", "kind": "pv"},
            {"name": "temperature-entropy", "kind": "ts"},
        ],
    }
    draft = configured_draft(visualization)

    assert draft.get_locally_valid()
    assert not draft.get_dirty()
    assert draft.visualization_payload() == visualization
    assert draft.plot_model.rowCount() == 5


def test_disabled_latent_state_uses_canonical_dirty_semantics(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft(None)
    assert draft.get_locally_valid()
    assert not draft.get_dirty()

    draft.set_enabled(True)
    active = draft.begin_add_plot()
    assert active is not None
    assert draft.commit_plot()
    assert draft.get_dirty()
    assert draft.plot_payloads()

    draft.set_enabled(False)
    assert draft.visualization_payload() is None
    assert not draft.get_dirty()
    assert draft.plot_payloads()

    draft.set_enabled(True)
    assert draft.get_dirty()
    assert draft.get_locally_valid()


def test_disabling_saved_visualization_is_dirty_and_reversible(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft({"plots": [curves()]})

    draft.set_enabled(False)
    assert draft.get_dirty()
    draft.set_enabled(True)
    assert not draft.get_dirty()


def test_temporary_plot_lifecycle_is_single_owner_and_transactional(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft({"plots": [curves("first"), {"name": "second", "kind": "pv"}]})
    messages: list[str] = []
    draft.message.connect(messages.append)

    active = draft.begin_edit_plot(0)
    assert active is not None
    active.set_name("edited")
    assert draft.begin_add_plot() is None
    assert not draft.remove_plot(1)
    assert "active plot edit" in messages[-1]
    assert draft.cancel_plot()
    assert [plot["name"] for plot in draft.plot_payloads()] == ["first", "second"]

    active = draft.begin_edit_plot(0)
    assert active is not None
    active.set_name("edited")
    assert draft.commit_plot()
    assert draft.move_plot(1, -1)
    assert [plot["name"] for plot in draft.plot_payloads()] == ["second", "edited"]
    assert draft.remove_plot(1)
    assert [plot["name"] for plot in draft.plot_payloads()] == ["second"]


def test_active_plot_edit_locks_every_shared_visualization_mutation(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft(
        {
            "format": "png",
            "fluids": ["Propane"],
            "filters": {"pressure": 100000.0},
            "display_units": {"pressure": "bar"},
            "plots": [curves()],
        }
    )
    before = draft.raw_state()
    messages: list[str] = []
    draft.message.connect(messages.append)
    assert draft.begin_edit_plot(0) is not None
    assert draft.get_has_active_plot_edit()

    draft.set_enabled(False)
    draft.set_format("svg")
    assert not draft.set_fluid_selected("Cyclopentane", True)
    assert not draft.filters.set_raw_value(0, "200000")
    assert not draft.display_units.remove_row(0)
    assert not draft.remove_plot(0)
    assert not draft.move_plot(0, 1)

    assert draft.raw_state() == before
    assert messages
    assert all("active plot edit" in message for message in messages)
    assert draft.cancel_plot()
    assert not draft.get_has_active_plot_edit()


def test_structured_visualization_issue_identifies_shared_and_plot_rows(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft(
        {
            "filters": {"pressure": 100000.0},
            "plots": [curves()],
        }
    )
    draft.filters.set_raw_value(0, "bad")

    assert draft.get_first_invalid_field() == VISUALIZATION_FILTERS
    assert draft.get_first_invalid_row() == 0

    draft.filters.set_raw_value(0, "100000")
    draft.set_dataset_context(dataset(properties=["specific_entropy"]))

    assert draft.get_first_invalid_field() == VISUALIZATION_PLOTS
    assert draft.get_first_invalid_row() == 0


def test_invalid_plot_commit_emits_structured_attention_without_closing_editor(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft({"plots": [curves()]})
    rejected: list[tuple[str, int, str]] = []
    draft.plot_commit_rejected.connect(
        lambda field, row, message: rejected.append((field, row, message))
    )
    active = draft.begin_add_plot()
    assert active is not None
    active.set_name("density-curves")

    assert not draft.commit_plot()
    assert draft.get_active_plot_draft() is active
    assert rejected
    assert rejected[-1][0] == PLOT_NAME
    assert rejected[-1][1] == -1


def test_context_refresh_preserves_active_raw_values_and_lifecycle_replaces_it(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft({"plots": [curves()]})
    active = draft.begin_edit_plot(0)
    assert active is not None
    active.filters.add_row("pressure", "not-a-number")

    draft.set_dataset_context(dataset(properties=["specific_entropy"]))

    assert draft.get_active_plot_draft() is active
    assert active.filters.raw_rows() == (("pressure", "not-a-number"),)
    assert not active.get_locally_valid()
    draft.load_visualization({"plots": [{"name": "entropy", "kind": "ts"}]})
    assert draft.get_active_plot_draft() is None
    assert draft.plot_payloads() == [{"name": "entropy", "kind": "ts"}]


def test_dataset_incompatibility_retains_plot_and_blocks_only_while_enabled(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft({"plots": [curves()]})

    draft.set_dataset_context(dataset(properties=["specific_entropy"]))

    assert draft.plot_payloads() == [curves()]
    index = draft.plot_model.index(0, 0)
    assert index.data(COMPATIBLE_ROLE) is False
    assert "unavailable" in str(index.data(ISSUE_ROLE))
    assert not draft.get_locally_valid()
    with pytest.raises(ValueError, match="unavailable"):
        draft.visualization_payload()

    draft.set_enabled(False)
    assert draft.get_locally_valid()
    assert draft.visualization_payload() is None
    draft.set_dataset_context(dataset())
    draft.set_enabled(True)
    assert draft.get_locally_valid()


def test_shared_inheritance_merge_and_override_semantics(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft(
        {
            "format": "svg",
            "fluids": ["Propane"],
            "filters": {"phase": "gas"},
            "display_units": {"pressure": "bar"},
            "plots": [
                {
                    **curves(),
                    "format": "pdf",
                    "fluids": ["Cyclopentane"],
                    "filters": {"phase": "gas"},
                    "display_units": {"pressure": "Pa"},
                },
                curves("inherits"),
            ],
        }
    )

    overridden = draft._effective_plot(draft.plot_payloads()[0])
    inherited = draft._effective_plot(draft.plot_payloads()[1])
    assert overridden["format"] == "pdf"
    assert overridden["fluids"] == ["Cyclopentane"]
    assert overridden["display_units"] == {"pressure": "Pa"}
    assert inherited["format"] == "svg"
    assert inherited["fluids"] == ["Propane"]
    assert inherited["display_units"] == {"pressure": "bar"}
    assert draft.resolved_plot_payload(0) == overridden
    assert draft.resolved_plot_payload(1) == inherited
    assert draft.resolved_plot_payload(2) is None

    conflicting = draft.plot_payloads()
    conflicting[0]["filters"] = {"phase": "liquid"}
    draft.load_visualization(
        {
            "filters": {"phase": "gas"},
            "plots": conflicting,
        }
    )
    assert not draft.get_locally_valid()
    assert "conflicting shared" in draft.get_issue()


def test_incompatible_shared_rows_and_fluids_remain_visible(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft(
        {
            "fluids": ["Propane"],
            "display_units": {"specific_entropy": "kJ/(kg*K)"},
            "plots": [{"name": "entropy", "kind": "ts"}],
        }
    )

    draft.set_dataset_context(
        {
            "mode": "property_table",
            "fluids": ["Cyclopentane"],
            "grid": {"temperature": {}, "pressure": {}},
            "properties": ["mass_density"],
        }
    )

    assert draft.selected_fluid_values() == ("Propane",)
    assert draft.display_units.raw_rows() == (("specific_entropy", "kJ/(kg*K)"),)
    assert not draft.get_locally_valid()
    fluid = draft.selected_fluids.index(0, 0)
    assert fluid.data(DRAFT_COMPATIBLE_ROLE) is False


def test_alias_duplicates_are_rejected_without_dropping_values(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft(
        {
            "fluids": ["Propane", "R290"],
            "plots": [curves()],
        }
    )

    assert draft.selected_fluid_values() == ("Propane", "R290")
    assert not draft.get_locally_valid()
    assert "duplicate canonical" in draft.get_issue()


def test_invalid_raw_shared_mapping_is_dirty_and_recovers_semantically(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft(
        {
            "filters": {"pressure": 100000.0},
            "plots": [curves()],
        }
    )
    draft.filters.set_raw_value(0, "")
    assert not draft.get_locally_valid()
    assert draft.get_dirty()
    draft.filters.set_raw_value(0, "100000")
    assert draft.get_locally_valid()
    assert not draft.get_dirty()


def test_reset_for_mode_change_cancels_edit_and_preserves_baseline_difference(
    application: QCoreApplication,
) -> None:
    del application
    draft = configured_draft({"plots": [curves()]})
    assert draft.begin_edit_plot(0) is not None

    draft.reset_for_mode_change()

    assert draft.get_active_plot_draft() is None
    assert draft.visualization_payload() is None
    assert draft.plot_payloads() == []
    assert draft.get_dirty()


def test_visualization_draft_import_excludes_heavy_modules() -> None:
    code = """
import sys
import carnopy.app.visualization_draft
for name in (
    "CoolProp", "numpy", "pandas", "pyarrow", "matplotlib",
    "carnopy.cli", "carnopy.pipeline", "carnopy.visualization.plots",
    "carnopy.visualization.render", "carnopy.app.plot_rendering",
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
