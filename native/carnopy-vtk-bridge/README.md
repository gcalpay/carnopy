# Carnopy VTK bridge qualification

`carnopy-vtk-bridge` is a private, Linux-only companion wheel used to qualify
Qt Quick and VTK integration for Carnopy GUI-2. It statically embeds the
minimal VTK 9.6.2 module graph needed by `QQuickVTKItem` and a cone source; it
does not depend on Python VTK.

The bridge exposes three functions:

- `prepare_graphics_api()` must run before constructing a Qt application;
- `register_qml_types()` registers `Carnopy.VTK 1.0/QualificationCone`;
- `live_instances()` reports native QML item lifetime for qualification.

This package is built only by the branch-scoped manual qualification job. It
is not a Carnopy public runtime dependency or publication artifact.

