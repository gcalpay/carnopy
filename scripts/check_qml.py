from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QML_ROOT = ROOT / "src" / "carnopy" / "app" / "qml"


class QmlCheckError(RuntimeError):
    """Raised when QML tooling reports a source problem."""


def qml_tool(name: str) -> Path:
    spec = importlib.util.find_spec("PySide6")
    if spec is None or spec.origin is None:
        raise QmlCheckError("PySide6 is required to check QML sources")
    suffix = ".exe" if sys.platform == "win32" else ""
    path = Path(spec.origin).resolve().parent / f"{name}{suffix}"
    if not path.is_file():
        raise QmlCheckError(f"PySide6 does not provide the required {name} tool at {path}")
    return path


def qml_files(root: Path = QML_ROOT) -> tuple[Path, ...]:
    files = tuple(sorted(root.rglob("*.qml")))
    if not files:
        raise QmlCheckError(f"no QML files found under {root}")
    return files


def _run(arguments: list[str]) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(arguments, cwd=ROOT, capture_output=True, check=False)
    if completed.returncode != 0:
        output = (completed.stdout + completed.stderr).decode("utf-8", errors="replace")
        raise QmlCheckError(f"QML tool failed ({' '.join(arguments)}):\n{output}")
    return completed


def check_format(files: tuple[Path, ...]) -> None:
    formatter = qml_tool("qmlformat")
    for path in files:
        completed = _run(
            [
                str(formatter),
                "--ignore-settings",
                "--indent-width",
                "4",
                "--column-width",
                "100",
                "--newline",
                "unix",
                str(path),
            ]
        )
        if completed.stdout != path.read_bytes():
            raise QmlCheckError(f"QML source is not qmlformat-clean: {path.relative_to(ROOT)}")


def check_lint(files: tuple[Path, ...], root: Path = QML_ROOT) -> None:
    lint = qml_tool("qmllint")
    _run(
        [
            str(lint),
            "--ignore-settings",
            "-I",
            str(root),
            "-W",
            "0",
            *(str(path) for path in files),
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check packaged Carnopy QML without writing it.")
    parser.parse_args(argv)
    files = qml_files()
    check_format(files)
    check_lint(files)
    print(f"QML checks passed for {len(files)} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
