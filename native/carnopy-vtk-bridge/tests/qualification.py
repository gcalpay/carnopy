from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
import zipfile
from collections.abc import Callable
from email.parser import BytesParser
from importlib import import_module, metadata
from itertools import product
from pathlib import Path
from types import ModuleType

NAME = "carnopy-vtk-bridge"
VERSION = "0.1.0a5"
PACKAGE = "carnopy_vtk_bridge"
UNSET_ENVIRONMENT_VARIABLES = (
    "CMAKE_ARGS",
    "CMAKE_BUILD_PARALLEL_LEVEL",
    "CMAKE_GENERATOR",
    "CMAKE_PREFIX_PATH",
    "LD_LIBRARY_PATH",
    "PYTHONHOME",
    "PYTHONPATH",
    "QML2_IMPORT_PATH",
    "QML_IMPORT_PATH",
    "QTDIR",
    "QT_PLUGIN_PATH",
    "Qt6_DIR",
)


def _wheel_filename_tags(wheel_path: Path) -> set[str]:
    assert wheel_path.name.endswith(".whl"), wheel_path.name
    parts = wheel_path.name.removesuffix(".whl").split("-")
    assert len(parts) in {5, 6}, f"invalid wheel filename: {wheel_path.name}"
    assert parts[0] == PACKAGE, parts[0]
    assert parts[1] == VERSION, parts[1]
    if len(parts) == 6:
        assert re.fullmatch(r"[0-9][0-9A-Za-z_]*", parts[2]), parts[2]

    python_tags = parts[-3].split(".")
    abi_tags = parts[-2].split(".")
    platform_tags = parts[-1].split(".")
    assert python_tags == ["cp312"], python_tags
    assert abi_tags == ["cp312"], abi_tags
    assert platform_tags and all(tag and tag != "any" for tag in platform_tags), platform_tags
    return {
        f"{python_tag}-{abi_tag}-{platform_tag}"
        for python_tag, abi_tag, platform_tag in product(
            python_tags,
            abi_tags,
            platform_tags,
        )
    }


def inspect_wheel(wheel_path: Path) -> None:
    assert wheel_path.is_file(), f"wheel does not exist: {wheel_path}"
    filename_tags = _wheel_filename_tags(wheel_path)
    with zipfile.ZipFile(wheel_path) as wheel:
        members = wheel.namelist()
        names = set(members)
        assert len(members) == len(names), "wheel contains duplicate members"
        metadata_paths = [name for name in names if name.endswith(".dist-info/METADATA")]
        wheel_paths = [name for name in names if name.endswith(".dist-info/WHEEL")]
        assert len(metadata_paths) == 1, metadata_paths
        assert len(wheel_paths) == 1, wheel_paths

        dist_info = metadata_paths[0].rsplit("/", 1)[0]
        assert dist_info == f"{PACKAGE}-{VERSION}.dist-info", dist_info
        assert wheel_paths[0] == f"{dist_info}/WHEEL"
        native_paths = [
            name
            for name in names
            if name.startswith(f"{PACKAGE}/_native.") and name.endswith(".so")
        ]
        assert len(native_paths) == 1, native_paths

        expected = {
            f"{PACKAGE}/__init__.py",
            native_paths[0],
            f"{dist_info}/METADATA",
            f"{dist_info}/WHEEL",
            f"{dist_info}/RECORD",
            f"{dist_info}/licenses/LICENSE",
        }
        assert names == expected, f"unexpected wheel inventory: {sorted(names ^ expected)}"

        project_metadata = BytesParser().parsebytes(wheel.read(metadata_paths[0]))
        assert project_metadata["Name"] == NAME
        assert project_metadata["Version"] == VERSION
        assert project_metadata.get_all("Requires-Dist") == ["PySide6-Essentials==6.11.1"]

        wheel_metadata = BytesParser().parsebytes(wheel.read(wheel_paths[0]))
        assert wheel_metadata["Root-Is-Purelib"] == "false"
        tags = wheel_metadata.get_all("Tag", [])
        assert tags and len(tags) == len(set(tags)), tags
        assert set(tags) == filename_tags, (tags, filename_tags)
        for tag in tags:
            python_tag, abi_tag, platform_tag = tag.split("-")
            assert python_tag == "cp312", tag
            assert abi_tag == "cp312", tag
            assert platform_tag != "any", tag

        forbidden_parts = {"__pycache__", "tests", "src", ".pytest_cache"}
        assert not any(forbidden_parts.intersection(Path(name).parts) for name in names)
        assert not any(name.endswith((".cpp", ".h", ".pyc", "CMakeLists.txt")) for name in names)


