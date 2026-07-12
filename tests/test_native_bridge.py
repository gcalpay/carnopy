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
