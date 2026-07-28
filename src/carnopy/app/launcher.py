from __future__ import annotations

import sys
from collections.abc import Sequence

from carnopy.app.qml_launcher import MISSING_APP_EXTRA, build_parser, configure_qt_platform


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
