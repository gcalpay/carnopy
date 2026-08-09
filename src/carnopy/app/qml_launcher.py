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

WSLG_SOFTWARE_RENDERING = {
    "LIBGL_ALWAYS_SOFTWARE": "1",
    "QSG_RHI_BACKEND": "opengl",
    "QT_OPENGL": "software",
}


def build_parser(program: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=program,
        description="Open the Carnopy desktop application.",
    )
    parser.add_argument("--workspace", type=Path, help="Initialized Carnopy workspace to open.")
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
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    return parser


def configure_qt_platform(requested: str) -> None:
    """Select the requested Qt platform before importing PySide6."""
    if requested != "auto":
        os.environ["QT_QPA_PLATFORM"] = requested
        return
    if "QT_QPA_PLATFORM" not in os.environ and _wslg_available():
        os.environ["QT_QPA_PLATFORM"] = "xcb"
        # The repository's native Qt qualification uses this deterministic
        # XCB path because WSLg/Xwayland may not expose a usable GBM device.
        # Respect explicit caller overrides for all three variables.
        for name, value in WSLG_SOFTWARE_RENDERING.items():
            os.environ.setdefault(name, value)


def _wslg_available() -> bool:
    return bool(
        (os.environ.get("WSL_INTEROP") or os.environ.get("WSL_DISTRO_NAME"))
        and os.environ.get("WSL2_GUI_APPS_ENABLED") == "1"
        and os.environ.get("DISPLAY")
        and os.environ.get("WAYLAND_DISPLAY")
    )


def _run(argv: Sequence[str] | None, *, program: str) -> int:
    arguments = build_parser(program).parse_args(argv)
    configure_qt_platform(arguments.qt_platform)
    try:
        from carnopy.app.qml_runtime import QmlStartupError, run_qml_application
    except ModuleNotFoundError as exc:
        if exc.name != "PySide6":
            raise
        print(MISSING_APP_EXTRA, file=sys.stderr, end="")
        return 1
    try:
        return run_qml_application(arguments.workspace, smoke_test=arguments.smoke_test)
    except QmlStartupError as exc:
        print(f"Carnopy QML startup failed: {exc}", file=sys.stderr)
        return 1


def main_gui(argv: Sequence[str] | None = None) -> int:
    return _run(argv, program="carnopy-gui")


def main_app(argv: Sequence[str] | None = None) -> int:
    return _run(argv, program="carnopy-app")


def main(argv: Sequence[str] | None = None) -> int:
    return _run(argv, program="python -m carnopy.app.qml_launcher")


if __name__ == "__main__":
    raise SystemExit(main())