def _wait_until(
    process_events: Callable[[], None],
    predicate: Callable[[], bool],
    description: str,
    timeout_seconds: float = 10.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        process_events()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {description}")


def _wait_for_qml_component(
    process_events: Callable[[], None],
    component: object,
    description: str,
) -> None:
    from PySide6.QtQml import QQmlComponent

    assert isinstance(component, QQmlComponent), type(component)
    _wait_until(
        process_events,
        lambda: component.status() != QQmlComponent.Status.Loading,
        description,
    )
    assert component.status() == QQmlComponent.Status.Ready, [
        str(error) for error in component.errors()
    ]


def _assert_origin(
    origin: Path,
    *,
    prefix: Path,
    qualification_mount: Path,
    description: str,
) -> None:
    resolved = origin.resolve()
    assert resolved.is_relative_to(prefix), f"{description} is outside sys.prefix: {resolved}"
    assert not resolved.is_relative_to(qualification_mount), (
        f"{description} came from the qualification mount: {resolved}"
    )


def _assert_installed_module(
    module: ModuleType,
    distribution_name: str,
    *,
    prefix: Path,
    qualification_mount: Path,
) -> Path:
    module_origin = module.__spec__.origin if module.__spec__ is not None else None
    assert module_origin not in {None, "built-in", "frozen"}, module_origin
    _assert_origin(
        Path(module_origin),
        prefix=prefix,
        qualification_mount=qualification_mount,
        description=f"{module.__name__} module",
    )

    distribution = metadata.distribution(distribution_name)
    distribution_files = distribution.files
    assert distribution_files is not None, distribution_name
    metadata_files = [
        path
        for path in distribution_files
        if path.name == "METADATA" and path.parent.name.endswith(".dist-info")
    ]
    assert len(metadata_files) == 1, metadata_files
    _assert_origin(
        Path(distribution.locate_file(metadata_files[0])),
        prefix=prefix,
        qualification_mount=qualification_mount,
        description=f"{distribution_name} distribution",
    )
    return Path(module_origin).resolve().parent


def _run_tool(command: list[str], *, environment: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    assert completed.returncode == 0, f"{' '.join(command)} failed:\n{output}"
    return output


def _verify_installed_elf(native_path: Path, qt_library_root: Path) -> None:
    dynamic = _run_tool(["readelf", "--dynamic", str(native_path)])
    for line in dynamic.splitlines():
        if "(RPATH)" not in line and "(RUNPATH)" not in line:
            continue
        match = re.search(r"Library (?:rpath|runpath): \[(.*)]", line)
        assert match is not None, line
        for entry in match.group(1).split(":"):
            assert entry, line
            assert not entry.startswith("/"), f"absolute ELF search path: {entry}"
            lowered = entry.lower()
            for forbidden in (
                "aqt",
                "build",
                "checkout",
                "gcc_64",
                "github/workspace",
                "linux_gcc",
                "runner/_work",
                "runner_temp",
            ):
                assert forbidden not in lowered, f"forbidden ELF search path: {entry}"

    ldd_environment = os.environ.copy()
    ldd_environment["LD_LIBRARY_PATH"] = str(qt_library_root)
    linked = _run_tool(["ldd", str(native_path)], environment=ldd_environment)
    assert "not found" not in linked, linked
    assert re.search(r"(?im)^\s*libvtk", linked) is None, linked

    qt_resolutions: dict[str, Path] = {}
    for line in linked.splitlines():
        fields = line.split()
        if not fields or not fields[0].startswith("libQt"):
            continue
        assert len(fields) >= 3 and fields[1] == "=>", line
        resolved = Path(fields[2]).resolve(strict=True)
        assert resolved.is_relative_to(qt_library_root), (
            f"{fields[0]} resolved outside the PySide6 wheel: {resolved}"
        )
        qt_resolutions[fields[0]] = resolved
    assert qt_resolutions, linked


def _qt_library_root() -> Path:
    distribution = metadata.distribution("PySide6-Essentials")
    root = Path(distribution.locate_file("PySide6/Qt/lib")).resolve(strict=True)
    assert root.is_dir(), root
    return root


def _verify_qt_runtime_libraries() -> None:
    qt_library_root = _qt_library_root()
    for library_name in (
        "libQt6Core.so.6",
        "libQt6DBus.so.6",
        "libQt6Gui.so.6",
        "libQt6Network.so.6",
        "libQt6OpenGL.so.6",
        "libQt6OpenGLWidgets.so.6",
        "libQt6Qml.so.6",
        "libQt6Quick.so.6",
        "libQt6Widgets.so.6",
    ):
        library_path = (qt_library_root / library_name).resolve(strict=True)
        linked = _run_tool(["ldd", str(library_path)])
        assert "not found" not in linked, f"unresolved dependency for {library_name}:\n{linked}"


def smoke_qt_runtime() -> None:
    assert sys.flags.isolated == 1, "Qt runtime probe must run with Python -I"
    inherited = sorted(name for name in UNSET_ENVIRONMENT_VARIABLES if name in os.environ)
    assert not inherited, f"Qt runtime probe inherited build/import variables: {inherited}"

    _verify_qt_runtime_libraries()
    for module_name in (
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtWidgets",
    ):
        import_module(module_name)

    from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtQuick import QQuickWindow, QSGRendererInterface

    QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
    app = QGuiApplication([sys.argv[0]])

    def process_events() -> None:
        QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 25)

    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        b"""
import QtQuick
import QtQuick.Window

Window {
    width: 240
    height: 160
    visible: false
    Rectangle {
        anchors.fill: parent
        color: "#101820"
    }
}
""",
        QUrl("inmemory:/qt-runtime-probe.qml"),
    )
    _wait_for_qml_component(process_events, component, "the Qt runtime probe component")
    window = component.create()
    assert isinstance(window, QQuickWindow), type(window)

    window.show()
    _wait_until(process_events, window.isExposed, "the Qt runtime probe window")
    window.hide()
    _wait_until(process_events, lambda: not window.isVisible(), "the hidden probe window")
    window.deleteLater()
    component.deleteLater()
    engine.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    process_events()
    assert not any(top_level.isVisible() for top_level in app.topLevelWindows())
    app.quit()


