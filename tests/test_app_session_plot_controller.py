from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from carnopy.app.inspection_controller import InspectionController
from carnopy.app.plot_draft import PlotDraft
from carnopy.app.plot_preview_provider import VerifiedPlotPreviewRegistry
from carnopy.app.protocol import RequestType, WorkerEvent
from carnopy.app.request_coordinator import (
    DesktopRequestCoordinator,
    RequestFinalizer,
    RequestOutcome,
)
from carnopy.app.session_plot_controller import SessionPlotController
from carnopy.app.workspace import initialize_workspace
from carnopy.visualization.requests import PlotRequest, request_id


class StubSession(QObject):
    event_received = Signal(object)
    completed = Signal(object)
    policy_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.request_id = uuid4()
        self.force_stop_available = True

    def force_stop(self) -> bool:
        self.force_stop_available = False
        self.policy_changed.emit()
        return True


class StubCoordinator(QObject):
    busy_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.is_busy = False
        self.session: StubSession | None = None
        self.finalizer: RequestFinalizer | None = None
        self.started: dict[str, object] | None = None

    def start_request(
        self,
        _owner: str,
        _request_type: RequestType,
        payload: dict[str, object],
        *,
        finalizer: RequestFinalizer | None = None,
    ) -> StubSession:
        self.started = payload
        self.finalizer = finalizer
        self.session = StubSession()
        self.is_busy = True
        self.busy_changed.emit(True)
        return self.session

    def finish(
        self,
        *,
        result: dict[str, object] | None = None,
        failure: dict[str, object] | None = None,
    ) -> None:
        assert self.session is not None
        successful = result is not None
        cleanup = self.finalizer.finish(successful) if self.finalizer is not None else None
        terminal = (
            WorkerEvent(
                request_id=self.session.request_id,
                type="result",
                payload=result,
            )
            if result is not None
            else None
        )
        outcome = RequestOutcome(
            request_id=self.session.request_id,
            request_type="render_plot",
            owner="plot",
            terminal_event=terminal,
            client_failure=failure,
            stderr="",
            exit_code=0 if successful else 1,
            exit_status="normal" if successful else "crash",
            force_stopped=False,
            cleanup_error=cleanup,
            terminal_envelope={
                "request_id": str(self.session.request_id),
                "request_type": "render_plot",
                "terminal_event": (None if terminal is None else terminal.model_dump(mode="json")),
                "client_failure": failure,
                "stderr": "",
                "exit_code": 0 if successful else 1,
                "exit_status": "normal" if successful else "crash",
                "force_stopped": False,
                "cleanup_error": cleanup,
            },
        )
        self.session.completed.emit(outcome)
        self.is_busy = False
        self.busy_changed.emit(False)


@pytest.fixture(scope="module")
def application() -> QApplication:
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    yield app


