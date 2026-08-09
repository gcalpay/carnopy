from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from carnopy.app.activity_controller import ActivityController
from carnopy.app.client import WorkerClient
from carnopy.app.config_controller import ConfigurationController
from carnopy.app.config_document import ConfigurationDocument, sha256_bytes
from carnopy.app.configured_plot_results_controller import ConfiguredPlotResultsController
from carnopy.app.jobs import JobStore
from carnopy.app.plot_artifacts import (
    PlotArtifactError,
    export_verified_plot_bundle,
    verify_configured_plot_record,
)
from carnopy.app.plot_preview_provider import (
    VerifiedPlotPreviewRegistry,
    _qt_compatible_svg_preview,
)
from carnopy.app.request_coordinator import DesktopRequestCoordinator
from carnopy.app.workspace import Workspace, initialize_workspace
from carnopy.visualization.requests import PlotRequest, request_id


def _configured_bundle(
    tmp_path: Path,
) -> tuple[Workspace, dict[str, object], Path, Path]:
    workspace = initialize_workspace(tmp_path / "workspace")
    output_directory = workspace.outputs / "run-one"
    output_directory.mkdir()
    dataset = output_directory / "dataset.parquet"
    dataset.write_bytes(b"recorded dataset")
    figure_directory = workspace.figures / "run-one"
    figure_directory.mkdir()
    image_path = figure_directory / "density.png"
    image_path.write_bytes(b"recorded image")
    sidecar_path = image_path.with_suffix(".plot.json")
    request = PlotRequest(
        name="density",
        kind="property_curves",
        property_name="mass_density",
        x_field="temperature",
        fluids=("n-Propane",),
    )
    canonical = request.canonical_dict()
    visualization_id = request_id((request,))
    source_identity = {
        "requested_path": str(output_directory),
        "dataset_path": str(dataset),
        "dataset_format": "parquet",
        "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "integrity": "verified",
        "metadata_path": None,
        "run_id": "run-id",
        "spec_id": "spec-id",
        "generation_context_id": "context-id",
        "mode": "property_table",
        "backend": "coolprop",
        "backend_model": "heos",
        "backend_version": "8.0.0",
        "reference_state_policy": "DEF",
    }
    sidecar = {
        "plot_schema_version": 2,
        "plot_kind": request.kind,
        "source_identity": source_identity,
        "visualization_request_id": visualization_id,
        "normalized_request": canonical,
        "advisories": [],
        "valid_sample_count": 4,
        "excluded_sample_count": 0,
        "image": {
            "path": str(image_path),
            "sidecar_path": str(sidecar_path),
            "sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
            "format": "png",
        },
    }
    sidecar_path.write_text(
        json.dumps(sidecar, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path = figure_directory / "visualization-report.json"
    report = {
        "visualization_report_schema_version": 1,
        "visualization_request_id": visualization_id,
        "status": "completed",
        "source_identity": {
            "run_directory": str(output_directory),
            "run_id": "run-id",
            "spec_id": "spec-id",
            "generation_context_id": "context-id",
        },
        "normalized_visualization": {
            "visualization_request_id": visualization_id,
            "plots": [canonical],
        },
        "requested_plot_count": 1,
        "succeeded_plot_count": 1,
        "failed_plot_count": 0,
        "skipped_plot_count": 0,
        "outcomes": [
            {
                "name": "density",
                "kind": request.kind,
                "status": "completed",
                "image_path": str(image_path),
                "sidecar_path": str(sidecar_path),
                "valid_sample_count": 4,
                "excluded_sample_count": 0,
                "advisories": [],
            }
        ],
    }
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    record: dict[str, object] = {
        "job_schema_version": 1,
        "request_id": "request-id",
        "operation": "generate",
        "status": "completed",
        "configuration": {
            "relative_path": "configs/config.yaml",
            "sha256": "a" * 64,
        },
        "summary": {
            "run_id": "run-id",
            "spec_id": "spec-id",
            "generation_context_id": "context-id",
            "output_directory": str(output_directory),
            "visualization": {
                "visualization_request_id": visualization_id,
                "status": "completed",
                "figure_directory": str(figure_directory),
                "report_path": str(report_path),
                "requested_plot_count": 1,
                "succeeded_plot_count": 1,
                "failed_plot_count": 0,
                "skipped_plot_count": 0,
            },
        },
    }
    return workspace, record, report_path, sidecar_path


@pytest.fixture(scope="module")
def application() -> QApplication:
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    yield app


def test_configured_plot_verification_is_record_driven_and_ordered(
    tmp_path: Path,
) -> None:
    workspace, record, _report_path, _sidecar_path = _configured_bundle(tmp_path)
    unrecorded = workspace.figures / "run-one" / "unrecorded.png"
    unrecorded.write_bytes(b"not part of the report")

    bundle = verify_configured_plot_record(workspace, record)

    assert bundle.request_id == "request-id"
    assert [outcome.name for outcome in bundle.outcomes] == ["density"]
    assert bundle.outcomes[0].artifact is not None
    assert all(outcome.name != "unrecorded" for outcome in bundle.outcomes)


def test_configured_plot_verification_rejects_request_or_image_tampering(
    tmp_path: Path,
) -> None:
    workspace, record, _report_path, sidecar_path = _configured_bundle(tmp_path)
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar["normalized_request"]["name"] = "another-name"
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    with pytest.raises(PlotArtifactError, match="request does not match"):
        verify_configured_plot_record(workspace, record)

    workspace, record, _report_path, _sidecar_path = _configured_bundle(tmp_path / "second")
    image = workspace.figures / "run-one" / "density.png"
    image.write_bytes(b"tampered")
    with pytest.raises(PlotArtifactError, match="SHA-256"):
        verify_configured_plot_record(workspace, record)


def test_export_rewrites_only_export_paths_and_refuses_overwrite(tmp_path: Path) -> None:
    workspace, record, _report_path, sidecar_path = _configured_bundle(tmp_path)
    bundle = verify_configured_plot_record(workspace, record)
    artifact = bundle.outcomes[0].artifact
    assert artifact is not None
    source_sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))

    destination = tmp_path / "exports" / "copy.png"
    destination.parent.mkdir()
    image_path, exported_sidecar_path = export_verified_plot_bundle(
        artifact,
        destination,
    )
    exported = json.loads(exported_sidecar_path.read_text(encoding="utf-8"))

    assert image_path.read_bytes() == artifact.image_path.read_bytes()
    assert exported["image"]["path"] == str(image_path)
    assert exported["image"]["sidecar_path"] == str(exported_sidecar_path)
    source_sidecar["image"]["path"] = str(image_path)
    source_sidecar["image"]["sidecar_path"] = str(exported_sidecar_path)
    assert exported == source_sidecar
    with pytest.raises(PlotArtifactError, match="overwrite"):
        export_verified_plot_bundle(artifact, destination)


