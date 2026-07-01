from __future__ import annotations

import builtins
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from carnopy._version import __version__
from carnopy.app import launcher


@pytest.mark.parametrize("argument", ["--help", "--version"])
def test_launcher_help_and_version_do_not_import_pyside(argument: str) -> None:
    code = f"""
import sys
from carnopy.app.launcher import main
try:
    main([{argument!r}])
except SystemExit as exc:
    if exc.code != 0:
        raise
if any(name == "PySide6" or name.startswith("PySide6.") for name in sys.modules):
    raise SystemExit("PySide6 was imported")
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    if argument == "--version":
        assert completed.stdout == f"carnopy-app {__version__}\n"


def test_launcher_reports_exact_missing_app_extra(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    original_import = builtins.__import__

    def missing_pyside(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "carnopy.app.window":
            raise ModuleNotFoundError("No module named 'PySide6'", name="PySide6")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", missing_pyside)

    assert launcher.main([]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == launcher.MISSING_APP_EXTRA


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="app extra is not installed"
)
def test_launcher_passes_workspace_to_application(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import carnopy.app.window

    received: list[Path | None] = []
    monkeypatch.setattr(
        carnopy.app.window,
        "run_application",
        lambda workspace: received.append(workspace) or 0,
    )

    assert launcher.main(["--workspace", str(tmp_path)]) == 0
    assert received == [tmp_path]
