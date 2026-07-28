from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

MISSING_APP_EXTRA = """Carnopy desktop application requires the app extra.

With pip:
  python -m pip install "carnopy[app]"

With uv:
  uv tool install --force "carnopy[app]"
"""


def run_command(
    arguments: list[str],
    *,
    cwd: Path,
    expected_code: int = 0,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [sys.executable, "-m", "carnopy", *arguments],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != expected_code:
        raise RuntimeError(
            f"command failed with {completed.returncode}, expected {expected_code}: "
            f"{arguments}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed


def run_app_command(
    arguments: list[str],
    *,
    cwd: Path,
    expected_code: int = 0,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [str(Path(sys.executable).with_name("carnopy-app")), *arguments],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != expected_code:
        raise RuntimeError(
            f"carnopy-app failed with {completed.returncode}, expected {expected_code}: "
            f"{arguments}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed


def run_gui_command(
    arguments: list[str],
    *,
    cwd: Path,
    expected_code: int = 0,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [str(Path(sys.executable).with_name("carnopy-gui")), *arguments],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != expected_code:
        raise RuntimeError(
            f"carnopy-gui failed with {completed.returncode}, expected {expected_code}: "
            f"{arguments}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed


def smoke_public_qml_apps(work_directory: Path) -> None:
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    for command_name in ("carnopy-gui", "carnopy-app"):
        completed = subprocess.run(
            [str(Path(sys.executable).with_name(command_name)), "--smoke-test"],
            cwd=work_directory,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"offscreen {command_name} QML smoke test failed\n"
                f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
            )


def smoke_app_plot(work_directory: Path, source: Path) -> None:
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    environment["MPLBACKEND"] = "Agg"
    environment["MPLCONFIGDIR"] = str(work_directory / "app-plot-mpl")
    code = r"""
import hashlib
import sys
from pathlib import Path
from PySide6.QtCore import QEventLoop, QSize, QTimer
from PySide6.QtWidgets import QApplication
from carnopy.app.client import WorkerClient
from carnopy.app.export_cleanup import ImageExportFinalizer
from carnopy.app.plot_preview_provider import (
    VerifiedPlotImageProvider,
    VerifiedPlotPreviewRegistry,
)
from carnopy.app.plot_staging import create_plot_staging
from carnopy.app.request_coordinator import DesktopRequestCoordinator
from carnopy.app.workspace import initialize_workspace

root = Path(sys.argv[1])
source = Path(sys.argv[2])
workspace = initialize_workspace(root / "workspace")
app = QApplication([])

def request(owner, kind, payload, *, finalizer=None):
    client = WorkerClient()
    coordinator = DesktopRequestCoordinator(client)
    outcomes = []
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.setInterval(30_000)
    timer.timeout.connect(loop.quit)
    coordinator.busy_changed.connect(lambda busy: None if busy else loop.quit())
    session = coordinator.start_request(owner, kind, payload, finalizer=finalizer)
    session.completed.connect(outcomes.append)
    timer.start()
    loop.exec()
    timer.stop()
    if coordinator.is_busy:
        cleanup_loop = QEventLoop()
        coordinator.busy_changed.connect(
            lambda busy: None if busy else cleanup_loop.quit()
        )
        client.force_stop(session.request_id)
        QTimer.singleShot(5_000, cleanup_loop.quit)
        cleanup_loop.exec()
        raise SystemExit(f"desktop worker timed out: {kind}")
    coordinator.shutdown()
    coordinator.deleteLater()
    client.deleteLater()
    app.processEvents()
    if len(outcomes) != 1:
        raise SystemExit(f"desktop worker returned no outcome: {kind}: {outcomes!r}")
    outcome = outcomes[0]
    result = outcome.result_payload
    if result is None:
        raise SystemExit(f"desktop worker failed: {kind}: {outcome.failure_payload!r}")
    return result

inspection = request("inspection", "inspect_source", {"source_path": str(source)})
lease = create_plot_staging(workspace.root)
plot = {
    "name": "installed-smoke-density",
    "kind": "property_curves",
    "property": "mass_density",
}
if inspection["summary"]["identity"]["mode"] == "property_table":
    plot["x"] = "temperature"
render_payload = {
    "workspace_path": str(workspace.root),
    "source_path": str(source),
    "inspection_revision": inspection["revision"],
    "plot_name": "installed-smoke-density",
    "format": "png",
    "plot": plot,
    "staging": lease.worker_payload(),
}
rendered = request(
    "plot",
    "render_plot",
    render_payload,
    finalizer=ImageExportFinalizer(lease),
)
image = Path(rendered["image_path"])
sidecar = Path(rendered["sidecar_path"])
for path, expected in (
    (image, rendered["image_sha256"]),
    (sidecar, rendered["sidecar_sha256"]),
):
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit(f"desktop plot artifact failed verification: {path}")
registry = VerifiedPlotPreviewRegistry()
token = registry.issue(
    workspace_identity=str(workspace.root),
    figures_root=workspace.figures,
    image_path=image,
    image_sha256=rendered["image_sha256"],
    image_format="png",
    verification_revision=rendered["sidecar_sha256"],
)
provider = VerifiedPlotImageProvider(registry)
decoded_size = QSize()
decoded = provider.requestImage(token, decoded_size, QSize())
if decoded.isNull() or decoded_size.isEmpty():
    raise SystemExit("QML plot preview provider did not decode the rendered PNG")
for name in (
    "matplotlib",
    "carnopy.visualization.plots",
    "carnopy.visualization.render",
    "carnopy.app.plot_rendering",
):
    if name in sys.modules:
        raise SystemExit(f"GUI parent imported worker rendering module: {name}")
"""
    completed = subprocess.run(
        [sys.executable, "-c", code, str(work_directory / "app-plot"), str(source)],
        cwd=work_directory,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "offscreen desktop plot smoke test failed\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )


def smoke_app_inspection(*sources: Path) -> None:
    from carnopy.app.source_inspection import inspect_for_app, resolve_table
    from carnopy.app.table_preview import preview_table

    expected_kinds = ("dataset", "preparation", "model_sweep")
    for source, expected_kind in zip(sources, expected_kinds, strict=True):
        inspection = inspect_for_app(source)
        if inspection.source_kind != expected_kind or not inspection.tables:
            raise RuntimeError(
                f"desktop inspection returned unexpected result for {source}: "
                f"{inspection.source_kind}, {inspection.tables}"
            )
        table = resolve_table(source, inspection.tables[0].table_id, inspection.revision)
        preview = preview_table(table, offset=0, limit=1)
        if preview["block_count"] > 1:
            raise RuntimeError("desktop table preview exceeded its requested limit")


def build_plot_arguments(run_directory: Path, figure: Path) -> list[str]:
    # The packaged starter intentionally emits multiple fluids. Select one
    # emitted canonical value so this request reaches the renderer boundary.
    return [
        "plot",
        str(run_directory),
        "--kind",
        "property-curves",
        "--property",
        "mass_density",
        "--fluid",
        "IsoButane",
        "--output",
        str(figure),
    ]


def build_generate_arguments(
    config: Path,
    output_root: Path,
    *,
    figures_root: Path | None = None,
) -> list[str]:
    arguments = ["generate", str(config), "--out", str(output_root)]
    if figures_root is not None:
        arguments.extend(["--figures-out", str(figures_root)])
    return arguments


def build_sweep_arguments(config: Path, output_root: Path) -> list[str]:
    return ["sweep", str(config), "--out", str(output_root)]


def build_prepare_arguments(source: Path, config: Path, output_root: Path) -> list[str]:
    return ["prepare", str(source), "--config", str(config), "--out", str(output_root)]


def add_configured_visualization(config: Path) -> None:
    with config.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(
            """
visualization:
  format: png
  plots:
    - name: density-vs-vapor-fraction
      kind: property_curves
      property: mass_density
"""
        )


def add_sweep_comparison_plots(config: Path) -> None:
    with config.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(
            """
comparison_plots:
  format: png
  plots:
    - name: propane_density_temperature_by_pressure
      kind: property_comparison
      fluid: Propane
      property: mass_density
      x: temperature
      group_by: pressure
      models: [heos, pr, srk]
    - name: propane_density_relative_delta
      kind: property_delta
      fluid: Propane
      property: mass_density
      x: temperature
      group_by: pressure
      models: [pr, srk]
      delta_metric: signed_relative_difference
"""
        )


def enable_preparation_array_exports(config: Path) -> None:
    text = config.read_text(encoding="utf-8")
    old = "outputs:\n  formats: [parquet]\n"
    new = """outputs:
  parquet: true
  arrays:
    formats: [npy, npz, safetensors]
    dtype: float32
    include_auxiliary: false
"""
    if old not in text:
        raise RuntimeError("preparation template does not contain the expected outputs block")
    config.write_text(text.replace(old, new), encoding="utf-8")


def enable_preparation_baseline_diagnostics(config: Path) -> None:
    text = config.read_text(encoding="utf-8")
    marker = "outputs:\n"
    if marker not in text:
        raise RuntimeError("preparation template does not contain the expected outputs block")
    block = """
scenarios:
  - name: installed_baseline
    kind: shuffle
    seed: 42
    partitions:
      train: 0.7
      test: 0.3

quality:
  baseline_diagnostics:
    models: [dummy_mean, ridge]
    random_seed: 42
    ridge_alpha: 1.0
    histogram_max_iterations: 20
"""
    config.write_text(text.replace(marker, f"{block}\n{marker}", 1), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test an installed Carnopy distribution.")
    parser.add_argument("--work-directory", type=Path, required=True)
    parser.add_argument("--with-visualization", action="store_true")
    parser.add_argument("--with-ml-exports", action="store_true")
    parser.add_argument("--with-analysis", action="store_true")
    parser.add_argument("--with-app", action="store_true")
    parser.add_argument("--expected-version")
    arguments = parser.parse_args()

    work_directory = arguments.work_directory.resolve()
    work_directory.mkdir(parents=True, exist_ok=False)
    version = run_command(["--version"], cwd=work_directory)
    expected_output = (
        f"carnopy {arguments.expected_version}\n"
        if arguments.expected_version is not None
        else None
    )
    if expected_output is not None and version.stdout != expected_output:
        raise RuntimeError(
            f"installed version output {version.stdout!r} does not match {expected_output!r}"
        )
    if expected_output is None and not version.stdout.startswith("carnopy "):
        raise RuntimeError(f"unexpected version output: {version.stdout!r}")
    run_command(["--help"], cwd=work_directory)
    run_command(["sweep", "--help"], cwd=work_directory)
    run_command(["prepare", "--help"], cwd=work_directory)
    run_command(["properties"], cwd=work_directory)
    app_help = run_app_command(["--help"], cwd=work_directory)
    if "Open the Carnopy desktop application." not in app_help.stdout:
        raise RuntimeError(f"unexpected carnopy-app help output: {app_help.stdout!r}")
    app_version = run_app_command(["--version"], cwd=work_directory)
    expected_app_version = version.stdout.replace("carnopy ", "carnopy-app ", 1)
    if app_version.stdout != expected_app_version:
        raise RuntimeError(f"unexpected carnopy-app version output: {app_version.stdout!r}")
    gui_help = run_gui_command(["--help"], cwd=work_directory)
    if "Open the Carnopy desktop application." not in gui_help.stdout:
        raise RuntimeError(f"unexpected carnopy-gui help output: {gui_help.stdout!r}")
    gui_version = run_gui_command(["--version"], cwd=work_directory)
    expected_gui_version = version.stdout.replace("carnopy ", "carnopy-gui ", 1)
    if gui_version.stdout != expected_gui_version:
        raise RuntimeError(f"unexpected carnopy-gui version output: {gui_version.stdout!r}")

    config = work_directory / "config.yaml"
    run_command(
        ["init", "vapor_mass_fraction_table", str(config)],
        cwd=work_directory,
    )
    matplotlib_available = importlib.util.find_spec("matplotlib") is not None
    safetensors_available = importlib.util.find_spec("safetensors") is not None
    pyside_available = importlib.util.find_spec("PySide6") is not None
    sklearn_available = importlib.util.find_spec("sklearn") is not None
    if not arguments.with_ml_exports and safetensors_available:
        raise RuntimeError("base distribution unexpectedly includes SafeTensors")
    if arguments.with_ml_exports and not safetensors_available:
        raise RuntimeError("ML export smoke test requires SafeTensors")
    if not arguments.with_analysis and sklearn_available:
        raise RuntimeError("distribution unexpectedly includes scikit-learn")
    if arguments.with_analysis and not sklearn_available:
        raise RuntimeError("analysis smoke test requires scikit-learn")
    if arguments.with_app:
        if not pyside_available:
            raise RuntimeError("desktop application smoke test requires PySide6")
        smoke_public_qml_apps(work_directory)
    else:
        if pyside_available:
            raise RuntimeError("distribution unexpectedly includes PySide6")
        failed_app = run_app_command([], cwd=work_directory, expected_code=1)
        if failed_app.stderr != MISSING_APP_EXTRA:
            raise RuntimeError(f"unexpected missing-app error:\n{failed_app.stderr}")
        failed_gui = run_gui_command([], cwd=work_directory, expected_code=1)
        if failed_gui.stderr != MISSING_APP_EXTRA:
            raise RuntimeError(f"unexpected missing-gui error:\n{failed_gui.stderr}")
    command_environment: dict[str, str] | None = None
    figures_root: Path | None = None
    if arguments.with_visualization:
        if not matplotlib_available:
            raise RuntimeError("visualization smoke test requires Matplotlib")
        add_configured_visualization(config)
        figures_root = work_directory / "configured-figures"
        command_environment = os.environ.copy()
        command_environment["MPLBACKEND"] = "Agg"
        command_environment["MPLCONFIGDIR"] = str(work_directory / "mpl-config")

    run_command(
        ["validate", str(config)],
        cwd=work_directory,
        environment=command_environment,
    )
    output_root = work_directory / "runs"
    run_command(
        build_generate_arguments(
            config,
            output_root,
            figures_root=figures_root,
        ),
        cwd=work_directory,
        environment=command_environment,
    )
    runs = [path for path in output_root.iterdir() if path.is_dir()]
    if len(runs) != 1:
        raise RuntimeError(f"expected one generated run, found {runs}")
    reference = runs[0] / "config.reference.yaml"
    if not reference.is_file() or "Carnopy configuration reference" not in reference.read_text(
        encoding="utf-8"
    ):
        raise RuntimeError("generated run does not contain the packaged configuration reference")
    inspection = run_command(["inspect", str(runs[0])], cwd=work_directory)
    if "Compatible plot kinds:" not in inspection.stdout:
        raise RuntimeError(
            f"installed inspect command returned unexpected output:\n{inspection.stdout}"
        )

    preparation_config = work_directory / "preparation.yaml"
    run_command(["init", "preparation", str(preparation_config)], cwd=work_directory)
    if arguments.with_ml_exports:
        enable_preparation_array_exports(preparation_config)
    if arguments.with_analysis:
        enable_preparation_baseline_diagnostics(preparation_config)
    prepared_root = work_directory / "prepared"
    run_command(
        build_prepare_arguments(runs[0], preparation_config, prepared_root),
        cwd=work_directory,
    )
    prepared_bundles = [path for path in prepared_root.iterdir() if path.is_dir()]
    if len(prepared_bundles) != 1:
        raise RuntimeError(f"expected one preparation bundle, found {prepared_bundles}")
    prepared_bundle = prepared_bundles[0]
    if not all(
        path.is_file()
        for path in (
            prepared_bundle / "manifest.json",
            prepared_bundle / "diagnostics.json",
            prepared_bundle / "dataset_card.md",
            prepared_bundle / "data" / "table.parquet",
            prepared_bundle / "data" / "provenance.parquet",
            prepared_bundle / "data" / "diagnostics.parquet",
            prepared_bundle / "data" / "exclusions.parquet",
        )
    ):
        raise RuntimeError("preparation smoke test did not create required artifacts")
    arrays_directory = prepared_bundle / "data" / "arrays"
    if arguments.with_ml_exports:
        if not all(
            path.is_file()
            for path in (
                arrays_directory / "features.float32.npy",
                arrays_directory / "targets.float32.npy",
                arrays_directory / "dataset.float32.npz",
                arrays_directory / "dataset.float32.safetensors",
            )
        ):
            raise RuntimeError("ML export smoke test did not create array exports")
    elif arrays_directory.exists():
        raise RuntimeError("base preparation smoke test unexpectedly created array exports")
    preparation_inspection = run_command(["inspect", str(prepared_bundle)], cwd=work_directory)
    if "Source kind: preparation bundle" not in preparation_inspection.stdout:
        raise RuntimeError("preparation inspect smoke test returned unexpected output")
    quality_report = json.loads(
        prepared_bundle.joinpath("quality_report.json").read_text(encoding="utf-8")
    )
    if arguments.with_analysis:
        if quality_report["baseline_diagnostics"]["status"] != "completed":
            raise RuntimeError("analysis smoke test did not complete baseline diagnostics")
    elif quality_report["baseline_diagnostics"]["status"] != "not_requested":
        raise RuntimeError("base preparation unexpectedly requested baseline diagnostics")

    figure = work_directory / "density.png"
    plot_arguments = build_plot_arguments(runs[0], figure)
    if arguments.with_visualization:
        assert figures_root is not None
        configured_directory = figures_root / runs[0].name
        configured_image = configured_directory / "density-vs-vapor-fraction.png"
        configured_sidecar = configured_directory / "density-vs-vapor-fraction.plot.json"
        configured_report = configured_directory / "visualization-report.json"
        if not all(
            path.is_file()
            for path in (
                configured_image,
                configured_sidecar,
                configured_report,
            )
        ):
            raise RuntimeError(
                "configured visualization smoke test did not create image, sidecar, and report"
            )
        report = json.loads(configured_report.read_text(encoding="utf-8"))
        if report["status"] != "completed" or report["succeeded_plot_count"] != 1:
            raise RuntimeError(f"unexpected configured visualization report: {report}")

        run_command(
            plot_arguments,
            cwd=work_directory,
            environment=command_environment,
        )
        if not figure.is_file() or not figure.with_suffix(".plot.json").is_file():
            raise RuntimeError("plot smoke test did not create image and sidecar")
        batch_root = work_directory / "batch-figures"
        run_command(
            [
                "plot",
                str(runs[0]),
                "--config",
                str(config),
                "--figures-out",
                str(batch_root),
            ],
            cwd=work_directory,
            environment=command_environment,
        )
        batch_directory = batch_root / runs[0].name
        if not batch_directory.joinpath("visualization-report.json").is_file():
            raise RuntimeError("batch visualization smoke test did not create its report")
    else:
        if matplotlib_available:
            raise RuntimeError("base distribution unexpectedly includes Matplotlib")
        failed = run_command(plot_arguments, cwd=work_directory, expected_code=1)
        combined = failed.stdout + failed.stderr
        if "Plotting requires the visualization extra." not in combined:
            raise RuntimeError(f"unexpected missing-visualization error:\n{combined}")

    sweep_config = work_directory / "sweep.yaml"
    run_command(["init", "model_sweep", str(sweep_config)], cwd=work_directory)
    sweep_text = sweep_config.read_text(encoding="utf-8")
    if "\ncomparison_plots:" in sweep_text:
        raise RuntimeError("model_sweep starter must not contain active comparison_plots")
    sweep_root = work_directory / "sweeps"
    sweep_environment = command_environment
    if arguments.with_visualization:
        add_sweep_comparison_plots(sweep_config)
        sweep_environment = os.environ.copy()
        sweep_environment["MPLBACKEND"] = "Agg"
        sweep_environment["MPLCONFIGDIR"] = str(work_directory / "sweep-mpl-config")
    sweep_completed = run_command(
        build_sweep_arguments(sweep_config, sweep_root),
        cwd=work_directory,
        environment=sweep_environment,
    )
    sweep_bundles = [path for path in sweep_root.iterdir() if path.is_dir()]
    if len(sweep_bundles) != 1:
        raise RuntimeError(f"expected one generated sweep bundle, found {sweep_bundles}")
    sweep_bundle = sweep_bundles[0]
    if not (sweep_bundle / "comparison" / "values.parquet").is_file():
        raise RuntimeError("model sweep smoke test did not create comparison values")
    if not (sweep_bundle / "comparison" / "deltas.parquet").is_file():
        raise RuntimeError("model sweep smoke test did not create comparison deltas")
    sweep_inspection = run_command(["inspect", str(sweep_bundle)], cwd=work_directory)
    if "Source kind: model-sweep bundle" not in sweep_inspection.stdout:
        raise RuntimeError("sweep inspect smoke test returned unexpected output")
    if arguments.with_visualization:
        comparison_directory = sweep_bundle / "comparison_plots"
        if not all(
            path.is_file()
            for path in (
                comparison_directory / "propane_density_temperature_by_pressure.png",
                comparison_directory / "propane_density_temperature_by_pressure.plot.json",
                comparison_directory / "propane_density_relative_delta.png",
                comparison_directory / "propane_density_relative_delta.plot.json",
                comparison_directory / "comparison-report.json",
            )
        ):
            raise RuntimeError("comparison-plot sweep smoke test did not create all artifacts")
    elif (sweep_bundle / "comparison_plots").exists():
        raise RuntimeError("no-plot model sweep unexpectedly created comparison plots")
    else:
        if "Comparison plots: not configured" not in sweep_completed.stdout:
            raise RuntimeError("no-plot model sweep did not report absent comparison plots")
        sweep_with_plots = work_directory / "sweep-with-plots.yaml"
        run_command(["init", "model_sweep", str(sweep_with_plots)], cwd=work_directory)
        add_sweep_comparison_plots(sweep_with_plots)
        failed_sweep = run_command(
            build_sweep_arguments(sweep_with_plots, work_directory / "sweeps-with-plots"),
            cwd=work_directory,
            expected_code=1,
        )
        combined = failed_sweep.stdout + failed_sweep.stderr
        if "Plotting requires the visualization extra." not in combined:
            raise RuntimeError(f"unexpected missing-visualization sweep error:\n{combined}")

    if arguments.with_app:
        smoke_app_inspection(runs[0], prepared_bundle, sweep_bundle)
        smoke_app_plot(work_directory, runs[0])

    print(f"Installed Carnopy smoke test passed: {version.stdout.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
