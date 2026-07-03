from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest
from pydantic import ValidationError

os.environ.setdefault("MPLBACKEND", "Agg")

from carnopy.app.plot_rendering import (
    RenderPlotPayload,
    _output_path,
    _source_name,
)
from carnopy.app.plot_staging import (
    PlotStagingLease,
    cleanup_plot_staging,
    create_plot_staging,
)
from carnopy.app.protocol import PROTOCOL_VERSION
from carnopy.app.source_inspection import inspect_for_app
from carnopy.app.worker import main
from carnopy.app.workspace import initialize_workspace
from carnopy.provenance import sha256_file
from carnopy.visualization.models import VisualizationError


def _dataset(path: Path) -> Path:
    pd.DataFrame(
        {
            "run_id": ["run"] * 4,
            "case_id": [0, 1, 2, 3],
            "mode": ["property_table"] * 4,
            "fluid": ["Propane"] * 4,
            "backend": ["coolprop"] * 4,
            "backend_model": ["heos"] * 4,
            "backend_version": ["test"] * 4,
            "phase": ["gas"] * 4,
            "valid": [True] * 4,
            "temperature_K": [280.0, 300.0, 280.0, 300.0],
            "pressure_Pa": [100_000.0, 100_000.0, 200_000.0, 200_000.0],
            "mass_density_kg_m3": [1.9, 1.8, 3.9, 3.7],
        }
    ).to_parquet(path, index=False)
    return path


def _payload(workspace: Path, source: Path, revision: str) -> dict[str, object]:
    return {
        "workspace_path": str(workspace),
        "source_path": str(source),
        "inspection_revision": revision,
        "plot_name": "density-curves",
        "format": "png",
        "plot": {
            "kind": "property_curves",
            "property": "mass_density",
            "x": "temperature",
        },
        "staging": {
            "staging_id": "a" * 32,
            "device": 0,
            "inode": 1,
        },
    }


def _leased_payload(
    workspace: Path,
    source: Path,
    revision: str,
) -> tuple[dict[str, object], PlotStagingLease]:
    lease = create_plot_staging(workspace)
    payload = _payload(workspace, source, revision)
    payload["staging"] = lease.worker_payload()
    return payload, lease


def _request(payload: dict[str, object]) -> str:
    return json.dumps(
        {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": str(uuid4()),
            "type": "render_plot",
            "payload": payload,
        }
    )


def _events(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_render_payload_has_one_authoritative_format(tmp_path: Path) -> None:
    base = _payload(tmp_path, tmp_path / "dataset.parquet", "a" * 64)

    assert RenderPlotPayload.model_validate(base).format == "png"
    RenderPlotPayload.model_validate({**base, "plot": {**base["plot"], "format": "png"}})

    with pytest.raises(ValidationError, match="conflicts with top-level format"):
        RenderPlotPayload.model_validate({**base, "plot": {**base["plot"], "format": "svg"}})
    with pytest.raises(ValidationError, match="not output_format"):
        RenderPlotPayload.model_validate({**base, "plot": {**base["plot"], "output_format": "png"}})


def test_source_name_is_worker_derived_and_safe(tmp_path: Path) -> None:
    run = tmp_path / "20260703T120000Z_Property_ABC12345"
    run.mkdir()
    standalone = tmp_path / "My Dataset (SI).parquet"
    standalone.touch()
    non_ascii = tmp_path / "数据.parquet"
    non_ascii.touch()

    assert _source_name(run, "a" * 64) == "20260703t120000z_property_abc12345"
    assert _source_name(standalone, "b" * 64) == "my-dataset-si"
    assert _source_name(non_ascii, "c" * 64) == "dataset-cccccccc"


def test_plot_output_rejects_symlinked_source_directory(tmp_path: Path) -> None:
    figures = tmp_path / "figures"
    figures.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (figures / "dataset").symlink_to(outside, target_is_directory=True)

    with pytest.raises(VisualizationError, match="symbolic link"):
        _output_path(figures, "dataset", "density", "png")


def test_plot_output_refuses_existing_image_or_sidecar(tmp_path: Path) -> None:
    figures = tmp_path / "figures"
    figures.mkdir()
    image = _output_path(figures, "dataset", "density", "png")
    image.write_bytes(b"existing")

    with pytest.raises(VisualizationError, match="refusing to overwrite"):
        _output_path(figures, "dataset", "density", "png")


def test_worker_renders_nested_plot_and_closes_figure(tmp_path: Path) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")
    dataset = _dataset(tmp_path / "My Dataset.parquet")
    inspection = inspect_for_app(dataset)
    payload, lease = _leased_payload(workspace.root, dataset, inspection.revision)
    stdout = io.StringIO()

    assert (
        main(
            io.StringIO(_request(payload) + "\n"),
            stdout,
            io.StringIO(),
        )
        == 0
    )

    events = _events(stdout)
    assert [event["type"] for event in events] == ["accepted", "phase", "result"]
    payload = events[-1]["payload"]
    assert isinstance(payload, dict)
    image = Path(str(payload["image_path"]))
    sidecar = Path(str(payload["sidecar_path"]))
    assert image == workspace.figures / "my-dataset" / "density-curves.png"
    assert sidecar == image.with_suffix(".plot.json")
    assert payload["image_sha256"] == sha256_file(image)
    assert payload["sidecar_sha256"] == sha256_file(sidecar)
    assert payload["visualization_request_id"].startswith("viz-")
    assert payload["valid_rows_plotted"] == 4
    sidecar_payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert sidecar_payload["image"]["path"] == str(image)
    assert sidecar_payload["image"]["sidecar_path"] == str(sidecar)
    assert (lease.path / "promotion-manifest.json").is_file()
    cleanup_plot_staging(lease, successful=True)
    assert not lease.path.exists()

    import matplotlib.pyplot as plt

    assert plt.get_fignums() == []


def test_render_plot_rejects_changed_inspection_revision(tmp_path: Path) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")
    dataset = _dataset(tmp_path / "dataset.parquet")
    payload, lease = _leased_payload(workspace.root, dataset, "0" * 64)
    stdout = io.StringIO()

    assert (
        main(
            io.StringIO(_request(payload) + "\n"),
            stdout,
            io.StringIO(),
        )
        == 1
    )

    payload = _events(stdout)[-1]["payload"]
    assert isinstance(payload, dict)
    assert payload["code"] == "execution_failed"
    assert "changed" in str(payload["message"])
    assert list(workspace.figures.iterdir()) == []
    cleanup_plot_staging(lease, successful=False)


def test_worker_plot_rendering_does_not_import_coolprop(tmp_path: Path) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")
    dataset = _dataset(tmp_path / "dataset.parquet")
    revision = inspect_for_app(dataset).revision
    payload, lease = _leased_payload(workspace.root, dataset, revision)
    request = _request(payload)
    code = r"""
import io
import json
import sys
from carnopy.app.worker import main

stdout = io.StringIO()
assert main(io.StringIO(sys.argv[1] + "\n"), stdout, io.StringIO()) == 0
payload = json.loads(stdout.getvalue().splitlines()[-1])["payload"]
assert payload["kind"] == "property_curves"
assert "CoolProp" not in sys.modules
assert "carnopy.backends.coolprop" not in sys.modules
assert "carnopy.app.capabilities" not in sys.modules
"""

    completed = subprocess.run(
        [sys.executable, "-c", code, request],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "MPLBACKEND": "Agg",
            "MPLCONFIGDIR": str(tmp_path / "mpl"),
        },
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    cleanup_plot_staging(lease, successful=True)
