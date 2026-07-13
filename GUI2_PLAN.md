# Carnopy GUI-2: QML workflows and native scientific 3D

This temporary document is the implementation source of truth for GUI-2. It
records decisions that must survive long development threads and context
compaction. Delete it only after every GUI-2 stage is complete, permanent
documentation and Graphify outputs describe the final architecture, and the
maintainer has accepted the completed implementation.

## Release and frontend baseline

- `0.1.0a3` is the published baseline and contains the completed Qt Widgets
  GUI-1 application.
- GUI-2 targets `0.1.0a4.dev0` during development and `0.1.0a4` for release.
- `carnopy-gui` and `carnopy-app` will both launch one QML application in
  `0.1.0a4`.
- Widgets remain temporarily as a parity oracle, then are removed before the
  release. GUI-2 will not ship a frontend selector or two desktop applications.
- The `app` extra means the cross-platform QML application. The optional `3d`
  extra adds native VTK rendering to that same application. It is not a second
  GUI.

The release transition into GUI-2 development is complete through:

```text
docs(app): track GUI-2 implementation stages
chore(release): start 0.1.0a4 development
```

Carnopy and companion bridge PEP 440 metadata now report `0.1.0a4.dev0`; the
numeric CMake declaration remains `0.1.0`. This metadata-only transition does
not require another native VTK qualification run. Stage 1 is active.

## Authority and permanent boundaries

The tracked `AGENTS.md` and local `.agents/local.md` control Git authority,
dependency operations, model selection, scientific behavior, public contracts,
and verification. Do not duplicate their model policy here.

When explicit maintainer input is required, do not use an automatic timeout or
infer a default. Wait for an explicit response.

Locked GUI-2 requirements:

- QML becomes the only normal frontend after tested parity.
- Preserve the CLI, public Python API, YAML schemas, immutable output layouts,
  provenance, integrity, units, identities, and no-overwrite behavior.
- Preserve one short-lived private worker process per request and one globally
  active desktop request.
- Keep CoolProp, pandas, PyArrow, Matplotlib, scientific pipelines, and rendering
  implementations outside the QML process.
- Provide complete dataset, model-sweep, and preparation workflows without
  duplicating scientific logic in QML.
- Provide emitted-value 3D without interpolation, smoothing, extrapolation,
  resampling, invented states, or silent hole filling.
- Keep the native VTK bridge as a companion distribution in this repository.
- Support the QML application on Linux, Windows, and macOS. Native 3D is
  Linux-first until additional platforms pass explicit qualification.
- Deliver GUI-2 through one final pull request with coherent intermediate
  commits and stage-specific verification.
- Git mutation, dependency changes, credentials, external configuration,
  release tags, and publication remain human-controlled.

Internal names, controller grouping, scene serialization, CI structure, native
build mechanics, and commit grouping may change when repository evidence and
tests justify a better implementation. Changes to scientific behavior, public
interfaces, the renderer family, companion-distribution strategy, or platform
promises require maintainer approval.

## Stage status

| Stage | Status | Purpose |
| --- | --- | --- |
| 0 | Complete | Qualify the native Qt Quick and VTK bridge |
| 1 | Active | Establish request ownership and dataset desktop controllers |
| 2 | Pending | Add the modern QML workspace and dataset workflow |
| 3 | Pending | Reach GUI-1 parity and retire Widgets |
| 4 | Pending | Add controlled sweep and preparation worker operations |
| 5 | Pending | Add structured sweep and preparation QML workflows |
| 6 | Pending | Build exact emitted-value 3D scenes |
| 7 | Pending | Add native interactive 3D to the QML application |
| 8 | Pending | Qualify packaging, platforms, documentation, and release readiness |

## Stage 0: Native feasibility gate

Stage 0 qualified a same-repository `carnopy-vtk-bridge` wheel containing a C++
`QQuickVTKItem` subtype. The successful qualification used:

- final qualified commit:
  `094378ca3fef53de7338f593188d5e14f1461a84`;
- workflow: <https://github.com/gcalpay/carnopy/actions/runs/29190590135>;
- Linux Ubuntu 24.04 container runtime;
- CPython 3.12;
- Qt 6.11.1;
- VTK 9.6.2;
- software OpenGL through Xvfb for automated rendering.

The clean-runtime test built and inspected both wheels, installed them in an
isolated environment, loaded the QML type, rendered and interacted with a cone,
resized and reconstructed the scene after hide and show, destroyed the native
item, exited cleanly, and found no unresolved host-only library dependency.