def test_configured_results_controller_projects_only_activity_records(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    workspace, record, _report_path, _sidecar_path = _configured_bundle(tmp_path)
    document = ConfigurationDocument({"schema_version": 2, "document_type": "dataset"})
    config_path = workspace.configs / "config.yaml"
    config_path.write_bytes(document.yaml_bytes)
    document.mark_saved(config_path, document.yaml_bytes)
    configuration_record = record["configuration"]
    assert isinstance(configuration_record, dict)
    configuration_record["sha256"] = sha256_bytes(document.yaml_bytes)
    JobStore(workspace.private_directory).write(record)
    coordinator = DesktopRequestCoordinator(WorkerClient())
    activity = ActivityController(coordinator)
    configuration = ConfigurationController(coordinator)
    configuration.document = document
    controller = ConfiguredPlotResultsController(
        activity,
        configuration,
        VerifiedPlotPreviewRegistry(),
    )
    activity.set_workspace(workspace)
    controller.set_workspace(workspace)

    assert controller.records_model.get_count() == 1
    assert controller.select_generation("request-id")
    assert controller.get_evidence_label() == "Recorded provenance consistent"
    assert controller.outcomes_model.get(0)["name"] == "density"
    assert controller.get_selected_name() == "density"
    assert controller.get_selected_kind() == "property_curves"
    assert controller.get_selected_format() == "png"
    assert controller.get_selected_valid_sample_count() == 4
    assert controller.get_selected_excluded_sample_count() == 0
    assert controller.get_preview_url().startswith("image://carnopy-plots/")
    assert controller.get_result_matches_current_saved_baseline()

    document.set_payload(
        {"schema_version": 2, "document_type": "dataset", "mode": "property_table"}
    )
    configuration.state_changed.emit()
    assert controller.get_current_draft_dirty()
    assert controller.get_result_matches_current_saved_baseline()
    assert "unsaved draft changes" in controller.get_result_relation_issue()
    coordinator.shutdown()


def test_preview_tokens_revalidate_bytes_and_can_be_revoked(tmp_path: Path) -> None:
    workspace, record, _report_path, _sidecar_path = _configured_bundle(tmp_path)
    bundle = verify_configured_plot_record(workspace, record)
    artifact = bundle.outcomes[0].artifact
    assert artifact is not None
    registry = VerifiedPlotPreviewRegistry()
    token = registry.issue(
        workspace_identity=str(workspace.root),
        figures_root=workspace.figures,
        image_path=artifact.image_path,
        image_sha256=artifact.image_sha256,
        image_format=artifact.image_format,
        verification_revision=bundle.verification_revision,
    )

    assert registry.read(token) == (b"recorded image", "png")
    artifact.image_path.write_bytes(b"tampered")
    with pytest.raises(PlotArtifactError, match="SHA-256"):
        registry.read(token)
    registry.revoke(token)
    with pytest.raises(PlotArtifactError, match="token is unavailable"):
        registry.read(token)


def test_svg_preview_removes_only_empty_glyph_definitions_and_uses() -> None:
    svg = b"""\
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:xlink="http://www.w3.org/1999/xlink" width="20" height="20">
  <defs>
    <path id="empty-space" transform="scale(0.015625)"/>
    <path id="visible-mark" d="M 1 1 L 19 19"/>
  </defs>
  <g>
    <use xlink:href="#empty-space"/>
    <use xlink:href="#visible-mark"/>
  </g>
</svg>
"""

    preview = _qt_compatible_svg_preview(svg)

    assert b"empty-space" not in preview
    assert b"visible-mark" in preview
    image = QImage.fromData(preview)
    assert not image.isNull()
