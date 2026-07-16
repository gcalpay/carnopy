from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtQml import QQmlError
from PySide6.QtWidgets import QApplication

from carnopy.app.application_identity import APPLICATION_NAME, ORGANIZATION_NAME
from carnopy.app.qml_resources import (
    MANDATORY_ICON_FILES,
    MANDATORY_QML_FILES,
    MANIFEST_PATH,
    manifest_records,
    packaged_path,
    verify_packaged_resources,
)
from carnopy.app.qml_runtime import QmlWarningCapture, create_qml_runtime

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def application() -> QApplication:
    existing = QApplication.instance()
    application = existing if isinstance(existing, QApplication) else QApplication([])
    return application


def test_packaged_resource_manifest_matches_every_installed_byte() -> None:
    records = verify_packaged_resources()
    assert records == manifest_records()
    assert {record.owner for record in records} == {"Carnopy", "IBM Plex", "Lucide"}
    assert len({record.packaged_path for record in records}) == len(records)
    assert len(records) == 28

    manifest = json.loads(packaged_path(MANIFEST_PATH).read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["branding"]["sha256"] == (
        "7c01f9c7f8fe12f98acc2063396a9af615a5a6eba30e995e4f86bc4fd8155fcc"
    )
    projects = {project["name"]: project for project in manifest["third_party_projects"]}
    assert projects["IBM Plex"]["revision"] == "2f9ba1b25957d958db71a849e85d72e3ecfb845a"
    assert projects["IBM Plex"]["license_expression"] == "OFL-1.1"
    assert projects["Lucide"]["revision"] == ("1.24.0 (b5b5d95933790a311aa6b7ed232fc8469934acdf)")
    assert projects["Lucide"]["license_expression"] == "ISC AND MIT"
    assert {
        f"resources/{record.packaged_path}"
        for record in records
        if record.owner == "Lucide" and record.packaged_path.startswith("icons/")
    } == set(MANDATORY_ICON_FILES)
    assert all(packaged_path(path).is_file() for path in MANDATORY_QML_FILES)


def test_private_qml_runtime_loads_one_warning_free_root(
    application: QApplication,
    tmp_path: Path,
) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    workspace = tmp_path / "workspace"
    runtime = create_qml_runtime(
        settings=settings,
        initial_workspace=workspace,
        application_arguments=[],
    )
    roots = runtime.engine.rootObjects()
    assert len(roots) == 1
    root = roots[0]
    assert root.objectName() == "carnopyQmlRoot"
    assert root.property("runtimeReady") is True
    assert root.property("desktopController") is runtime.controller
    assert root.property("qmlSettings") is runtime.controller.qml_settings
    assert root.property("startupWorkspace") == str(workspace)
    assert runtime.warning_capture.startup_warnings == ()
    assert runtime.warning_capture.runtime_warnings == ()
    assert QCoreApplication.organizationName() == ORGANIZATION_NAME
    assert QCoreApplication.applicationName() == APPLICATION_NAME
    assert runtime.close()
    assert runtime._font_ids == []
    application.processEvents()


def test_qml_warning_capture_distinguishes_startup_and_later_warnings(
    application: QApplication,
) -> None:
    capture = QmlWarningCapture()
    emitted: list[str] = []
    capture.runtime_warning.connect(emitted.append)
    startup = QQmlError()
    startup.setDescription("startup binding warning")
    capture.record([startup])
    capture.finish_startup()
    runtime = QQmlError()
    runtime.setDescription("later binding warning")
    capture.record([runtime])
    application.processEvents()

    assert capture.startup_warnings == ("<Unknown File>: startup binding warning",)
    assert capture.runtime_warnings == ("<Unknown File>: later binding warning",)
    assert emitted == ["<Unknown File>: later binding warning"]


def test_qml_resource_and_runtime_imports_remain_scientifically_isolated() -> None:
    code = """
import sys
import carnopy.app.qml_resources
if "PySide6" in sys.modules:
    raise SystemExit("resource lookup imported Qt")
import carnopy.app.qml_runtime
for name in ("CoolProp", "numpy", "pandas", "pyarrow", "matplotlib"):
    if name in sys.modules:
        raise SystemExit(f"QML runtime imported scientific dependency: {name}")
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_private_qml_launcher_smoke_exits_cleanly() -> None:
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    completed = subprocess.run(
        [sys.executable, "-m", "carnopy.app.qml_launcher", "--smoke-test"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""


def test_qml_sources_pass_non_writing_qt_tooling() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_qml.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout == "QML checks passed for 15 file(s).\n"