def _verify_installed_layout() -> ModuleType:
    assert sys.flags.isolated == 1, "qualification must run with Python -I"
    inherited = sorted(name for name in UNSET_ENVIRONMENT_VARIABLES if name in os.environ)
    assert not inherited, f"qualification inherited build/import variables: {inherited}"

    prefix = Path(sys.prefix).resolve()
    qualification_mount = Path(__file__).resolve().parent
    carnopy = import_module("carnopy")
    bridge = import_module(PACKAGE)
    _assert_installed_module(
        carnopy,
        "carnopy",
        prefix=prefix,
        qualification_mount=qualification_mount,
    )
    bridge_root = _assert_installed_module(
        bridge,
        NAME,
        prefix=prefix,
        qualification_mount=qualification_mount,
    )

    native_paths = sorted(bridge_root.glob("_native*.so"))
    assert len(native_paths) == 1, native_paths
    _assert_origin(
        native_paths[0],
        prefix=prefix,
        qualification_mount=qualification_mount,
        description="installed native extension",
    )

    pyside = import_module("PySide6")
    pyside_origin = Path(pyside.__file__).resolve()
    _assert_origin(
        pyside_origin,
        prefix=prefix,
        qualification_mount=qualification_mount,
        description="PySide6 module",
    )
    qt_library_root = (pyside_origin.parent / "Qt" / "lib").resolve(strict=True)
    _verify_installed_elf(native_paths[0], qt_library_root)
    return bridge


