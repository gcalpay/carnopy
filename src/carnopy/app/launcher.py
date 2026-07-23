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


def build_parser(program: str = "carnopy-app") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=program,
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
    parser.add_argument("--version", action="version", version=f"{program} {__version__}")
    return parser


def configure_qt_platform(requested: str) -> None:
    """Select the requested Qt platform before importing PySide6."""
    if requested != "auto":
        os.environ["QT_QPA_PLATFORM"] = requested
        return
    if "QT_QPA_PLATFORM" not in os.environ and _wslg_available():
        os.environ["QT_QPA_PLATFORM"] = "xcb"


def _wslg_available() -> bool:
    return bool(
        (os.environ.get("WSL_INTEROP") or os.environ.get("WSL_DISTRO_NAME"))
        and os.environ.get("WSL2_GUI_APPS_ENABLED") == "1"
        and os.environ.get("DISPLAY")
        and os.environ.get("WAYLAND_DISPLAY")
    )


def main(argv: Sequence[str] | None = None, *, program: str = "carnopy-app") -> int:
    arguments = build_parser(program).parse_args(argv)
    configure_qt_platform(arguments.qt_platform)
    try:
        from carnopy.app.window import run_application
    except ModuleNotFoundError as exc:
        if exc.name != "PySide6":
            raise
        print(MISSING_APP_EXTRA, file=sys.stderr, end="")
        return 1
    return run_application(arguments.workspace)


def main_gui(argv: Sequence[str] | None = None) -> int:
    return main(argv, program="carnopy-gui")


if __name__ == "__main__":
    raise SystemExit(main())
