cmake_minimum_required(VERSION 3.28)
project(carnopy_vtk_bridge VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_AUTOMOC ON)

find_package(Python 3.12 EXACT REQUIRED COMPONENTS Interpreter Development.Module)
find_package(
  Qt6 6.11.1 EXACT CONFIG REQUIRED
  COMPONENTS Core Gui OpenGL OpenGLWidgets Qml Quick Widgets
)

set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(VTK_BUILD_ALL_MODULES OFF CACHE BOOL "" FORCE)
set(VTK_BUILD_DOCUMENTATION OFF CACHE BOOL "" FORCE)
set(VTK_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(VTK_BUILD_SPHINX_DOCUMENTATION OFF CACHE BOOL "" FORCE)
set(VTK_BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(VTK_ENABLE_REMOTE_MODULES OFF CACHE BOOL "" FORCE)
set(VTK_ENABLE_WRAPPING OFF CACHE BOOL "" FORCE)
set(VTK_INSTALL_SDK OFF CACHE BOOL "" FORCE)
set(VTK_QT_VERSION 6 CACHE STRING "" FORCE)
set(VTK_USE_MPI OFF CACHE BOOL "" FORCE)
set(VTK_USE_X OFF CACHE BOOL "" FORCE)
set(VTK_WRAP_JAVA OFF CACHE BOOL "" FORCE)
set(VTK_WRAP_JAVASCRIPT OFF CACHE BOOL "" FORCE)
set(VTK_WRAP_PYTHON OFF CACHE BOOL "" FORCE)
set(VTK_WRAP_SERIALIZATION OFF CACHE BOOL "" FORCE)
# VTK enables broad StandAlone and Rendering module groups by default. Keep
# those groups disabled and request only the bridge's direct modules below;
# VTK still enables their required transitive dependencies.
set(VTK_GROUP_ENABLE_Qt DONT_WANT CACHE STRING "" FORCE)
set(VTK_GROUP_ENABLE_Rendering DONT_WANT CACHE STRING "" FORCE)
set(VTK_GROUP_ENABLE_StandAlone DONT_WANT CACHE STRING "" FORCE)
set(VTK_MODULE_ENABLE_VTK_FiltersSources YES CACHE STRING "" FORCE)
set(VTK_MODULE_ENABLE_VTK_GUISupportQtQuick YES CACHE STRING "" FORCE)

include(FetchContent)
FetchContent_Declare(
  VTK
  URL https://www.vtk.org/files/release/9.6/VTK-9.6.2.tar.gz
  URL_HASH SHA256=aed12cec12a9609179bf66329070266627ca64244a10856a452b2a17ffb04a1d
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE
  EXCLUDE_FROM_ALL
)
FetchContent_MakeAvailable(VTK)

Python_add_library(_native MODULE WITH_SOABI src/native.cpp)
target_compile_definitions(_native PRIVATE QT_NO_KEYWORDS)
target_link_libraries(
  _native
  PRIVATE
    Qt6::Core
    Qt6::Qml
    Qt6::Quick
    VTK::FiltersSources
    VTK::GUISupportQtQuick
)
vtk_module_autoinit(
  TARGETS _native
  MODULES VTK::FiltersSources VTK::GUISupportQtQuick
)
set_target_properties(_native PROPERTIES INSTALL_RPATH "$ORIGIN")

install(TARGETS _native LIBRARY DESTINATION carnopy_vtk_bridge)