def _context(source: Path, *, mode: str = "property_table") -> dict[str, object]:
    return {
        "source": str(source),
        "source_kind": "dataset",
        "revision": "a" * 64,
        "plot_context": {
            "mode": mode,
            "fluids": ["Propane"],
            "properties": ["mass_density"],
            "visualization": {
                "plot_kinds": ["property_curves", "xy", "pv"],
                "formats": ["png", "svg", "pdf"],
                "scales": ["linear", "log"],
                "kind_contracts": {
                    "property_curves": {
                        "required": ["property"],
                        "applicable": ["property", "x", "fluids", "format"],
                    },
                    "xy": {
                        "required": ["x", "y", "format"],
                        "applicable": ["x", "y", "format"],
                    },
                    "pv": {
                        "required": ["format"],
                        "applicable": ["format"],
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
                        "name": "mass_density",
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
            },
        },
    }


def _controller(
    tmp_path: Path,
) -> tuple[SessionPlotController, StubCoordinator, Path]:
    stub = StubCoordinator()
    inspection = InspectionController(cast(DesktopRequestCoordinator, stub))
    controller = SessionPlotController(
        cast(DesktopRequestCoordinator, stub),
        inspection,
        VerifiedPlotPreviewRegistry(),
    )
    workspace = initialize_workspace(tmp_path / "workspace")
    source = workspace.outputs / "source.parquet"
    source.write_bytes(b"source")
    controller.set_workspace(workspace)
    controller._inspection_changed(_context(source))
    return controller, stub, source


def _select_property_curve(controller: SessionPlotController) -> PlotDraft:
    draft = controller.get_active_plot_draft()
    assert isinstance(draft, PlotDraft)
    draft.set_kind("property_curves")
    draft.set_property_name("mass_density")
    draft.set_x_field("temperature")
    return draft


def test_configured_request_opens_as_session_edit_without_rendering(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    controller, stub, _source = _controller(tmp_path)

    assert controller.begin_edit_from_request(
        {
            "name": "configured-density",
            "kind": "property_curves",
            "property": "mass_density",
            "x": "temperature",
            "format": "svg",
        }
    )
    draft = controller.get_active_plot_draft()
    assert isinstance(draft, PlotDraft)
    assert draft.get_name() == "configured-density"
    assert draft.get_kind() == "property_curves"
    assert draft.get_property_name() == "mass_density"
    assert draft.get_x_field() == "temperature"
    assert draft.get_output_format() == "svg"
    assert stub.started is None


@pytest.mark.parametrize(
    ("mode", "expected_x"),
    [
        ("property_table", "temperature"),
        ("saturation_table", ""),
        ("vapor_mass_fraction_table", ""),
    ],
)
def test_new_session_edit_uses_valid_compatible_defaults_without_rendering(
    tmp_path: Path,
    application: QApplication,
    mode: str,
    expected_x: str,
) -> None:
    del application
    controller, stub, source = _controller(tmp_path)
    controller._inspection_changed(_context(source, mode=mode))

    assert controller.begin_edit("png")
    draft = controller.get_active_plot_draft()
    assert isinstance(draft, PlotDraft)
    assert draft.get_name() == "session-plot"
    assert draft.get_kind() == "property_curves"
    assert draft.get_property_name() == "mass_density"
    assert draft.get_x_field() == expected_x
    assert draft.selected_fluid_values() == ("Propane",)
    assert draft.get_output_format() == "png"
    assert draft.get_locally_valid()
    assert controller.get_can_render()
    assert stub.started is None


def test_new_session_edit_rejects_context_without_a_compatible_plot(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    controller, stub, source = _controller(tmp_path)
    context = _context(source)
    plot_context = context["plot_context"]
    assert isinstance(plot_context, dict)
    visualization = plot_context["visualization"]
    assert isinstance(visualization, dict)
    visualization["plot_kinds"] = []
    controller._inspection_changed(context)

    assert not controller.begin_edit("png")
    assert not controller.get_has_active_edit()
    assert controller.get_state() == "failed"
    assert controller.get_issue_code() == "no_compatible_plot"
    assert "unavailable for this dataset" in controller.get_issue()
    assert stub.started is None


def test_session_edit_explicitly_selects_all_source_fluids(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    controller, stub, _source = _controller(tmp_path)
    assert controller._context is not None
    controller._context["fluids"] = ["Propane", "IsoButane"]
    visualization = controller._context["visualization"]
    assert isinstance(visualization, dict)
    contracts = visualization["kind_contracts"]
    assert isinstance(contracts, dict)
    for contract in contracts.values():
        assert isinstance(contract, dict)
        applicable = contract["applicable"]
        assert isinstance(applicable, list)
        applicable.append("fluids")

    assert controller.begin_edit("png")
    draft = controller.get_active_plot_draft()
    assert isinstance(draft, PlotDraft)
    assert draft.selected_fluid_values() == ("Propane", "IsoButane")
    _select_property_curve(controller)

    assert draft.set_fluid_selected("Propane", False)
    assert draft.set_fluid_selected("IsoButane", False)
    assert draft.get_first_invalid_field() == "plot.fluids"
    assert draft.get_issue() == "select at least one inspected-source fluid"
    assert not controller.get_can_render()
    assert stub.started is None


def test_session_plot_success_commits_result_and_destroys_edit(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    controller, stub, source = _controller(tmp_path)
    assert controller.begin_edit("png")
    assert controller.get_can_render()
    assert controller.render()
    request = PlotRequest(
        name="session-plot",
        kind="property_curves",
        property_name="mass_density",
        x_field="temperature",
    )
    canonical = request.canonical_dict()
    visualization_id = request_id((request,))
    image = controller.workspace.figures / "source" / "session-plot.png"  # type: ignore[union-attr]
    image.parent.mkdir()
    image.write_bytes(b"png")
    sidecar_path = image.with_suffix(".plot.json")
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    sidecar_path.write_text(
        json.dumps(
            {
                "plot_schema_version": 2,
                "plot_kind": "property_curves",
                "source_identity": {
                    "requested_path": str(source),
                    "dataset_path": str(source),
                },
                "visualization_request_id": visualization_id,
                "normalized_request": canonical,
                "valid_sample_count": 4,
                "excluded_sample_count": 0,
                "advisories": [
                    {
                        "code": "crowded_curve_family",
                        "message": "Select fewer exact pressure series.",
                    }
                ],
                "image": {
                    "path": str(image),
                    "sidecar_path": str(sidecar_path),
                    "sha256": digest,
                    "format": "png",
                },
            }
        ),
        encoding="utf-8",
    )
    sidecar_digest = hashlib.sha256(sidecar_path.read_bytes()).hexdigest()
    stub.finish(
        result={
            "source": str(source),
            "inspection_revision": "a" * 64,
            "image_path": str(image),
            "sidecar_path": str(sidecar_path),
            "sidecar_sha256": sidecar_digest,
            "image_sha256": digest,
            "format": "png",
            "kind": "property_curves",
            "valid_rows_plotted": 4,
            "invalid_rows_excluded": 0,
            "visualization_request_id": visualization_id,
            "normalized_request": canonical,
        }
    )

    assert controller.get_state() == "succeeded"
    assert not controller.get_has_active_edit()
    assert controller.get_committed_request()["name"] == "session-plot"
    assert controller.get_preview_url().startswith("image://carnopy-plots/")
    assert controller.get_result_name() == "session-plot"
    assert controller.get_result_kind() == "property_curves"
    assert controller.get_result_format() == "png"
    assert controller.get_valid_sample_count() == 4
    assert controller.get_excluded_sample_count() == 0
    assert controller.get_advisory_text() == "Select fewer exact pressure series."

    exported = tmp_path / "exported-session.png"
    assert controller.export_result(str(exported))
    exported_sidecar = exported.with_suffix(".plot.json")
    assert exported.read_bytes() == b"png"
    exported_payload = json.loads(exported_sidecar.read_text(encoding="utf-8"))
    assert exported_payload["image"]["path"] == str(exported.resolve())
    assert exported_payload["image"]["sidecar_path"] == str(exported_sidecar.resolve())
    assert exported_payload["image"]["sha256"] == digest

    assert controller.begin_edit("svg")
    assert controller.render()
    stub.finish(
        failure={
            "category": "execution",
            "code": "execution_failed",
            "message": "second render failed",
        }
    )
    assert controller.get_has_active_edit()
    assert controller.get_has_result()
    assert controller.cancel_edit()
    assert controller.get_has_result()


def test_session_plot_failure_keeps_edit_and_uses_only_structured_field(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    controller, stub, _source = _controller(tmp_path)
    attention: list[tuple[str, int]] = []
    controller.attention_requested.connect(lambda field, row: attention.append((field, row)))
    assert controller.begin_edit("png")
    _select_property_curve(controller)
    assert controller.render()
    stub.finish(
        failure={
            "category": "execution",
            "code": "execution_failed",
            "message": "English text mentions plot.name but is not parsed",
            "details": {"issues": [{"field": "plot.filters", "row": 2}]},
        }
    )

    assert controller.get_state() == "editing"
    assert controller.get_has_active_edit()
    assert attention == [("plot.filters", 2)]
    assert controller.can_replace_inspection("changing source") is False
    workspace = controller.workspace
    assert workspace is not None
    replacement = initialize_workspace(tmp_path / "replacement")
    controller.set_workspace(replacement)
    assert controller.workspace == workspace
    assert controller.cancel_edit()


def test_importing_plot_controllers_keeps_worker_dependencies_out_of_gui() -> None:
    code = """
import sys
import carnopy.app.configured_plot_results_controller
import carnopy.app.session_plot_controller
for name in (
    "carnopy.visualization.configuration", "carnopy.visualization.models",
    "carnopy.visualization.plots", "carnopy.app.plot_rendering",
    "carnopy.app.source_inspection", "carnopy.app.table_preview",
    "CoolProp", "numpy", "pandas", "pyarrow", "matplotlib",
):
    if name in sys.modules:
        raise SystemExit(name)
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
