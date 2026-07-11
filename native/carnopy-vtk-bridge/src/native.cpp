#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <QCoreApplication>
#include <QEvent>
#include <QQuickVTKItem.h>
#include <qqml.h>

#include <atomic>

#include <vtkActor.h>
#include <vtkConeSource.h>
#include <vtkObject.h>
#include <vtkObjectFactory.h>
#include <vtkPolyDataMapper.h>
#include <vtkProperty.h>
#include <vtkRenderWindow.h>
#include <vtkRenderer.h>
#include <vtkSmartPointer.h>

namespace
{
std::atomic<int> liveInstanceCount{ 0 };
std::atomic<int> sceneInitializationCount{ 0 };
std::atomic<int> sceneDestructionCount{ 0 };
bool qmlTypesRegistered = false;
}

class QualificationSceneData final : public vtkObject
{
public:
  static QualificationSceneData* New();
  vtkTypeMacro(QualificationSceneData, vtkObject);

  vtkSmartPointer<vtkConeSource> Cone;
  vtkSmartPointer<vtkPolyDataMapper> Mapper;
  vtkSmartPointer<vtkActor> Actor;
  vtkSmartPointer<vtkRenderer> Renderer;
};

vtkStandardNewMacro(QualificationSceneData);

class QualificationCone final : public QQuickVTKItem
{
  Q_OBJECT
  Q_PROPERTY(int interactionCount READ interactionCount NOTIFY interactionCountChanged)

public:
  explicit QualificationCone(QQuickItem* parent = nullptr)
    : QQuickVTKItem(parent)
  {
    ++liveInstanceCount;
  }

  ~QualificationCone() override { --liveInstanceCount; }

  int interactionCount() const { return this->InteractionCount; }

  vtkUserData initializeVTK(vtkRenderWindow* renderWindow) override
  {
    auto scene = vtkSmartPointer<QualificationSceneData>::New();
    scene->Cone = vtkSmartPointer<vtkConeSource>::New();
    scene->Mapper = vtkSmartPointer<vtkPolyDataMapper>::New();
    scene->Actor = vtkSmartPointer<vtkActor>::New();
    scene->Renderer = vtkSmartPointer<vtkRenderer>::New();

    scene->Cone->SetResolution(48);
    scene->Mapper->SetInputConnection(scene->Cone->GetOutputPort());
    scene->Actor->SetMapper(scene->Mapper);
    scene->Actor->GetProperty()->SetColor(0.95, 0.45, 0.12);
    scene->Renderer->AddActor(scene->Actor);
    scene->Renderer->SetBackground(0.05, 0.08, 0.12);
    scene->Renderer->ResetCamera();
    renderWindow->AddRenderer(scene->Renderer);
    ++sceneInitializationCount;
    return scene;
  }

  void destroyingVTK(vtkRenderWindow*, vtkUserData) override
  {
    ++sceneDestructionCount;
  }

Q_SIGNALS:
  void interactionCountChanged();

protected:
  bool event(QEvent* event) override
  {
    if (event && event->type() == QEvent::MouseButtonPress)
    {
      ++this->InteractionCount;
      Q_EMIT this->interactionCountChanged();
    }
    return QQuickVTKItem::event(event);
  }

private:
  int InteractionCount = 0;
};

namespace
{
PyObject* prepareGraphicsApi(PyObject*, PyObject*)
{
  if (QCoreApplication::instance() != nullptr)
  {
    PyErr_SetString(
      PyExc_RuntimeError, "prepare_graphics_api() must run before QCoreApplication construction");
    return nullptr;
  }
  QQuickVTKItem::setGraphicsApi();
  Py_RETURN_NONE;
}

PyObject* registerQmlTypes(PyObject*, PyObject*)
{
  if (!qmlTypesRegistered)
  {
    const int typeId = qmlRegisterType<QualificationCone>(
      "Carnopy.VTK", 1, 0, "QualificationCone");
    if (typeId < 0)
    {
      PyErr_SetString(PyExc_RuntimeError, "failed to register Carnopy.VTK QualificationCone");
      return nullptr;
    }
    qmlTypesRegistered = true;
  }
  Py_RETURN_NONE;
}

PyObject* liveInstances(PyObject*, PyObject*)
{
  return PyLong_FromLong(liveInstanceCount.load());
}

PyObject* sceneInitializations(PyObject*, PyObject*)
{
  return PyLong_FromLong(sceneInitializationCount.load());
}

PyObject* sceneDestructions(PyObject*, PyObject*)
{
  return PyLong_FromLong(sceneDestructionCount.load());
}

PyMethodDef methods[] = {
  { "prepare_graphics_api", prepareGraphicsApi, METH_NOARGS,
    "Prepare QQuickVTKItem's OpenGL RHI before application construction." },
  { "register_qml_types", registerQmlTypes, METH_NOARGS,
    "Register the Carnopy.VTK QualificationCone QML type." },
  { "live_instances", liveInstances, METH_NOARGS,
    "Return the number of live native QualificationCone items." },
  { "scene_initializations", sceneInitializations, METH_NOARGS,
    "Return the number of initialized VTK qualification scenes." },
  { "scene_destructions", sceneDestructions, METH_NOARGS,
    "Return the number of destroyed VTK qualification scenes." },
  { nullptr, nullptr, 0, nullptr },
};

PyModuleDef module = {
  PyModuleDef_HEAD_INIT,
  "_native",
  "Carnopy's private native QML and VTK qualification bridge.",
  -1,
  methods,
};
}

PyMODINIT_FUNC PyInit__native()
{
  return PyModule_Create(&module);
}

#include "native.moc"