This proves architectural feasibility only. It does not qualify the final
scientific renderer, other Python versions, other operating systems, or future
native changes. Metadata-only retargeting does not require rebuilding VTK.
Substantive bridge or packaging changes do.

## Stage 1: Request ownership and dataset desktop core

Stage 1 deliberately avoids extracting every future controller at once.

Required work:

- Keep `WorkerClient` limited to QProcess transport, JSON Lines parsing, stderr,
  process state, and one transport outcome after process exit.
- Add one request coordinator that owns the active request UUID, type, owner,
  cancellation policy, terminal envelope, force-stop state, and parent cleanup
  finalizer.
- Route events and terminal results only to the controller that owns the
  request. Unknown or stale ownership must fail safely.
- Remove plot-specific staging creation and cleanup from `WorkerClient`.
- Keep guarded parent staging only for image and sidecar exports. Dataset,
  sweep, and preparation staging remains pipeline-owned.
- Extract QML-ready QtCore workspace and dataset-configuration controllers.
- Preserve recent workspaces, deterministic YAML, worker validation, atomic
  writes, external-change checks, dirty-state prompts, ordering, compatibility
  validation, and reference-state advisories.
- Adapt the Widgets frontend to these controllers without changing user-visible
  behavior.

Completed Stage 1 slices:

- request ownership, coordinator-owned terminal envelopes, cancellation policy,
  and export finalization;
- QML-ready workspace state, trusted two-phase workspace operations, direct
  recent-workspace model binding, and the desktop composition root;
- QML-ready dataset draft and sampler state, dataset-only baselines, ordered
  selection models, local compatibility issues, and incomplete-draft discard
  protection;
- QML-ready configured-visualization draft state, canonical and raw dirty
  baselines, retained latent and incompatible selections, ordered plot
  snapshots, one workflow-local Add/Edit plot draft, and Widgets bindings over
  the authoritative draft.

Widgets remains the active frontend, and Stage 1 remains active. Its remaining
boundary is to extract the complete dataset-configuration workflow from
`DatasetConfigEditor` into a QML-ready QtCore controller without starting QML.
That controller must own document import, opening, clearing, exact complete-YAML
coordination, worker validation before writes, Save and Save As orchestration,
external-change handling, discard protection, and execution gating while using
the existing dataset and visualization drafts. Adapt Widgets to that controller
and preserve the current worker and file-safety boundaries. After this
workflow-controller slice is verified, Stage 1 is complete and Stage 2 begins.

Execution, inspection, table, plotting, jobs, and recovery controllers are not
preemptively extracted in Stage 1. Extract each immediately before its QML
migration so its interface is grounded in the actual vertical workflow.

## Stage 2: Modern QML dataset application

- Package QML and design resources through installed-package resources.
- Build a restrained scientific design system with reliable system, light, and
  dark palettes, responsive navigation, dense layouts, keyboard access, visible
  focus, accessibility labels, contextual help, and non-color-only status.
- Preserve `--qt-platform auto|xcb|wayland`.
- Implement workspace lifecycle and configuration states: unavailable, loading,
  landing, and editing.
- With a workspace but no draft, show only **New Dataset** and **Import Existing
  Configuration**.
- Show Dataset, Visualization, YAML Preview, Save, Save As, and Close
  Configuration only while a real draft exists.
- Display units beside numeric inputs and convert display values to canonical SI
  before validation and serialization.
- Keep public launchers on Widgets during this stage. Exercise QML through an
  internal or test entrypoint until existing workflow parity is proven.

## Stage 3: GUI-1 parity and Widgets retirement

Extract and migrate the remaining existing desktop workflows incrementally:

- validation and generation with progress and cancellation;
- source discovery and dataset, sweep, preparation, CSV, and Parquet inspection;
- bounded table preview;
- session plot editing, worker rendering, PNG and SVG preview, and explicit PDF
  opening;
- job history and guarded staging recovery.

Rename the final page **Activity and Recovery** and explain its purpose. Switch
both public launchers to QML only after equivalent tests pass. Then delete the
Widgets implementation and implementation-specific Widgets tests while keeping
shared worker, protocol, controller, scientific-boundary, and workflow tests.

## Stage 4: Sweep and preparation worker operations

Add private worker operations for sweep and preparation capabilities, loading,
exact-text validation, planning, execution, progress, and cancellation.

Preparation planning must be non-writing and verify source identity, integrity,
revision, semantic fields, units, derived dependencies, reference-state
compatibility, scenarios, exact-state leakage protection, transformations,
output formats, categorical coding, optional dependency availability, matrix
diagnostics, and baseline feasibility.

