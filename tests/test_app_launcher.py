from __future__ import annotations

import builtins
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from carnopy._version import __version__
from carnopy.app import qml_launcher


@pytest.mark.parametrize(
    ("entrypoint", "program"),
    [("main_app", "carnopy-app"), ("main_gui", "carnopy-gui")],
)
@pytest.mark.parametrize("argument", ["--help", "--version"])
def test_launcher_help_and_version_do_not_import_pyside(
    argument: str,
    entrypoint: str,
    program: str,
) -> None:
    code = f"""
import sys
from carnopy.app.qml_launcher import {entrypoint}
try:
    {entrypoint}([{argument!r}])
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
        assert completed.stdout == f"{program} {__version__}\n"


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
        if name == "carnopy.app.qml_runtime":
            raise ModuleNotFoundError("No module named 'PySide6'", name="PySide6")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", missing_pyside)

    assert qml_launcher.main_app([]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == qml_launcher.MISSING_APP_EXTRA


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="app extra is not installed"
)
@pytest.mark.parametrize("entrypoint", [qml_launcher.main_app, qml_launcher.main_gui])
def test_launcher_passes_workspace_to_qml_application(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entrypoint: object,
) -> None:
    import carnopy.app.qml_runtime

    received: list[tuple[Path | None, bool]] = []
    monkeypatch.setattr(
        carnopy.app.qml_runtime,
        "run_qml_application",
        lambda workspace, *, smoke_test: received.append((workspace, smoke_test)) or 0,
    )

    assert callable(entrypoint)
    assert entrypoint(["--workspace", str(tmp_path)]) == 0
    assert received == [(tmp_path, False)]


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="app extra is not installed"
)
@pytest.mark.parametrize("entrypoint", ["main_gui", "main_app"])
def test_public_qml_launcher_smoke_exits_cleanly(entrypoint: str) -> None:
    code = f"""
from carnopy.app.qml_launcher import {entrypoint}
raise SystemExit({entrypoint}(["--smoke-test"]))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        timeout=30,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""


@pytest.mark.parametrize(
    ("argument", "initial", "expected"),
    [
        ("auto", "wayland", "wayland"),
        ("xcb", "wayland", "xcb"),
        ("wayland", "xcb", "wayland"),
    ],
)
def test_launcher_applies_explicit_platform_before_importing_pyside(
    argument: str,
    initial: str,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__
    observed: list[str | None] = []

    def inspect_platform(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "carnopy.app.qml_runtime":
            observed.append(os.environ.get("QT_QPA_PLATFORM"))
            return SimpleNamespace(
                QmlStartupError=RuntimeError,
                run_qml_application=lambda _workspace, *, smoke_test: 0,
            )
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setenv("QT_QPA_PLATFORM", initial)
    monkeypatch.setattr(builtins, "__import__", inspect_platform)

    assert qml_launcher.main_app(["--qt-platform", argument]) == 0
    assert observed == [expected]


def test_auto_platform_prefers_xcb_for_wslg_native_dialogs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.setenv("WSL_INTEROP", "/run/WSL/test_interop")
    monkeypatch.setenv("WSL2_GUI_APPS_ENABLED", "1")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")

    qml_launcher.configure_qt_platform("auto")

    assert os.environ["QT_QPA_PLATFORM"] == "xcb"


def test_auto_platform_preserves_explicit_environment_on_wslg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "wayland")
    monkeypatch.setenv("WSL_INTEROP", "/run/WSL/test_interop")
    monkeypatch.setenv("WSL2_GUI_APPS_ENABLED", "1")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")

    qml_launcher.configure_qt_platform("auto")

    assert os.environ["QT_QPA_PLATFORM"] == "wayland"


def test_auto_platform_leaves_native_linux_selection_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.delenv("WSL_INTEROP", raising=False)
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    monkeypatch.setenv("WSL2_GUI_APPS_ENABLED", "1")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")

    qml_launcher.configure_qt_platform("auto")

    assert "QT_QPA_PLATFORM" not in os.environ
