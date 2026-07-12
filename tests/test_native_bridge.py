from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE_ROOT = ROOT / "native" / "carnopy-vtk-bridge"


def test_native_bridge_requests_only_its_direct_vtk_modules() -> None:
    cmake = (BRIDGE_ROOT / "CMakeLists.txt").read_text(encoding="utf-8")

    assert 'set(VTK_BUILD_ALL_MODULES OFF CACHE BOOL "" FORCE)' in cmake
    for group in ("Qt", "Rendering", "StandAlone"):
        assert f'set(VTK_GROUP_ENABLE_{group} DONT_WANT CACHE STRING "" FORCE)' in cmake

    requested = set(
        re.findall(
            r"set\(VTK_MODULE_ENABLE_VTK_([A-Za-z0-9]+) YES CACHE STRING \"\" FORCE\)",
            cmake,
        )
    )
    assert requested == {"FiltersSources", "GUISupportQtQuick"}


def test_qml_registered_bridge_type_remains_subclassable() -> None:
    source = (BRIDGE_ROOT / "src" / "native.cpp").read_text(encoding="utf-8")

    assert "class QualificationCone : public QQuickVTKItem" in source
    assert "class QualificationCone final" not in source
    assert "qmlRegisterType<QualificationCone>" in source


def test_qt_runtime_probe_precedes_bridge_imports() -> None:
    qualification = (BRIDGE_ROOT / "tests" / "qualification.py").read_text(encoding="utf-8")

    assert 'subparsers.add_parser("smoke-qt-runtime")' in qualification
    assert "def smoke_qt_runtime()" in qualification
    assert "_verify_qt_runtime_libraries()" in qualification
    for library in (
        "libQt6DBus.so.6",
        "libQt6Network.so.6",
        "libQt6Qml.so.6",
        "libQt6Quick.so.6",
    ):
        assert f'"{library}"' in qualification
    assert qualification.index("def smoke_qt_runtime()") < qualification.index(
        "def _verify_installed_layout()"
    )