Add cancellation checkpoints to expensive phases and disable cancellation before
immutable finalization. Handled failures clean staging; recognized staging left
by force-stop remains recoverable. Do not change public schemas, APIs, or output
layouts.

## Stage 5: Sweep and preparation QML workflows

The sweep workflow covers models, reference-model settings, comparison options,
comparison plots, validation, execution, cancellation, and inspection handoff.

The preparation workflow covers immutable dataset or sweep sources, numeric and
categorical features, targets, auxiliary fields, derived fields, all current
scenarios and partitions, `log10`, `standard`, `minmax`, and `robust`
transformations, canonical Parquet, optional NPY, NPZ, and SafeTensors outputs,
matrix diagnostics, and optional dummy, ridge, and histogram-gradient-boosting
diagnostics.

Inspection presents manifests, dataset cards, quality flags, exclusions,
provenance, leakage audits, partition summaries, correlations, singular values,
rank, conditioning, and baseline metrics. Missing optional dependencies disable
only the affected feature and provide exact installation guidance.

## Stage 6: Exact scientific 3D scenes

Worker-prepared scenes support dataset runs and prepared main or scenario tables.

- Points represent finite emitted rows.
- Wireframe edges connect exact adjacent coordinate levels only within compatible
  fluid, model, phase, and partition contexts.
- Surfaces require two independent coordinates, explicit structured-grid
  evidence, and one unambiguous row per coordinate pair.
- A surface cell exists only when all corners exist and share a compatible
  context.
- Missing and invalid rows remain gaps.
- Ambiguous duplicates, incompatible contexts, non-positive logarithmic domains,
  and unsupported shapes fail clearly.
- Picking maps exactly to source-row identity and provenance.
- No backend call, interpolation, smoothing, extrapolation, resampling, or
  silent repair is permitted.

The scene representation must be bounded, hashed, reconstructible, and
consumable by the GUI and bridge without scientific imports in QML.

## Stage 7: Native interactive 3D

Expand the qualified bridge with render-thread-owned VTK state, scene
reconstruction, rotate, pan, zoom, camera reset, standard views, axes and units,
scalar legends, validated linear and logarithmic presentation, points,
wireframe, surface modes, exact picking, and deterministic teardown.

The QML page selects inspection-backed sources, coordinates, scalar values,
scales, representations, and filters. Unsupported surfaces receive an explicit
explanation rather than an approximation.

Authoritative image export uses a short-lived worker with explicit scene,
camera, dimensions, scalar mapping, and rendering settings. It writes a guarded
no-overwrite PNG and sidecar. Live framebuffer capture is not authoritative.

## Stage 8: Packaging and release qualification

The package has one QML GUI with optional capabilities:

- `app` installs the cross-platform QML application without native VTK;
- `3d` adds the native bridge to the same QML application;
- base, `viz`, `ml`, and `analysis` remain isolated.

Two packaging decisions remain open until their dedicated Stage 8 review:

1. whether `all` remains cross-platform without `3d` or includes `3d` and becomes
   Linux-only;
2. whether native 3D initially supports only CPython 3.12 or requires bridge
   wheels for every Carnopy-supported Python version.

Qualification must cover installed QML resources, Linux, Windows, and macOS QML
startup, Linux native build and wheel inspection, rendering, picking, resize,
hide and show reconstruction, teardown, process exit, dependency isolation,
optional-feature errors, security auditing, and non-destructive distribution
rehearsal.

The bridge and Carnopy remain separate artifacts. Human configuration is
required before any companion PyPI project, Trusted Publisher, tag, or
publication. Publication order is bridge first and Carnopy second.

Document verified behavior only, including platform status, native dependency
size, Qt and VTK licensing boundaries, and WSLg guidance.

## Completion gate

Before the final pull request:

- run focused checks after every stage;
- run the complete repository quality gate;
- inspect source, wheel, sdist, QML, and native-resource inventories;
- run installed base, app, analysis, 3D, and applicable `all` smoke profiles;
- run the three-platform QML checks and Linux native checks;
- manually exercise WSLg XCB and Wayland startup;
- manually exercise dataset, sweep, preparation, inspection, table, plot, job,
  recovery, and exact 3D workflows;
- use an explicitly configured allowed reviewer for an independent final audit;
- resolve all concrete high- and medium-severity findings;
- update permanent documentation and Graphify from the final architecture;
- delete this temporary plan only after those steps pass.

Manim, PyMC, SINDy, optimization, ORC and TFC workflows, mixtures, training
infrastructure, deployment, additional backends, and standalone installers are
deferred to separately reviewed milestones.