def smoke_installed() -> None:
    bridge = _verify_installed_layout()
    live_instances = bridge.live_instances
    prepare_graphics_api = bridge.prepare_graphics_api
    register_qml_types = bridge.register_qml_types
    scene_destructions = bridge.scene_destructions
    scene_initializations = bridge.scene_initializations

    from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QObject, QPoint, Qt, QUrl
    from PySide6.QtGui import QGuiApplication, QImage
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtQuick import QQuickWindow
    from PySide6.QtTest import QTest

    assert live_instances() == 0
    assert scene_initializations() == 0
    assert scene_destructions() == 0
    prepare_graphics_api()
    app = QGuiApplication([sys.argv[0]])

    def process_events() -> None:
        QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 25)

    try:
        prepare_graphics_api()
    except RuntimeError:
        pass
    else:
        raise AssertionError("late graphics preparation was accepted")

    register_qml_types()
    engine = QQmlEngine()
    qml_warnings: list[str] = []
    engine.warnings.connect(lambda warnings: qml_warnings.extend(map(str, warnings)))
    component = QQmlComponent(engine)
    component.setData(
        b"""
import QtQuick
import QtQuick.Window
import Carnopy.VTK 1.0

Window {
    width: 480
    height: 360
    visible: false
    color: "#101820"
    QualificationCone {
        objectName: "qualificationCone"
        anchors.fill: parent
    }
}
""",
        QUrl("inmemory:/qualification.qml"),
    )
    _wait_for_qml_component(process_events, component, "the native QML component")
    window = component.create()
    assert isinstance(window, QQuickWindow), type(window)
    window.setPersistentSceneGraph(False)
    window.setPersistentGraphics(False)
    item = window.findChild(QObject, "qualificationCone")
    assert item is not None
    assert not window.isVisible()
    assert scene_initializations() == 0
    assert scene_destructions() == 0

    _wait_until(process_events, lambda: live_instances() == 1, "the native item to become live")
    window.show()
    _wait_until(process_events, window.isExposed, "the QML window to become exposed")
    _wait_until(
        process_events,
        lambda: scene_initializations() > scene_destructions(),
        "the VTK scene to initialize",
    )

    frames: list[tuple[QImage, bytes]] = []

    def capture_frame(
        *,
        expected_size: tuple[int, int] | None = None,
        different_from: bytes | None = None,
    ) -> bool:
        image = window.grabWindow()
        if image.isNull() or image.width() == 0 or image.height() == 0:
            return False
        if expected_size is not None and (image.width(), image.height()) != expected_size:
            return False
        rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
        pixels = bytes(rgba.constBits()[: rgba.sizeInBytes()])
        if different_from is not None and pixels == different_from:
            return False
        frames[:] = [(image.copy(), pixels)]
        return True

    def assert_nonuniform(frame: tuple[QImage, bytes]) -> None:
        pixels = frame[1]
        first_pixel = pixels[:4]
        assert first_pixel and any(
            pixels[offset : offset + 4] != first_pixel for offset in range(4, len(pixels), 4)
        ), "rendered image is uniform"

    _wait_until(process_events, capture_frame, "a rendered initial frame")
    assert_nonuniform(frames[0])
    initial_pixels = frames[0][1]

    start = QPoint(window.width() // 2, window.height() // 2)
    middle = QPoint(start.x() + 30, start.y() + 20)
    end = QPoint(start.x() + 60, start.y() + 40)
    QTest.mousePress(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        start,
        10,
    )
    QTest.mouseMove(window, middle, 20)
    process_events()
    QTest.mouseMove(window, end, 20)
    QTest.mouseRelease(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        end,
        10,
    )
    _wait_until(
        process_events,
        lambda: int(item.property("interactionCount")) >= 1,
        "the forwarded mouse interaction",
    )
    frames.clear()
    _wait_until(
        process_events,
        lambda: capture_frame(different_from=initial_pixels),
        "the rendered frame to change after the drag",
    )
    assert_nonuniform(frames[0])

    window.resize(640, 400)
    _wait_until(
        process_events,
        lambda: window.width() == 640 and window.height() == 400,
        "the resized window",
    )
    frames.clear()
    _wait_until(
        process_events,
        lambda: capture_frame(expected_size=(640, 400)),
        "a 640x400 rendered frame",
    )
    assert (frames[0][0].width(), frames[0][0].height()) == (640, 400)
    assert_nonuniform(frames[0])

    initialized_before_release = scene_initializations()
    destroyed_before_release = scene_destructions()
    assert initialized_before_release > destroyed_before_release
    window.hide()
    _wait_until(process_events, lambda: not window.isVisible(), "the hidden window")
    window.releaseResources()
    _wait_until(
        process_events,
        lambda: (
            scene_destructions() > destroyed_before_release
            and scene_destructions() == scene_initializations()
        ),
        "the released VTK scene to be destroyed",
    )

    reinitializations_before_show = scene_initializations()
    window.show()
    _wait_until(process_events, window.isExposed, "the reshown window")
    _wait_until(
        process_events,
        lambda: scene_initializations() > reinitializations_before_show,
        "the VTK scene to reinitialize",
    )
    frames.clear()
    _wait_until(
        process_events,
        lambda: capture_frame(expected_size=(640, 400)),
        "a rendered frame after scene reinitialization",
    )
    assert_nonuniform(frames[0])

    destroyed_before_teardown = scene_destructions()
    window.hide()
    _wait_until(process_events, lambda: not window.isVisible(), "the final hidden window")
    window.releaseResources()
    _wait_until(
        process_events,
        lambda: (
            scene_destructions() > destroyed_before_teardown
            and scene_destructions() == scene_initializations()
        ),
        "the final VTK scene destruction",
    )

    item = None
    window.deleteLater()
    component.deleteLater()
    engine.deleteLater()

    def process_deferred_deletions() -> None:
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        process_events()

    _wait_until(
        process_deferred_deletions,
        lambda: live_instances() == 0 and scene_destructions() == scene_initializations(),
        "native item and VTK scene teardown",
    )
    assert not any(top_level.isVisible() for top_level in app.topLevelWindows())
    assert not qml_warnings, qml_warnings
    app.quit()


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect-wheel")
    inspect_parser.add_argument("wheel", type=Path)
    subparsers.add_parser("smoke-qt-runtime")
    subparsers.add_parser("smoke-installed")
    args = parser.parse_args()

    if args.command == "inspect-wheel":
        inspect_wheel(args.wheel)
    elif args.command == "smoke-qt-runtime":
        smoke_qt_runtime()
    else:
        smoke_installed()


if __name__ == "__main__":
    main()
