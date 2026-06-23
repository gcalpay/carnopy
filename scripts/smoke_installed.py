from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


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


def build_plot_arguments(run_directory: Path, figure: Path) -> list[str]:
    return [
        "plot",
        str(run_directory),
        "--kind",
        "property-curves",
        "--property",
        "mass_density",
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test an installed Carnopy distribution.")
    parser.add_argument("--work-directory", type=Path, required=True)
    parser.add_argument("--with-visualization", action="store_true")
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
    run_command(["properties"], cwd=work_directory)

    config = work_directory / "config.yaml"
    run_command(
        ["init", "vapor_mass_fraction_table", str(config)],
        cwd=work_directory,
    )
    matplotlib_available = importlib.util.find_spec("matplotlib") is not None
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

    print(f"Installed Carnopy smoke test passed: {version.stdout.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
