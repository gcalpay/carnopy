from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from carnopy.app.launcher import MISSING_APP_EXTRA, build_parser, configure_qt_platform


def build_private_parser() -> argparse.ArgumentParser:
    parser = build_parser("python -m carnopy.app.qml_launcher")
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_private_parser().parse_args(argv)
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


if __name__ == "__main__":
    raise SystemExit(main())
