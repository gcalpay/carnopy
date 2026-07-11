from importlib import import_module

for _module in (
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtWidgets",
):
    import_module(_module)

_native = import_module(f"{__name__}._native")
live_instances = _native.live_instances
prepare_graphics_api = _native.prepare_graphics_api
register_qml_types = _native.register_qml_types
scene_destructions = _native.scene_destructions
scene_initializations = _native.scene_initializations

del _module, _native, import_module

__version__ = "0.1.0a3"
__all__ = (
    "__version__",
    "live_instances",
    "prepare_graphics_api",
    "register_qml_types",
    "scene_destructions",
    "scene_initializations",
)
