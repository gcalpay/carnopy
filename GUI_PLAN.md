# Carnopy GUI-1 implementation plan

This temporary document tracks the staged `0.1.0a3` desktop implementation.
It is the source of truth for GUI stage boundaries while GUI-1 is under active
development. Update the status after each stage and delete this file after
Stage 7 is complete.

## Durable boundaries

- The PySide6 Qt Widgets application is a sibling frontend to the Typer CLI.
- Widgets communicate with one short-lived worker process through the private,
  versioned JSON Lines protocol; they do not invoke or parse CLI commands.
- The GUI process does not import CoolProp, generation pipelines, pandas,
  PyArrow, Matplotlib renderers, or other scientific execution dependencies.
- Existing Carnopy Python pipelines remain the scientific implementation.
- YAML remains the portable configuration authority. The structured form is
  authoritative while editing, and its deterministic YAML preview is read-only.
- Imported external files remain untouched. Workspace-owned configuration files
  may be saved atomically after worker validation.
- Generated dataset runs remain immutable. Cooperative cancellation may clean
  worker-owned staging output but never a finalized run.
- GUI-1 creates, validates, generates, inspects, and plots dataset
  configurations. Sweep and preparation bundles are read-only; creating those
  workflows is deferred to GUI-2.

## Stage status

| Stage | Deliverable | Status |
| --- | --- | --- |
| 1 | Worker protocol, generation progress, cancellation, and staging cleanup | Complete |
| 2 | Optional app packaging, launcher, workspace lifecycle, and desktop shell | Complete |
| 3 | Dataset configuration editor and deterministic YAML workflow | Complete |
| 4 | Validation, generation, source inspection, table previews, jobs, and recovery | Complete |
| 5 | Manual plot export and PNG/SVG previews | Pending |
| 6 | CI, documentation, packaging, and `0.1.0a3` release hardening | Pending |
| 7 | Graphify architecture-map refresh and final boundary review | Pending |

## Stage 3 decisions

Stage 3 was implemented in focused commits and manually inspected before its
final documentation pass.

- New Dataset opens a mode-selection dialog and loads the selected packaged
  concise template.
- Full worker validation runs for Import and Save. Invalid imports remain
  external and must be repaired in a text editor.
- The first Save opens an exclusive file dialog under `workspace/configs/`.
- Configure uses Dataset, Visualization, and YAML Preview tabs.
- All registered properties stay visible. Unsupported properties cannot be
  newly selected; imported selections that become incompatible remain visible
  and removable and block Save until resolved.
- Mode changes require confirmation, preserve shared fields, reset the
  mode-specific grid, and clear configured plot requests.
- Configured visualization editing is structured and round-trip safe for every
  current plot field. Finite choices such as fields, fluids, categorical
  values, units, formats, scales, and valid series dimensions use guided
  controls. Exact numeric filter and series levels remain explicit inputs
  because no dataset exists yet.
- Full worker validation remains authoritative before Save. Stage 3 does not
  render plots.
- README and contributor guidance describe the implemented editor. Graphify
  remains unchanged until Stage 7.

## Stage 4 decisions

- Validate and Generate accept only the exact saved workspace configuration.
  The worker recomputes its SHA-256 before importing generation pipelines.
- Each action uses the shared GUI-side client abstraction and one short-lived
  worker process. Displayed CLI commands remain informational only.
- Generation reports phases and rows, supports cooperative cancellation, and
  reveals an explicit force-stop option only after a cancellation wait.
- Validate and Generate records are persisted as workspace-local JSON with the
  exact YAML snapshot and verbatim terminal worker envelope. They are never
  auto-pruned.
- Stale staging cleanup is opt-in and restricted to exact direct-child names;
  device and inode identity are revalidated before removal.
- Workspace discovery is direct-child only. Dataset runs, standalone CSV or
  Parquet, model-sweep bundles, and preparation bundles are inspected by the
  worker. Broken recognized candidates remain visible as uninspectable.
- Preparation manifest paths reject traversal, absolute paths, symlink
  components, non-files, and recorded-hash mismatches.
- Table previews preserve emitted order. Workers return at most 500 rows using
  bounded Parquet or CSV reads; Qt presents local 100-row pages. NumPy and
  SafeTensors outputs are listed but not rendered.

## Remaining stages

### Stage 5 — Plot exports and previews

Drive current plot controls from inspection results, render through the worker,
write nested no-overwrite-safe figure outputs and sidecars, preview PNG/SVG in
Qt, and open PDF with the system viewer.

### Stage 6 — Release hardening

Finish CI and installed-wheel coverage, document the optional Qt licensing
boundary and desktop workflow, update the source version to `0.1.0a3`, and run
the complete source and distribution gates.

### Stage 7 — Architecture map

Regenerate the public Graphify outputs after source and documentation stabilize.
Verify that GUI modules do not bridge directly to CLI handlers or CoolProp,
review inferred edges against source, commit only approved public graph outputs,
then delete this temporary plan.
