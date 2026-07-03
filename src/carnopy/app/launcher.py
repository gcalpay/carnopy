from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from carnopy._version import __version__

MISSING_APP_EXTRA = """Carnopy desktop application requires the app extra.

With pip:
  python -m pip install "carnopy[app]"

With uv:
  uv tool install --force "carnopy[app]"
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="carnopy-app",
        description="Open the Carnopy desktop application.",
    )
    parser.add_argument("--workspace", type=Path, help="Workspace to open or initialize.")
    parser.add_argument(
        "--qt-platform",
        choices=("auto", "xcb", "wayland"),
        default="auto",
        help=(
            "Qt platform integration. Use xcb as a WSLg fallback when native "
            "Wayland popups do not dismiss correctly."
        ),
    )
    parser.add_argument("--version", action="version", version=f"carnopy-app {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.qt_platform != "auto":
        os.environ["QT_QPA_PLATFORM"] = arguments.qt_platform
    try:
        from carnopy.app.window import run_application
    except ModuleNotFoundError as exc:
        if exc.name != "PySide6":
            raise
        print(MISSING_APP_EXTRA, file=sys.stderr, end="")
        return 1
    return run_application(arguments.workspace)


if __name__ == "__main__":
    raise SystemExit(main())
