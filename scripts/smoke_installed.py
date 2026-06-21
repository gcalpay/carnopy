from __future__ import annotations

import argparse
import importlib.util
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
    run_command(["validate", str(config)], cwd=work_directory)
    output_root = work_directory / "runs"
    run_command(
        ["generate", str(config), "--out", str(output_root)],
        cwd=work_directory,
    )
    runs = [path for path in output_root.iterdir() if path.is_dir()]
    if len(runs) != 1:
        raise RuntimeError(f"expected one generated run, found {runs}")

    matplotlib_available = importlib.util.find_spec("matplotlib") is not None
    figure = work_directory / "density.png"
    plot_arguments = build_plot_arguments(runs[0], figure)
    if arguments.with_visualization:
        if not matplotlib_available:
            raise RuntimeError("visualization smoke test requires Matplotlib")
        environment = os.environ.copy()
        environment["MPLBACKEND"] = "Agg"
        environment["MPLCONFIGDIR"] = str(work_directory / "mpl-config")
        run_command(plot_arguments, cwd=work_directory, environment=environment)
        if not figure.is_file() or not figure.with_suffix(".plot.json").is_file():
            raise RuntimeError("plot smoke test did not create image and sidecar")
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
