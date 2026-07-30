# Carnopy GUI-2: QML workflows and native scientific 3D

This temporary document is the implementation source of truth for GUI-2. It
records decisions that must survive long development threads and context
compaction. Delete it only after every GUI-2 stage is complete, permanent
documentation and Graphify outputs describe the final architecture, and the
maintainer has accepted the completed implementation.

[`DESKTOP_ARCHITECTURE.md`](DESKTOP_ARCHITECTURE.md) is the durable record of
implemented desktop structure and evolution. This plan remains authoritative
for unfinished GUI-2 work and stage acceptance.

## Release and frontend baseline

- `0.1.0a3` is the published baseline and contains the completed Qt Widgets
  GUI-1 application.
- The first GUI-2 release line uses `0.1.0a4.dev0` during development and
  `0.1.0a4` for the post-Stage-3 alpha release.
- `carnopy-gui` and `carnopy-app` now both launch one QML application;
  `carnopy-gui` is canonical and `carnopy-app` is the compatibility alias for
  `0.1.0a4`.
- The obsolete Widgets presentation has been removed after tested QML parity
  and public-launcher migration. GUI-2 does not ship a frontend selector or two
  desktop applications.
- Stage 2 completion was not the `0.1.0a4` release boundary. Step 19 activated
  Stage 3 while both public launchers still used Widgets. `0.1.0a4` is planned
  after Stage 3 passes the bounded alpha-release gate recorded below. It does
  not wait for Stages 4 through 8. No calendar date is committed.
- `0.1.0a4` deliberately contains the existing `0.1.0a3` desktop workflows in
  the modern QML application; it does not promise the later sweep/preparation
  expansion or native 3D. Stages 4 through 8 belong to later alpha release
  planning.
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
not require another native VTK qualification run. Stages 0 through 2 are
complete and Stage 3 is active.

## Authority and permanent boundaries

The tracked `AGENTS.md` and local `.agents/local.md` control Git authority,
dependency operations, model selection, scientific behavior, public contracts,
and verification. Do not duplicate their model policy here.

When explicit maintainer input is required, do not use an automatic timeout or
infer a default. Wait for an explicit response.

Locked GUI-2 requirements:

- QML becomes the only normal frontend after tested parity.
- Preserve the CLI, public Python API, YAML schemas, immutable output layouts,
  provenance, integrity, identities, and no-overwrite behavior. Preserve unit
  semantics except for the explicitly approved additive Stage 2 sampler units
  recorded below.
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
- Deliver GUI-2 through one branch and pull request per stage, with coherent
  intermediate commits, stage-specific verification, and explicit maintainer
  acceptance before that stage is marked complete.
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
| 1 | Complete | Establish request ownership and dataset desktop controllers |
| 2 | Complete | Add the modern QML workspace and dataset workflow |
| 3 | Active | Reach GUI-1 parity, retire Widgets, and qualify `0.1.0a4` |
| 4 | Pending | Add controlled sweep and preparation worker operations |
| 5 | Pending | Add structured sweep and preparation QML workflows |
| 6 | Pending | Build exact emitted-value 3D scenes |
| 7 | Pending | Add native interactive 3D to the QML application |
| 8 | Pending | Qualify native 3D packaging, platforms, and a later release |

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
  the authoritative draft;
- QML-ready complete dataset-configuration workflow ownership in
  `DatasetConfigController`, including document replacement, deterministic
  complete-YAML merging, worker validation before writes, Save and Save As,
  external-change and imported-reformat decisions, discard protection, and
  execution gating. `DesktopController` owns the operative instance and
  `DatasetConfigEditor` is now only the Widgets view and dialog adapter.

Stage 1 is complete. Widgets remains the unchanged active frontend and no QML
was added during the extraction. Stage 2 now owns the first packaged QML
workspace and dataset workflow over these controller and draft interfaces.

Execution, inspection, table, plotting, jobs, and recovery controllers are not
preemptively extracted in Stage 1. Extract each immediately before its QML
migration so its interface is grounded in the actual vertical workflow.

## Stage 2: Modern QML dataset application — complete

Stage 2 is complete and its detailed implementation plan no longer belongs in
the mandatory active-stage context. The full accepted 19-step plan,
implementation ledger, exact verification record, and transition into Stage 3
remain recoverable at merged Stage 2 revision
`e3550b244d2ac05d0a33cb37875c98c0cb49c7c5`. A small tracked index and recovery
command are kept in
[the Stage 2 historical record](docs/archive/GUI2_STAGE2.md).

The durable implemented outcome is recorded in
[DESKTOP_ARCHITECTURE.md](DESKTOP_ARCHITECTURE.md), source, and tests. In
summary, Stage 2 established:

- the packaged private Qt 6.11.1 QML runtime, installed resources, provenance,
  warning policy, responsive shell, themes, settings, and native-window
  lifecycle;
- one composition-owned controller and draft graph shared temporarily with the
  Widgets parity frontend, with scientific and rendering imports kept outside
  the GUI process;
- trusted Workspace, Dataset, configured-Visualization, deterministic YAML,
  worker-validated Save and Save As, dirty-state, replacement, and shutdown
  workflows;
- exact definition-first sampler canonicalization, exact-key atomic unit
  changes, practical starter grids, lightweight row projections, structured
  field navigation, and revision-bound standalone validation; and
- automated source and installed-QML coverage plus explicit native Linux
  acceptance, without claiming Stage 3 parity or Stage 8 platform/native-3D
  qualification.

Stage 3 may rely on those implemented interfaces and permanent boundaries but
must verify exact behavior against current source and tests. Read the archived
Stage 2 plan only for historical investigation. If a historical rule still
constrains active work but is absent from the durable architecture record,
promote that rule to `DESKTOP_ARCHITECTURE.md` rather than restoring the full
completed plan to this always-read file.

## Stage 3: QML workflow parity and Widgets retirement

Stage 3 migrates the remaining working GUI-1 workflows into the packaged QML
application, makes QML the only desktop presentation implementation, and
deletes the temporary Widgets parity frontend. It does not add a scientific
workflow, renderer, protocol type, public schema, dependency, or plotting kind.

Use:

```text
branch: feat/gui-stage3-qml-parity
PR:     feat(app): complete QML desktop workflow parity
```

The delivery hierarchy is:

```text
GUI-2 → Stage → Step → one or more commits
```

The conventional-commit text assigned below is the recommended primary commit
for that Step. A Step may use more than one coherent commit when independent
review or verification requires it.

The final navigation order is:

```text
Workspace
Dataset
YAML Preview
Run
Inspect
Visualization
Activity and Recovery
```

The rail label is **Activity and Recovery**. Its shorter in-page heading is
**Activity**, with **Run activity** and **Staging Recovery** tabs.

Stage 3 remains on `0.1.0a4.dev0`. The final version change and publication are
a separate `0.1.0a4` release branch and pull request after Stage 3 merges.
`carnopy-gui` becomes the canonical desktop command. `carnopy-app` remains a
thin QML compatibility alias for the documented `0.1.0a4` deprecation window.
Private GUI records and settings created before `0.1.0a4`, and presentation
details of the soon-retired Widgets frontend, carry no additional compatibility
guarantee. Existing narrow migration adapters remain only until tested QML
parity and receive no new features. This does not relax public YAML, generated
dataset, provenance, artifact-integrity, CLI, or scientific contracts.

Current implementation status as of 2026-07-29:

| Step | Tracked state | Verification and remaining boundary |
| --- | --- | --- |
| 1. Lock the Stage 3 contract | Implemented and committed | The complete approved parity, ownership, provenance, launcher, retirement, and release contracts below are authoritative. |
| 2. Extract execution state | Implemented and committed | Focused checks and the branch's remote Desktop-app check passed. |
| 3. Add QML Run | Implemented and committed | Focused checks and the branch's remote Desktop-app check passed. |
| 4. Extract inspection state | Implemented and committed | Focused checks pass. Its remote run exposed the page-loader/delegate-incubation race recorded below. |
| 5. Add QML Inspect | Implemented and committed | Focused and native checks pass. Its remote run reproduced the same race rather than introducing a second Desktop-app failure. |
| 6. Extract Activity and Recovery | Implemented and committed | Focused and remote checks pass, including the corrective page-lifecycle regression. |
| 7. Extract plot-result and session state | Implemented and committed | Focused artifact, controller, Widgets-adapter, import-isolation, packaging, and composition checks pass. The branch's remote checks passed. No protocol or public-schema change was required. |
| 8. Complete QML Visualization | Implemented and committed | QML binds both Step 7 controllers, and focused QML, artifact, export, runtime, packaging, composition, and scientific rendering checks plus the branch's remote checks pass. Page and tab entry remain worker-idle. Native review found and corrected dense-series legend crowding without changing emitted states. |
| 9. Add QML Activity and Recovery | Implemented and committed | The two-tab Activity page binds the existing typed models, routes destructive and cross-page actions through the composition façade, and keeps record/artifact ownership and identity-checked recovery unchanged. Focused controller, QML, runtime, packaging, and native delegate-click checks pass. |
| 10. Complete guarded workflow parity | Implemented and committed | The six exact cross-page paths, record-driven configured empty state, explicit inspected-data exploration, and operation-specific busy-close decisions are implemented. Focused QML, controller, lifecycle, and warning checks pass. |
| 11. Make QML the public desktop frontend | Implemented and committed | Both package entry points resolve directly to the lightweight QML launcher; source, installed-distribution, and remote checks pass. |
| 12. Retire the Widgets presentation layer | Implemented and committed | Fourteen obsolete source modules, five implementation-specific test modules, and obsolete mixed-test UI coverage are removed. Focused structural and QML parity verification and the branch's remote checks pass. |
| 13. Accept and complete Stage 3 | Native acceptance in progress | Step 12 and its remote checks pass. Native review rejected the first presentation capture and exposed the configured-result alignment, focus-preview, active-workspace navigation, Activity-card geometry, QtSvg compatibility, and inspected-data workflow defects recorded below. Corrections pass focused checks. Release-facing README and metadata are simplified to two primary installation paths and one canonical description; tracked citation and generated-software provenance are prepared without a placeholder DOI. Stage 3 remains incomplete until native review accepts the workflow, a representative capture is approved, and the final gates pass. |

The continuing native review also found bounded release-candidate defects.
Inspect now projects the worker-reported column count beside the bounded table
range and binds its
failure-layer delegate through a nonconflicting private Qt role, eliminating
the runtime `model is not defined` warning without changing generated failure
columns. A valid property-table state that lands exactly on saturation may
remain an invalid row with the retained `phase_evaluation_failed` backend
diagnostic; the GUI does not invent a single phase at a two-phase boundary.
A new inspected-data session plot now requires an explicit plot-kind
and field choice, explains property/axis/series/color roles, and surfaces
verified worker advisories instead of hiding crowded-family guidance.
Configured plot edits display their stored values, and an explicit Explore
action can seed—but never render—a session draft from one configured request
with inherited defaults. Dense heatmaps omit redundant hollow valid-sample
markers above 10,000 samples per fluid facet while retaining every sampled
color cell and every invalid-state cross. Finally, maximized close resolves the
remembered monitor from the persisted normal geometry rather than a WSLg frame
reported on another screen, while missing placement state centers on the
primary screen. These corrections change no YAML, worker protocol, emitted
rows, interpolation policy, or scientific identity.

Two earlier failed remote runs exposed a real QML lifecycle warning, not a
scientific, worker, inspection, or packaging failure. Rapid Dataset-to-Run
navigation replaced the central page `Loader` while `SearchableChoiceList`
still had a `ListView` delegate under incubation. Qt then reported both
`Loader: Cannot create delegate` and `Object or context destroyed during
incubation`. The local correction lazily instantiates each page on first visit
and retains it until runtime teardown, so navigation changes visibility rather
than destroying live delegates. Repeated runtime creation also avoids resetting
the already selected Basic Controls style. Warning assertions remain strict,
and a deterministic rapid Dataset-to-Run-to-Dataset regression verifies page
identity and warning-free navigation. The corrective commit and subsequent
remote checks pass.

- Step 1 is complete and this tracked Stage 3 contract is the implementation
  authority.
- Step 2 is implemented. One composition-owned
  `DatasetExecutionController` now owns saved-configuration validation,
  generation, progress, cancellation, typed results, saved-baseline relation
  state, and the write side of Run activity. Request UUID reservation, initial
  schema-version-1 record persistence, and worker start occur synchronously
  without an event-loop handoff. Progress persistence is coalesced to at most
  four writes per second while phase and terminal changes persist immediately.
- The former Widgets Run and Jobs adapters were removed in Step 12 after QML
  parity and public-launcher migration.
- Step 3 is implemented. The QML frontend exposes the authoritative
  saved-configuration Run workflow through a numbered responsive page and a
  Run-specific inspector. Validate, Generate, cooperative Cancel, and delayed
  Force Stop cross the root runtime bridge through queued composition-facade
  signals; QML does not call the execution controller re-entrantly.
- Exact saved path and SHA-256 state, typed phase/progress, terminal results,
  saved-baseline relation, and independent activity-persistence degradation
  are projections of the existing `DatasetExecutionController`. Real-worker
  regressions prove validation and generation remain on Run, persist their
  schema-version-1 activity records, and retain current-saved-baseline identity
  across later unsaved draft edits.
- Step 4 is implemented. One composition-owned `InspectionController` now owns
  direct-child workspace source discovery, worker inspection sessions, typed
  source-kind projections, exact revision-bound table selection, bounded
  preview paging, integrity presentation, and the inspected plot context.
  Sources are revealed 20 at a time, sorted by nanosecond modification time
  with a stable resolved-path tiebreaker, and symbolic links are excluded.
- Dataset failure layer, code, and property counts remain three independent
  models. Preparation array exports are flattened one row per logical named
  array so mixed shapes and dtypes within one artifact remain truthful. Legacy
  artifacts without logical-array metadata remain visible with an explicit
  unavailable projection.
- `carnopy.app.source_inspection` and `carnopy.app.table_preview` remain
  worker-only. Importing the controller and Qt models does not load them or
  pandas, PyArrow, NumPy, CoolProp, or Matplotlib. The former Widgets Inspect,
  source-list, and Plot adapters were removed in Step 12 after QML parity.
- Step 5 is implemented. The QML frontend now exposes the bounded
  workspace source list, explicit external file/folder choices,
  Summary/Tables/Arrays/Diagnostics views, a virtualized 100-row table page,
  automatic first preview after explicit inspection, local paging, Focus
  Table, and an Inspect-specific context inspector. All operations cross queued
  root-facade signals; QML consumes only the lightweight typed models from Step
  4 and does not import or materialize source data. Dataset shape presentation
  includes the worker-reported row totals and number of columns.
- Workspace-generated outputs remain the primary Inspect source path: their
  typed workspace rows show source kind before the generated directory ID.
  External CSV/Parquet and run/bundle dialogs are explicitly for sources not
  selected from that list, and QML `file:` URLs are normalized by the
  composition facade before worker inspection.
- Dataset, Run, Inspect, Visualization, and Activity navigation are available
  for an active workspace and show their own prerequisite states. YAML Preview
  alone requires an open document. Historical outputs and session plots remain
  reachable without fabricating a current configuration. The Dataset draft
  check and Run saved-snapshot check are labeled as optional diagnostics;
  generation still performs its own mandatory fresh worker validation.
- The QML runtime now applies the selected application palette before creating
  the QML engine, preventing fallback file dialogs from caching the platform
  highlight until the first theme change. Inspection fact layouts no longer
  feed a child width back into the `RowLayout` measuring it, and supported
  interaction tests remain warning-free.
- Dataset failure layer, code, and property aggregates remain visibly separate.
  Logical arrays retain per-array shapes and dtypes, and integrity wording stays
  source-kind-aware. The explicit `Explore in Visualization` affordance remains
  disabled until Step 8 binds the authoritative session-plot controller to QML;
  it does not simulate navigation or rendering.
- Step 6 is implemented. One composition-owned `ActivityController` now owns
  schema-version-1 record loading, typed projection, selection, diagnostic
  presentation, record-only removal, effective `Interrupted` state, and
  recognized staging recovery. It never starts a request or writes an activity
  record; `DatasetExecutionController` retains that write-side ownership.
- Stored `running` records without the matching live execution request display
  as interrupted without rewriting their JSON. Record removal leaves generated
  runs and figures untouched. Recovery rescans selected direct-child staging
  paths, compares path/device/inode identity, and then reuses the existing
  containment, type, symlink, and identity checks before deletion.
- Importing the controller remains free of worker inspection and heavy
  scientific/data/rendering modules. The former Widgets Jobs adapter was
  removed in Step 12.
- Step 7 is implemented. `ConfiguredPlotResultsController` discovers
  configured results only from successful persisted generation records and
  their exact recorded report paths. `plot_artifacts.py` checks workspace
  containment, symlink exclusion, run/spec/context identity, ordered canonical
  requests and outcomes, per-request sidecars, recorded source identity, image
  hashes, and report/sidecar/result counts before projecting the approved
  recorded-provenance relationship.
- PNG and SVG previews use opaque revision-bound tokens through a QML image
  provider; no arbitrary file URL crosses into QML. PDF remains explicit
  external-open only. Image-plus-sidecar export revalidates the source pair,
  stages both destination files without overwrite, and rewrites only the
  exported `image.path` and `image.sidecar_path` fields.
- One composition-owned `SessionPlotController` now owns the inspected-source
  plot draft, render request, structured failure, committed result, and preview
  token. Local invalidity focuses typed fields; worker messages are never
  parsed for navigation. Failed rendering retains the edit and prior committed
  result, while success commits the new result and destroys the temporary
  draft. Session edits guard source, workspace, and shutdown replacement but
  remain separate from YAML dirtiness and unrelated Dataset Save behavior.
- Plot-result controllers and the preview provider import only the lightweight
  request-identity path and do not load source inspection, table readers,
  pandas, PyArrow, NumPy, CoolProp, Matplotlib, or visualization renderer/model
  modules. The former Widgets Plot adapter was removed in Step 12.
- Step 8 is implemented. QML Visualization now presents the configured editor,
  record-driven configured-result evidence, opaque PNG/SVG previews, explicit
  PDF opening, provenance-preserving export, and session-only rendering over
  the Step 7 controllers. Page and tab entry remain worker-idle, and the
  emitted-state p–v/T–s correction preserves exact finite coordinates while
  replacing dense per-series legends with a continuous color scale. New
  inspected-data session edits require deliberate plot-kind and field
  selection; plot-kind help names each visual encoding and verified rendering
  advisories remain visible with the result.
- Step 9 is implemented and committed. The QML rail now enables **Activity and
  Recovery** for an active workspace. Its **Activity** page exposes **Run
  activity** and **Staging Recovery** tabs, virtualized record and candidate
  lists, typed selected-record details, an explicitly expanded diagnostic
  envelope, exact selected recovery paths, and confirmation before either
  private-record or staging removal.
- Activity selection and refresh remain local presentation operations on the
  read-side controller, but QML dispatches them through queued root signals so
  a clicked model delegate is not rebound during its own input callback.
  `Inspect Run`, `View Plots`, private-record removal, and recovery removal
  cross queued root signals into `DesktopController`.
  Inspect submits the exact recorded output directory before navigating;
  View Plots selects the exact generation request and opens the configured
  subview without inspection or rendering. Neither public launcher has
  migrated.
- Step 10 is implemented and committed. Run-result, Activity-record, Inspect, and
  configured-empty-state actions now share composition-owned helpers rather
  than duplicating navigation logic in QML. **Inspect Run** submits the exact
  generated output directory and navigates to Inspect when the request is
  accepted. **View Plots** selects the exact generation record even when it
  contains no configured visualization report, so the configured subview can
  present an explicit empty state. **Explore this run** performs an explicit
  inspection of that exact output and enters inspected-data exploration only
  after the matching inspection succeeds; it never creates or renders a plot.
- Busy shutdown is operation-specific. Generation close requests cooperative
  cancellation and completes only after the coordinator becomes idle. Plot
  rendering may use its parent-owned force-stop/finalizer path, but any staging
  cleanup failure aborts close and remains visible. Configuration, inspection,
  and preview requests without safe cancellation remain wait-only. Existing
  configured/session transient-edit, dirty-document, workspace, and source
  replacement guards remain authoritative below QML.
- Step 11 is implemented. `carnopy-gui` now resolves directly to
  `carnopy.app.qml_launcher:main_gui`, and `carnopy-app` resolves to the same
  runtime through `carnopy.app.qml_launcher:main_app`. Argument parsing,
  `--help`, and `--version` remain lightweight and import no PySide6 module.
  Both commands preserve `--workspace`, `--qt-platform`, the stable
  `.carnopy-gui` workspace marker, and the existing `QSettings` identity.
- Installed-distribution smoke starts both public command aliases rather
  than treating the module launcher as a private substitute. Linux, Windows,
  and macOS QML workflow jobs likewise execute the generated console scripts,
  including explicit Windows executable paths.
- Step 12 is implemented locally. Fourteen obsolete QWidget presentation
  modules are removed: the legacy launcher and main window; configuration,
  execution, inspection, source, activity, plot, and visualization pages;
  dialogs and form/widget helpers; and the old image-preview widget. Five
  implementation-specific test modules are removed, while worker-side source
  inspection coverage remains in its mixed test file.
- The installed plot smoke now decodes a worker-produced artifact through the
  QML verified-preview registry and image provider rather than constructing the
  deleted QWidget preview. Distribution inventories reject the retired modules,
  and packaging tests enforce that `qml_runtime.py` is the only remaining app
  root module importing `PySide6.QtWidgets` for native dialogs and
  `QApplication` integration.
- The deletion removes 3,407 source lines, 2,487 lines from the five deleted
  implementation-specific test modules, and 83 obsolete QWidget/duplicate
  discovery lines from the retained source-inspection test. These figures are
  historical evidence of removed frontend overlap, not a quality metric. No
  public schema, worker protocol, scientific behavior, dependency, or lock
  change is included.

### Permanent scientific and process boundaries

- Run only exact saved configuration bytes. Generation performs fresh worker
  validation before backend initialization; no earlier validation result
  authorizes it.
- Keep CoolProp, pandas, PyArrow, NumPy, Matplotlib, scientific pipelines,
  table readers, source inspection, and rendering implementations outside the
  QML process.
- Keep one globally active short-lived worker request and the existing private
  versioned JSON Lines protocol.
- Preserve public YAML, normalized schemas, scientific identity, artifact
  layouts, row order, retained failures, exact source revisions, hashes,
  no-overwrite behavior, and worker authority.
- Existing Dataset backend and model selection remains authoritative. Run,
  Inspect, and Visualization display captured provenance and do not mutate the
  backend or model.
- Preserve the existing plot kinds: `property_curves`, `property_heatmap`,
  `xy`, `pv`, and `ts`. Do not add interpolation, formulas, inferred states,
  contours, phase envelopes, thermodynamic cycles, or new plot schemas during
  parity.
- The obsolete Widgets adapters were removed only after equivalent QML paths
  and both public launchers were verified. Do not recreate a second desktop
  presentation without an explicitly approved product boundary.

### Controller ownership

`DesktopController` remains the composition and lifecycle authority and owns
one operative instance of:

| Controller | Authoritative responsibility |
| --- | --- |
| `DatasetExecutionController` | Exact saved-snapshot validation and generation, request state, progress, cancellation, result, and write-side Run activity |
| `InspectionController` | Source catalog, worker inspection result, typed summaries, array metadata, table selection, and bounded preview |
| `ActivityController` | Read-side activity projection and removal plus staging-recovery projection and removal |
| `ConfiguredPlotResultsController` | Persisted generation selection, visualization report verification, ordered outcomes, and configured previews |
| `SessionPlotController` | One inspected-source plot draft, explicit worker render, session result, preview, and export |
| verified preview provider | Opaque-token PNG/SVG reads and revalidated PDF opening |

Controllers consume JSON-compatible worker payloads but expose typed Qt
properties and models. QML must not parse worker envelopes, job JSON, arbitrary
paths, nested scientific dictionaries, or English messages to make lifecycle
decisions.

### Transactional Run startup and persistence

`DatasetExecutionController` owns both saved-configuration execution and the
write side of Run activity. `ActivityController` never starts or updates a
worker request.

Add these private coordinator operations:

```text
reserve_request(owner, request_type) -> RequestReservation
start_reserved_request(reservation, payload, finalizer=None) -> RequestSession
abandon_reserved_request(reservation) -> None
```

One `DatasetExecutionController` Qt slot performs this sequence synchronously
in one call stack:

```text
reserve UUID
→ atomically persist the schema-version-1 initial activity record
→ start the worker with that UUID
→ return the active session
```

No queued signal, event-loop handoff, `processEvents()`, coroutine yield, or
background task may occur between those operations. A reservation prevents
re-entrant request startup internally but does not expose global busy state.
The initial JSON write, flush, `fsync`, and atomic replacement must complete
before `WorkerClient.start_request()`. Public busy state begins only after
persistence succeeds and the reservation is promoted to an active session.

- Initial persistence failure abandons the reservation and starts no worker.
- Worker-start failure writes a typed start failure to the new record when
  possible and then abandons the reservation.
- The existing `start_request()` remains a convenience wrapper for operations
  that do not need durable pre-start recording.
- Phase and terminal changes persist immediately.
- Live progress remains unthrottled in the UI, while record writes are
  coalesced to at most four per second.
- A later persistence failure is surfaced independently and does not change the
  scientific worker result. The terminal write receives one bounded retry.

Expose:

```text
activityRecordAvailable
activityPersistenceIssue
```

`activityRecordAvailable` means that a readable record exists for the current
request, even if its latest update failed. `activityPersistenceIssue` reports
degradation separately from execution state.

Retain private job schema version 1 and extend it only with optional fields.
Existing valid `.carnopy-gui/jobs/*.json` records remain readable. Derive new
projections from their existing configuration, summary, and terminal-envelope
fields when possible. Missing optional fields produce explicit unavailable
state rather than an unreadable record. A stored `running` record without the
matching live coordinator request is projected as `Interrupted` without
rewriting the file. If additive version-1 storage proves insufficient, stop for
maintainer review rather than silently creating an incompatible schema.

Persist only saved-configuration validation and generation requests initiated
from Run. Do not persist Save validation, Dataset-page standalone validation,
inspection, table preview, or session plotting.

### Exact saved-baseline execution identity

Execution requires an active workspace and an exact `SavedConfigSnapshot` that
is saved, clean when captured, readable, hash-matching, and byte-identical to
the open document baseline. Expose:

```text
snapshotAvailable
snapshotPath
snapshotSha256
snapshotIssue
operation
state
phase
phaseCancellable
completedRows
totalRows
canValidate
canGenerate
canCancel
canForceStop
resultConfigurationPath
resultConfigurationSha256
resultMatchesCurrentSavedBaseline
currentDraftDirty
resultRelationIssue
failureCategory
failureCode
failureMessage
```

Execution states are:

```text
unavailable
ready
starting
running
cancellation_requested
force_stopping
succeeded
invalid
failed
cancelled
force_stopped
```

A stable worker `config`/`invalid_config` rejection is `invalid`; other
worker, transport, protocol, or operational failures are `failed`.

A result matches the current saved baseline only when the same workspace is
active, the resolved saved path is unchanged, the saved baseline SHA-256 equals
the captured execution SHA-256, and the on-disk saved file still hashes to that
value. Unsaved edits do not make the result historical. Show:

```text
Generated from the current saved configuration; unsaved draft changes now exist.
```

A result becomes historical only after workspace or configuration replacement,
a changed saved path, a later successful Save with a different SHA-256, or
external replacement of the saved file.

Generation result projection includes its request, run, status, output
directory, row counts, `spec_id`, `generation_context_id`, `output_request_id`,
and configured-visualization summary. The user remains on Run after completion
and explicitly chooses another workflow.

### Inspection worker boundary

Keep these modules worker-only:

```text
carnopy.app.source_inspection
carnopy.app.table_preview
```

They import or reach pandas and PyArrow and must remain lazily imported inside
worker request handlers. `InspectionController`, its Qt models, and QML must
not import either module or any module that imports pandas, PyArrow, NumPy,
CoolProp, or Matplotlib. The controller receives only the worker's
JSON-compatible inspection and preview payloads and projects them with
lightweight QtCore, standard-library, and private model code.

A clean-process import-isolation regression must prove that importing the QML
inspection controller does not load:

```text
carnopy.app.source_inspection
carnopy.app.table_preview
pandas
pyarrow
numpy
CoolProp
matplotlib
```

### Typed inspection models

Expose:

```text
state: empty | loading | ready | stale | failed
sourcePath
sourceKind
revision
integrityStatus
integrityLabel
issue
selectedTableId
previewState
previewFirstRow
previewLastRow
previewTotalRows
canExplorePlots

workspaceSourcesModel
sourceSummaryModel
identitySummaryModel
backendSummaryModel
rowSummaryModel
phaseCountsModel
failureLayerCountsModel
failureCodeCountsModel
failurePropertyCountsModel
sweepDeltaReasonCountsModel
preparationQualityErrorsModel
diagnosticsModel
tablesModel
arraysModel
tableModel
```

Dataset inspection currently provides three independent failure aggregates:
`failure_counts.layer`, `failure_counts.code`, and
`failure_counts.property`. Preserve them as separate models:

- `failureLayerCountsModel`: `failureLayer`, `count` (the private Qt role is
  prefixed because `layer` is a final `QQuickItem` property);
- `failureCodeCountsModel`: `code`, `count`;
- `failurePropertyCountsModel`: `property`, `count`.

Do not add a combined `failureSummaryModel` and never imply that separately
aggregated layer, code, and property values occurred in the same row. Sweep
delta-reason counts and preparation quality errors remain separate
source-specific projections. Missing aggregates expose empty models and
explicit availability state; they are never synthesized.

`diagnosticsModel` may expose source-kind-tagged facts already present in the
worker payload, with stable `section`, `label`, `value`, `severity`, and
`issue` roles. It must not infer relationships, checks, or scientific
conclusions. Raw envelopes may appear only as preformatted diagnostic text,
never as lifecycle authority.

`tablesModel` exposes stable ID, label, format, and SHA-256 roles.
`tableModel` owns bounded columns and rows and preserves worker order.

### Array metadata projection

`arraysModel` is one row per logical named array, not one row per artifact.
Stable roles are:

```text
artifactId
artifactLabel
format
artifactSha256
arrayName
shape
shapeDisplay
dtype
metadataAvailable
issue
```

Multiple rows may share one artifact ID and recorded path. Shape and dtype come
from each entry in the artifact's nested `arrays` mapping. Never apply an
artifact-level float dtype to an auxiliary array that records another dtype.
NPZ and SafeTensors artifacts can therefore expose features, targets, numeric
auxiliaries, and categorical arrays independently.

A legacy artifact without nested array metadata remains visible as one
artifact-only row with `metadataAvailable=false`; logical-array name, shape,
and dtype remain unavailable. The controller and QML never open or materialize
NPY, NPZ, or SafeTensors bytes.

### Source discovery and bounded preview

- Inspect only direct children of the workspace output root and skip symbolic
  links.
- Reveal 20 candidates initially and 20 more per explicit request.
- Sort by `st_mtime_ns` descending, then resolved path text as a stable
  tiebreaker. This is a new Stage 3 presentation rule.
- Refresh on workspace activation, successful generation, page entry, and
  explicit Refresh.
- Treat source-kind hints from discovery as presentation hints. Worker
  classification is authoritative.
- Selecting another source clears the committed plot context before starting
  inspection. A failed inspection cannot leave the previous source plot-
  eligible.
- After an explicit successful inspection, select the first table when one
  exists, make Tables the active tab, request the first 500-row worker block,
  and display rows 1 through 100. This automatic preview is an approved UX
  consequence of explicit inspection, not automatic source inspection.
- Preserve emitted row order. Add no sorting, filtering, interpolation,
  inferred rows, or implicit materialization.
- Display one-based UI row positions and never present them as `case_id`.
- Bind every preview and session plot to the exact inspection revision. A
  mismatch clears plot eligibility and marks inspection stale.

Integrity vocabulary is source-kind-aware. Use `Verified recorded artifact`
only when the worker established the recorded dataset hash relationship and
`Unrecorded source` for loose data without recorded provenance. Do not reuse
that exact vocabulary for sweep or preparation summaries unless their payload
establishes it. Recorded mismatches remain rejected.

### Existing scientific plot scope

Use these presentation labels without changing public kinds:

```text
property_curves    → Property curves
property_heatmap   → Sampled property heatmap
xy                 → Custom X–Y plot
pv                 → p–v emitted-state diagram
ts                 → T–s emitted-state diagram
```

`Custom X–Y plot` permits any two fields the inspected plot context marks
`axis_allowed`, plus compatible existing grouping, exact filters, series
selections, emitted fluids, display units, and scales. It does not permit
backend-only fields, arbitrary formulas, interpolation, or invented states.

Help must state that p–v uses emitted pressure and
`specific_volume = 1 / mass_density`, while T–s uses emitted temperature and
specific entropy. Invalid and missing gaps remain gaps. Neither kind constructs
a thermodynamic cycle, process path, phase envelope, or saturation dome.
Additional plot kinds require a later scientific review.

### Configured results and session exploration

Visualization has two top-level subviews:

```text
Configured for generation
Explore current data
```

Configured for generation contains the existing authoritative YAML configuration editor
and a clearly separate historical generated-results area. Entering the page or
changing subviews does not inspect or render anything.

Configured-result discovery is exclusively record-driven:

1. select a successful persisted generation record;
2. read its exact `output_directory`;
3. read its exact `visualization.figure_directory` and
   `visualization.report_path`;
4. enumerate only the report's ordered outcomes.

Never discover configured outcomes by scanning a figure directory. When a
terminal record lacks the required evidence, show **Evidence incomplete** and
do not fall back to directory contents.

For every report:

- verify containment under the active workspace roots and reject symbolic-link
  components;
- match run ID, `spec_id`, `generation_context_id`, source directory, and
  visualization paths to the generation record;
- parse the ordered normalized requests;
- recompute the report-wide visualization identity through the lightweight
  `carnopy.visualization.requests.request_id()` path;
- match each outcome to exactly one request by deterministic position and its
  unique name and kind;
- require each completed sidecar's canonical normalized request to equal that
  exact report request;
- match the sidecar's report-wide visualization ID and source identity;
- verify report, image, and sidecar containment and image bytes against the
  sidecar SHA-256.

`ConfiguredPlotResultsController` and `plot_artifacts.py` may use lightweight
request canonicalization from `visualization.requests` or a dependency-free
helper extracted from it. They must not import `visualization.configuration`,
`visualization.models`, or any module that imports pandas or Matplotlib.

Use these labels:

```text
Recorded provenance consistent
Evidence incomplete
Provenance mismatch
```

Do not use bare **Verified**: internal cryptographic and structural consistency
is not independent scientific validation.

`Explore current data` consumes the current ready Inspect selection, has no
duplicate source picker, uses a distinct workflow-local `PlotDraft`, remains
session-only, and never changes YAML. It renders only after explicit Render.
An explicit Explore action on a compatible configured row opens a session
draft with that row and its inherited shared defaults. It starts no worker and
does not join the two authorities; the user reviews the session draft and
chooses Render.

### Preview and export safety

QML never receives an arbitrary file URL. A private opaque-token image provider
binds each token to:

```text
workspace identity
canonical image path
expected image SHA-256
format
verification revision
```

Revalidation creates a fresh token. Disable ordinary QML image caching where
it could preserve invalidated bytes. PNG and SVG use in-app focus mode with
Fit, zoom in, zoom out, 100 percent, Escape/Close, and focus restoration. PDF
is revalidated immediately before explicit external opening.

Exporting an image and provenance sidecar must:

1. revalidate the record, report, sidecar, and image;
2. require both final destination paths to be absent;
3. stage both files in the destination directory;
4. copy the image bytes;
5. parse the sidecar and change only `image.path` and
   `image.sidecar_path`;
6. preserve the normalized request, source identity, original image SHA-256,
   scientific settings, advisories, and runtime metadata;
7. write the rewritten staged sidecar deterministically;
8. promote both files exclusively;
9. remove only operation-owned staging or partially promoted files whose
   identities still match.

This is a no-overwrite pair operation, not a claim of complete two-file crash
atomicity.

To obtain another format for a configured plot, inspect or reuse its exact
source run, convert its verified normalized request into a session draft,
choose another format, assign a distinct default name such as `<name>-svg`,
and render explicitly. Never rewrite a configured artifact.

### Session plot state and failures

Expose:

```text
sourceAvailable
sourcePath
inspectionRevision
activePlotDraft
hasActiveEdit
committedRequestAvailable
state
phase
canRender
canForceStop
resultAvailable
previewToken
previewFormat
previewIssue
advisories
```

Session states are `unavailable`, `ready`, `editing`, `rendering`,
`force_stopping`, `succeeded`, and `failed`.

- Ordinary navigation does not discard an active edit.
- Local `PlotDraft` invalidity retains the editor and focuses its typed local
  field and row.
- Worker failure retains the editor and displays structured category, code,
  message, and issues.
- Focus a worker-side field only when structured details actually provide its
  path. Never infer a field by parsing English text.
- Successful Render commits the request and result and destroys the temporary
  draft.
- Cancel destroys only the temporary draft and returns to the previous
  committed request and result.
- Changing inspected source or revision clears the committed session state only
  when no session edit is active.

### Activity and Recovery

`ActivityController` owns only loading, typed projection, selection, details,
record removal, effective interrupted state, and recovery. It exposes:

```text
recordsModel
selectedRecordId
selectedRecordState
selectedRecordSummary
selectedDiagnosticText
canInspectRun
canViewPlots
canRemoveRecord
recoveryCandidatesModel
selectedRecoveryCount
recoveryState
recoveryIssue
```

Collections exposed to QML are Qt models with stable roles. Raw envelopes may
appear only as preformatted diagnostic text.

Run records do not own generated artifacts. Removing a record deletes only its
private JSON after warning that the run and figures remain.

Recovery stays bounded to recognized direct staging children. Describe its
safety as **rescan-and-identity-checked removal**, not as a complete TOCTOU
guarantee:

- rescan immediately before removal;
- verify containment, type, device/inode identity, and absence of symbolic
  links;
- show exact selected count and paths;
- remove only explicitly selected recognized candidates;
- never remove immutable runs or arbitrary directories.

This terminology correction is nonblocking; the safety checks remain required.

### Exact cross-page actions

**Inspect Run**

- Take the exact output directory from the typed generation result or selected
  activity record.
- Explicitly call `InspectionController.inspectSource()`.
- Navigate to Inspect once the request is accepted.
- Remain on Inspect with typed failure feedback if inspection fails.

**View Plots**

- Select the exact originating generation request ID.
- Navigate to Visualization → Configured for generation.
- Do not inspect or render automatically.
- If no configured visualization existed, show an explicit empty state with
  **Explore this run**.

**Explore this run**

- Explicitly inspect the generation's exact output directory.
- On success, navigate to Visualization → Explore current data.
- On failure, remain in the current context and show typed failure feedback.
- Never create or render a plot automatically.

### Transient-edit and busy lifecycle guards

Expose:

```text
hasConfiguredPlotEdit
hasSessionPlotEdit
hasAnyTransientEdit
```

- Configured edit retains the existing Save, document, mode, coordinate,
  visualization-wide, workspace, and shutdown guards.
- Session edit blocks inspection-source replacement, workspace replacement,
  and shutdown.
- Session edit is not YAML dirty and does not block unrelated Dataset or
  configured-Visualization edits or Save.
- Workspace replacement and shutdown check both edit types before preflight
  and again before commit.
- QML cannot bypass guards through child-controller destructive slots.
- Active generation close offers **Keep Open** or cooperative
  **Cancel and Close** and waits for safe completion. Close never invokes
  generation force-stop implicitly.
- Run may retain its delayed explicit Force Stop action.
- Active plot render may offer explicit **Force Stop and Close** only through
  the parent-owned staging finalizer. Cleanup failure aborts close and exposes
  the staging issue.
- Configuration, inspection, and preview requests without a safe cancellation
  path must finish before close.

### QML experience

Run uses:

1. Saved configuration.
2. Validate only or Generate.
3. Worker phase and row progress.
4. Result and explicit next actions.

Show the exact path and abbreviated SHA-256 with the full value available
accessibly. Distinguish completed rows, invalid rows, run status, configured-
visualization status, saved-baseline relation, and activity-persistence state.
Do not navigate automatically.

Inspect wide mode uses a bounded source list, central tabbed workbench, and
context inspector. Tabs are Summary, Tables, Arrays, and Diagnostics. Tables is
selected after an explicit inspection when tables exist. **Focus Table** hides
the source list and inspector, expands the virtualized table, and restores both
surfaces and keyboard focus on exit. Compact and narrow layouts reuse existing
drawers rather than nested page scroll areas.

The Inspect inspector shows only worker-derived source, revision, integrity,
backend/model/version, reference-state, row, failure, selected-table, column,
unit, and hash facts. Do not invent checks such as monotonicity.

Configured for generation shows originating configuration SHA, run and visualization
identities, saved-baseline relation, and deterministic completed, failed, and
skipped cards. Failures show exact type and message and never a placeholder
graph. Explore current data uses an inline editor beside the preview in wide
mode and a stacked editor and preview at smaller widths.

Activity uses a bounded record list, selected summary and details, exact
Inspect/View actions, record removal, and an expandable raw diagnostic
envelope. Recovery uses its own tab with candidate count, path, age, issue,
selection, rescan, and confirmed removal.

Page-specific inspector content must be split into small components loaded by
page identity. Do not turn `Main.qml` or one inspector component into a second
controller.

Navigation availability is:

- Workspace always available.
- Dataset requires an active workspace.
- YAML Preview requires an open document.
- Run, Inspect, Visualization, and Activity and Recovery require an active
  workspace but render meaningful prerequisite states internally.
- Visualization may show persisted configured results without an open
  document.
- Explore current data requires a ready inspected dataset.
- Future workflows remain disabled, explained, and outside keyboard focus.

### Stage 3 Step sequence

Documentation synchronization remains part of every implementation boundary.
Update this Stage's status after every Step, and update
`DESKTOP_ARCHITECTURE.md` in the same Step whenever controller ownership,
process isolation, lifecycle authority, launcher behavior, or frontend
structure changes. When reviewed documentation remains accurate, say so in the
handoff rather than adding a meaningless edit.

#### Step 1 — Lock the tracked Stage 3 contract

Recommended commit:

```text
docs(app): lock GUI-2 Stage 3 parity contracts
```

Update this document with the complete Stage 3 contract and preserve Stages 0
through 2 and 4 through 8. Stop for human review and commit before
implementation.

Implemented on 2026-07-23 as the first Stage 3 commit. It records the final
navigation order, synchronous Run reservation and activity-persistence
contract, saved-baseline semantics, worker-only inspection boundary, typed
inspection and Activity projections, configured-result provenance rules,
sidecar-rewriting export, cross-page actions, QML launcher migration,
backward-compatible `carnopy-app` alias, Widgets-retirement gate, and separate
`0.1.0a4` release boundary. No implementation code changed in this Step.

#### Step 2 — Extract authoritative execution state

Recommended commit:

```text
refactor(app): extract dataset execution state
```

Primary areas:

```text
src/carnopy/app/execution_controller.py
src/carnopy/app/request_coordinator.py
src/carnopy/app/jobs.py
src/carnopy/app/desktop_controller.py
src/carnopy/app/execution_page.py
src/carnopy/app/jobs_page.py
tests/test_app_execution_controller.py
tests/test_app_request_coordinator.py
tests/test_app_jobs.py
DESKTOP_ARCHITECTURE.md
GUI2_PLAN.md
```

Implement exact snapshots, synchronous reservation/persistence/start,
schema-version-1-compatible activity writing, progress coalescing, saved-
baseline relation state, cancellation and force-stop policy, and a narrow
temporary Widgets adapter.

Stop if this requires changing the worker protocol, generation semantics, or
backward-readable job schema.

Implemented on 2026-07-23 without a worker-protocol, generation-contract, or
job-schema change. The controller persists the initial activity record before
starting the worker with the same reserved UUID, exposes persistence
degradation independently from the scientific outcome, and retains exact
saved-baseline identity across later unsaved draft edits. Existing schema-
version-1 records remain readable, and the temporary Widgets pages consume the
new ownership boundary without receiving QML-only presentation behavior.

#### Step 3 — Add the QML Run workflow

Recommended commit:

```text
feat(app): add the QML dataset execution workflow
```

Add the numbered flow, typed progress and results, Validate, Generate, Cancel,
delayed explicit Force Stop, Inspect Run, View Plots, responsive/keyboard
behavior, and Run-specific inspector. Do not navigate automatically.

Implemented on 2026-07-23 without a protocol, schema, dependency, or scientific
change. The page binds the Step 2 execution controller and uses queued
root-level signals for every worker action. `Inspect Run` and `View Plots` are
present as honest downstream actions but are not enabled before their
authoritative inspection and configured-result controllers exist. Focused
tests exercise responsive layout, the dedicated inspector, real worker
validation and generation, activity persistence, no automatic navigation, and
saved-baseline versus dirty-draft semantics.

#### Step 4 — Extract inspection state and models

Recommended commit:

```text
refactor(app): extract inspection state and table models
```

Primary areas:

```text
src/carnopy/app/inspection_controller.py
src/carnopy/app/inspection_models.py
src/carnopy/app/table_model.py
src/carnopy/app/desktop_controller.py
src/carnopy/app/inspection_page.py
src/carnopy/app/sources_page.py
src/carnopy/app/plot_page.py
tests/test_app_inspection_controller.py
tests/test_app_table_preview.py
DESKTOP_ARCHITECTURE.md
GUI2_PLAN.md
```

Implement bounded source discovery, separate failure aggregate models, source-
kind summaries, logical arrays, revision-bound previews, heavy-import
isolation, and temporary Widgets adapters. Keep `source_inspection.py` and
`table_preview.py` worker-only and record that boundary durably.

Implemented on 2026-07-23 without a worker-protocol, public-schema, dependency,
or scientific change. `DesktopController` owns the one operative controller.
Collections exposed for QML are stable-role Qt models, while raw nested summary
data is retained only as preformatted diagnostic text and a copied payload for
the temporary Plot-page adapter. An explicit inspection queues the first table
preview only after the completed request releases the global coordinator.
Preview row positions are one-based presentation positions; worker blocks
remain bounded to 500 and local pages to 100.

#### Step 5 — Add the QML Inspect workbench

Recommended commit:

```text
feat(app): add the QML inspection workbench
```

Add the bounded source list, Summary/Tables/Arrays/Diagnostics tabs,
virtualized table, automatic first preview after explicit inspection, Focus
Table, source-kind integrity language, root-facade external source actions, and
explicit Explore in Visualization.

Implemented on 2026-07-26 without a worker-protocol, public-schema, dependency,
or scientific change. The page uses the Step 4 typed models and queued
composition facade, keeps external native-dialog completion outside the dialog
event, and never opens table or array bytes in QML. The table view displays one-
based presentation rows in virtualized 100-row pages backed by bounded 500-row
worker requests. Focused real-worker tests cover explicit source inspection,
automatic preview, Focus Table, and paging through row 150. Session plotting
remains honestly unavailable in QML until Step 8 binds the authoritative
controller introduced by Step 7.
The same completed slice normalizes native-dialog file URLs at the composition
facade, gates Run navigation on a saved execution snapshot, distinguishes its
two optional diagnostic checks from generation's mandatory fresh validation,
applies the startup palette before QML-engine construction, and removes a
recursive Inspect `RowLayout` width dependency. Native dialog placement remains
owned by the platform compositor after Carnopy supplies the transient parent;
Carnopy does not replace native dialogs merely to control their first mapped
pixel position.

#### Step 6 — Extract Activity and Recovery state

Recommended commit:

```text
refactor(app): extract activity and recovery state
```

Move only record loading/projection/selection/removal, interrupted projection,
and staging recovery into `ActivityController`. Do not reopen execution startup
or duplicate Step 2's write-side ownership.

Implemented on 2026-07-26 without a worker-protocol, public-schema, dependency,
or job-schema change. `DesktopController` owns the one operative controller and
propagates workspace context once. Its stable-role record and recovery models
retain malformed records visibly, derive interruption only from the matching
live coordinator session, remove only private record JSON, and reject staging
replacement between selection and deletion. The temporary Widgets Jobs page
contains confirmation and presentation only. Before handoff, the exact remote
Desktop-app failure was traced to destructive QML page replacement rather than
Activity ownership. The same boundary retains lazily loaded visited pages,
makes Basic-style setup idempotent, and adds the fast-navigation regression;
the exact local Desktop-app suite is warning-free.

#### Step 7 — Extract configured-result and session-plot state

Recommended commit:

```text
refactor(app): extract plot result and session state
```

Add `ConfiguredPlotResultsController`, `SessionPlotController`,
`plot_artifacts.py`, and the verified preview provider. Implement record-driven
verification, per-request sidecar matching, opaque tokens, rewritten export
sidecars, session editing/rendering, precise p–v/T–s help, and narrow temporary
Widgets adapters.

Stop if current record/report/sidecar evidence cannot support the approved
consistency relationship without a protocol or public-schema change.

Implemented on 2026-07-26 without a worker-protocol, public-schema, dependency,
or persisted-record change. The composition now owns one configured-result
controller, one session-plot controller, and one opaque preview registry. The
configured controller is record-driven and verifies each report outcome
against its exact canonical request, provenance sidecar, recorded source
identity, and image. Export revalidates and rewrites only destination paths in
the copied sidecar. The session controller owns one transient edit and preserves
the last committed result across a failed retry. The temporary Widgets Plot
page is a narrow adapter, and clean-process tests enforce the GUI heavy-import
boundary.

#### Step 8 — Complete QML Visualization

Recommended commit:

```text
feat(app): add QML plot results and data exploration
```

Add Configured for generation and Explore current data, deterministic outcome cards,
lazy previews, inline session editing, explicit Render, focus mode, Export/Open
actions, and render-another-format flow. Page entry and tab changes start no
worker.

Implemented locally on 2026-07-26 without a worker-protocol, public-schema,
scientific-algorithm, or dependency change. The QML page now has explicit
**Configured for generation** and **Explore current data** views. Configured results
are selected from successful persisted generation records and display only the
verified ordered report outcomes. PNG and SVG use opaque, cache-disabled image
provider URLs and an in-app focus mode; PDF remains an explicitly revalidated
external-open action. Export routes through the composition façade and the
Step 7 no-overwrite image-plus-rewritten-sidecar operation.

Session exploration binds the one authoritative `SessionPlotController` and
its temporary `PlotDraft`. Creating an edit is explicit, Render is the only
worker-starting action, local and worker failures retain the edit, Cancel
returns to the last committed result, and Edit and render again starts another
explicit edit. A compatible configured row can explicitly seed a populated
session draft with inherited defaults; this bridge starts no worker and does
not modify YAML. Native close and SIGINT offer an explicit **Cancel edit and
close** decision for unresolved configured or session edits; accepting it
cancels only transient edit state before re-entering the ordinary dirty and
busy guards. Hidden editor instances are not retained, preventing duplicate
focus targets. Focused interaction tests prove that entering Visualization,
switching either subview, and beginning or cancelling an edit starts no worker.

Native review on 2026-07-28 exposed an unusable 41-entry legend in a two-fluid
T–s emitted-state result. The underlying separated liquid and gas branches were
scientifically correct: the generated property-table grid contains no emitted
states across the intervening phase interval, and the renderer already refused
to interpolate through the phase-label transition. The corrective renderer
presentation keeps every emitted state and every deliberate break, labels p–v
and T–s as emitted-state diagrams, uses one shared continuous colorbar for a
dense numeric series field instead of a per-facet legend, and records
`phase_break_count` separately from invalid-row `gap_count`. The same
high-cardinality presentation is shared by existing property curves. It does
not construct a saturation dome, cycle, process path, or backend-derived state.
Focused tests compare plotted finite coordinates exactly with emitted rows and
cover both the dense color scale and phase-break provenance.

Stage 3 native acceptance on 2026-07-29 rejected the first configured-result
capture because the result selectors were vertically centered independently,
the top-level Visualization tabs retained generic Controls styling, and focus
mode could center a clamped preview inside an oversized native-image canvas.
The corrective presentation uses flat reference-aligned tabs, top-aligns all
three configured-result columns, gives the run and outcome selectors one
shared wide-layout height, and separates **Fit** from native-pixel **100%**
scaling. Geometry and interaction regressions cover unequal selector counts and
a source image larger than the focus viewport. This is presentation-only: it
does not change plot bytes, preview-token verification, export provenance, or
worker rendering.

The same native pass exposed a shell-availability mismatch: Visualization and
Run were visually disabled without a document even though their prerequisite
states and historical workflows require only an active workspace. A shared
`workspaceState` reaction also routed Visualization back to Workspace when a
session-render request changed global busy state. The correction aligns both
rail instances and page retention with the locked navigation contract while
leaving YAML Preview document-gated. The wide Activity summary grid now gives
**Run records** and **Selected record** equal cells. QtSvg preview decoding also
receives an in-memory compatibility copy with only Matplotlib's empty glyph
definitions and their no-op uses removed; the verified SVG artifact, recorded
hash, sidecar, export bytes, and scientific content are untouched.

Release-candidate review also found that configuration selection opened at an
unrelated native-dialog location and that the Dataset backend and fluid
summary did not match the approved workbench hierarchy. The corrective QML
opens configuration selection in the active workspace's authoritative
`configs/` directory, explains the `configs/`, `outputs/`, and `figures/`
roles, presents the current single CoolProp backend through the same selector
treatment as Model and Mode, and aligns the requested-fluid and canonical-
identity summary. Configuration selection remains explicit because a workspace
may contain multiple YAML documents. This changes no workspace, backend,
configuration, or scientific contract.

Sampler review clarified inclusive point semantics without changing any YAML
field. Valid `linspace` editors now show the signed declared-unit spacing and
the number of intervals implied by their point count. Valid `stepspace`
editors label the existing `step` field as **Step size** and show both the
derived interval and sampled-point counts. The projections reuse the
lightweight sampler validation and reachability rules, import no NumPy, and
remain transient presentation state outside dirty and scientific identity.

The continuing native workflow review also clarified the boundary between
reproducible configured plots and ad-hoc inspected-data plots. Configured rows
remain YAML rendered only by the next Generate, but now expose a prominent
**Preview with inspected data** action that seeds a reviewed session draft and
never renders automatically. A new session draft explicitly selects every
fluid recorded by the inspected source, displays those selections, and becomes
locally invalid if all are removed; no empty selection is interpreted as a
hidden request for every fluid. Workspace output candidates present a readable
mode, UTC timestamp, and short run identity while retaining their exact paths
as authority. Secondary external-source dialogs start in the active
workspace's `outputs/` directory. Large-linear-range advisories now state the
observed minimum, maximum, and ratio and explain that logarithmic presentation
can reveal relative variation among lower positive values; they still never
change the requested scale. These corrections change no YAML, emitted rows,
worker protocol, plot identity, or interpolation policy.

Steps 9 and 10 are implemented and committed with focused verification. Native
human review covers Step 9, and the corrective queued delegate-interaction
regression is part of that accepted boundary.

#### Step 9 — Add QML Activity and Recovery

Recommended commit:

```text
feat(app): add QML activity and recovery
```

Add the two-tab Activity page, bounded records, typed details, exact cross-page
actions, diagnostic expansion, recovery selection, confirmation, and
accessible status presentation.

Implemented. The page consumes only the existing stable-role models and typed
selected summary. Record and recovery removals remain composition-routed and
preserve the controller's record-only and rescan-and-identity-checked safety
contracts. Record selection, refresh, recovery selection, and recovery refresh
also cross queued root signals, preventing model-backed delegates from being
reset or rebound inside their own click/toggle callback. Real delegate-click
regressions cover both record and recovery selection. No worker request starts
when the page or either tab opens.

#### Step 10 — Complete guarded end-to-end parity

Recommended commit:

```text
feat(app): complete guarded QML workflow parity
```

Verify:

```text
Generate → Inspect Run
Generate → View Plots
Configured empty state → Explore this run
Activity → Inspect Run
Activity → View Plots
Inspect → Explore current data
```

Cover workspace/source replacement, both transient edit types, busy close,
cleanup refusal, repeated launch/close, and warning-free teardown. Do not
migrate launchers before this boundary is green.

Implemented and committed on 2026-07-28. All six approved paths cross queued root
signals into `DesktopController` and reuse the exact typed run/output identity:

```text
Generate → Inspect Run
Generate → View Plots
Configured empty state → Explore this run
Activity → Inspect Run
Activity → View Plots
Inspect → Explore current data
```

A completed generation without a configured report remains selectable in the
configured-results controller and presents **Explore this run** instead of
being disabled. Exploration explicitly inspects the generation's recorded
output directory, waits for the matching success, and only then opens the
session-exploration subview; failure stays in the current context with typed
feedback. No cross-page action renders automatically.

Close handling now distinguishes safe lifecycle paths: generation uses
cooperative cancellation, plot rendering uses only its parent-owned
force-stop/finalizer path, cleanup failure keeps the application open, and
other active request kinds must finish. Controller and native QML regressions
cover exact routing, no automatic render, cancellation-to-close, cleanup
refusal, and the existing warning-free runtime boundary. No protocol, public
schema, scientific behavior, dependency, or launcher change is included.

Committed before Step 11 began. The public launcher migration does not alter
these lifecycle or cross-page contracts.

#### Step 11 — Make QML the public desktop frontend

Recommended commit:

```text
build(app): make QML the public desktop frontend
```

Point `carnopy-gui` and compatibility alias `carnopy-app` at the same QML
launcher. Preserve `--workspace`, `--qt-platform`, `--help`, `--version`, the
existing `.carnopy-gui` workspace/settings identity, lightweight help/version,
installed smokes, and missing-extra guidance. Update package inventories and
README migration wording.

Implemented on 2026-07-28. Both project scripts point directly at the
lightweight `qml_launcher` module and select the same QML runtime with their
own stable program names. Help and version exit before PySide6 is imported;
missing-`app` guidance is unchanged; workspace and Qt-platform arguments reach
the existing runtime unchanged. The module entry point remains available for
internal smoke use, but distribution and cross-platform CI now prove both
installed public commands. No dependency, lock, scientific, worker, protocol,
workspace-marker, or settings-identity change is included. Widgets source was
retained solely for the separately verified Step 12 deletion and is now
removed.

#### Step 12 — Retire the Widgets presentation layer

Recommended commit:

```text
refactor(app): retire the Widgets frontend
```

Delete obsolete QWidget pages, dialogs, forms, and implementation-specific
tests only after equivalent QML workflows pass. Retain QtCore controllers,
drafts/models, worker/client/protocol, request coordinator, workspace and
safety helpers, QML runtime, native-dialog integration, scientific code, and
controller/QML tests.

`QApplication`, `QFileDialog`, and `QMessageBox` may remain in the QML runtime.
Widgets retirement removes the duplicate QWidget frontend, not every
QtWidgets runtime class. Record deleted modules and line delta as historical
evidence, not a quality metric.

The Stage 2 graph is already hard-stale under the tracked six-commit cutoff and
must not be queried during Steps 10 through 12. After this structural deletion
settles, refresh only the three public graph artifacts in a separate
`docs(graph)` commit before final acceptance.

Implemented locally on 2026-07-28 after Step 11 and its remote checks passed.
The obsolete `launcher`, `window`, configuration form/editor/widget, execution,
inspection/source, activity, plot dialog/page/preview, and visualization
editor/widget modules are deleted. Their five presentation-specific test
modules are deleted; the worker-side cases in the mixed source-inspection test
remain. This removes 14 source modules and 3,407 source lines, five complete
test modules and 2,487 test lines, plus 83 obsolete QWidget/duplicate-discovery
lines from the retained inspection test. The counts are historical evidence,
not an acceptance metric.

The QML runtime remains the one intentional app-root user of `QtWidgets` for
`QApplication`, native file dialogs, and fallback message boxes. Installed plot
smoke now verifies a worker-rendered image through the opaque-token QML preview
provider. Package inventories and metadata tests reject the retired modules.
QtCore controllers, drafts, models, worker/protocol boundaries, filesystem and
artifact safety, QML resources, native-dialog integration, and all controller,
scientific, protocol, and QML tests remain. No public schema, worker protocol,
scientific behavior, dependency, or lock change is included.

#### Step 13 — Accept and complete Stage 3

Recommended commit:

```text
docs(app): complete GUI-2 Stage 3
```

Create this Step only after all automated and remote gates, Linux native
end-to-end acceptance, and explicit maintainer approval.

- Update this plan and `DESKTOP_ARCHITECTURE.md`.
- Capture a real 1920 by 1080 Dark-mode screenshot from an actual generated
  dataset and internally consistent configured plot. Do not use mock curves,
  committed generated data, personal paths, or a design reference.
- Update README around deterministic thermophysical datasets, explicit
  backend/model provenance, reproducible YAML, retained row diagnostics, the
  real QML workflow, CLI automation, and contribution.
- Present two primary installation paths—isolated desktop through `uv tool`
  and base CLI/library through `pip`—plus one compact optional-extras table.
- Mark Stage 3 complete and Stage 4 active without implementing Stage 4.

Do not add another architecture Markdown file. GitHub Issues is a human-owned
repository setting and must be enabled before README presents it as the
contributor entry point.

### Stage 3 verification and acceptance

Use focused checks for each Step:

```bash
git diff --check
uv run --locked python scripts/check_qml.py
uv run --locked ruff check <changed paths>
uv run --locked ruff format --check <changed paths>
uv run --locked mypy src/carnopy
uv run --locked pytest -q <focused tests>
```

Required regression families include:

- synchronous reservation/persistence/start ordering and re-entrant rejection;
- initial and later persistence failure and backward-readable version-1 jobs;
- saved-baseline versus dirty-draft result relation;
- separate failure aggregate models;
- multiple logical arrays and mixed dtypes in one artifact;
- QML-controller heavy-import isolation;
- source revision, discovery ordering, bounded paging, and row-order retention;
- source-kind integrity vocabulary;
- malformed or tampered records, reports, requests, paths, symbolic links,
  sidecars, and images;
- record-only configured result discovery and per-request matching;
- rewritten export sidecar paths and no-overwrite cleanup;
- no render on page entry;
- local versus worker plot-error focus;
- preview-token cache invalidation;
- exact cross-page actions;
- configured and session edit guards plus busy close;
- interrupted records and rescan-and-identity-checked recovery;
- both public launcher aliases;
- complete QML parity before Widgets deletion.

The final Stage 3 gate is:

```bash
git diff --check
uv lock --check
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src/carnopy
uv run --locked python scripts/check_qml.py
uv run --locked pytest
uv run --locked python scripts/preflight.py
uv pip check --python .venv/bin/python
bash scripts/local_gate.sh prerelease/local-gate
```

Run long preflight and distribution gates once at the final boundary, not after
every Step, unless a failure or cross-cutting change justifies an earlier run.

Remote and manual acceptance requires:

- green ordinary Stage 3 pull-request checks;
- installed-QML startup and focused interaction smokes on Linux, Windows, and
  macOS;
- Linux native workspace, Dataset, YAML, Run, Inspect table, session plot,
  configured gallery, PNG/SVG/PDF, Activity, Recovery, and lifecycle guards;
- 1440 by 900 and 1920 by 1080;
- compact and narrow transitions;
- scale factors 1, 1.5, and 2;
- multi-monitor restoration;
- Dark, Light, Warm, and System;
- no QML warnings, missed first clicks, or multi-second main-thread stalls.

Windows and macOS remain installed-QML alpha smoke coverage, not full native
qualification. Full platform and native-3D release qualification remains Stage
8.

### Separate `0.1.0a4` release

After Stage 3 merges into `main`, use:

```text
branch: release/0.1.0a4
PR:     chore(release): publish Carnopy 0.1.0a4
commit: chore(release): prepare 0.1.0a4
```

The release commit changes `0.1.0a4.dev0` to `0.1.0a4` in Carnopy source,
the synchronized companion-bridge metadata and qualification constant,
`uv.lock`, release/tooling assertions, and version-specific documentation.
Then run the complete source, package, Twine, and distribution gates; require
green CI on the release pull request; merge through protected `main`; create
one annotated `v0.1.0a4` tag; push only that tag; approve the protected PyPI
deployment; verify PyPI; and create the matching GitHub prerelease.

Tags, publication, environment approval, repository settings, and visibility
remain human-only. Do not pull Stage 4 through 8 work into this release. Native
VTK is not part of the `0.1.0a4` gate.

The release-facing README must use an honest shipped screenshot, lead with the
real scientific and desktop value, present isolated desktop through `uv tool`
and base CLI/library through `pip` as the two primary installation paths, and
place `app`, `viz`, `ml`, `analysis`, and `all` in one compact reference table.

### Stage 3 stop conditions and assumptions

Stop and ask the maintainer if evidence shows that:

- a worker-protocol or public-schema change is required;
- current p–v/T–s behavior contradicts the emitted-state contract;
- current persisted job/report/sidecar evidence cannot support configured
  result verification;
- a QML controller requires a heavy scientific, table, or rendering import;
- a lifecycle operation can bypass composition guards;
- sidecar export cannot preserve correct provenance safely;
- Widgets deletion would remove behavior without an equivalent tested QML path.

Assumptions:

- Qt remains pinned to 6.11.1.
- CoolProp remains the only backend and its recorded DEF reference-state policy
  remains unchanged and non-user-selectable.
- No dependency or `uv.lock` change is expected during Stage 3.
- No database, web service, new plot kind, 3D, sweep execution, preparation
  execution, or standalone installer is included.
- The existing Graphify graph describes the merged Stage 2 baseline but is
  hard-stale under the tracked six-commit cutoff. Do not query it during the
  remaining Stage 3 implementation; current source and tests are authoritative.
- Git staging, commits, pushes, merges, tags, and publication remain
  human-owned.

Before each implementation Step, recommend a parent model and reasoning effort
from the approved local ladder. The maintainer selects it; the agent does not
claim to change a selected level. Recommended defaults are:

- Steps 1 and 13: GPT-5.6 Sol High;
- routine QML page Steps: GPT-5.6 Sol High;
- execution, inspection, persistence, provenance, lifecycle, launcher
  migration, and Widgets deletion: GPT-5.6 Sol XHigh;
- GPT-5.6 Sol Max only for a genuine scientific, filesystem-integrity, or
  cross-platform contradiction.

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

## Stage 8: Native 3D packaging and later-release qualification

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

This is the release gate for the later native-3D-capable alpha line, not for
`0.1.0a4`. Assign its version only when the preceding stages and packaging
decisions are ready for review.

## Completion gate

Before merging each stage pull request:

- run the focused and complete gates relevant to that stage;
- complete any stage-specific native/manual acceptance recorded above;
- resolve concrete high- and medium-severity findings;
- update this plan only after explicit maintainer acceptance.

Before final GUI-2 completion:

- run focused checks after every stage;
- run the complete repository quality gate;
- inspect source, wheel, sdist, QML, and native-resource inventories;
- run installed base, app, analysis, 3D, and applicable `all` smoke profiles;
- run the three-platform QML checks and Linux native checks;
- manually exercise WSLg XCB and Wayland startup;
- manually exercise dataset, sweep, preparation, inspection, table, plot, job,
  recovery, and exact 3D workflows;
- use an explicitly configured allowed reviewer for an independent final audit;
- update permanent documentation and Graphify from the final architecture;
- delete this temporary plan only after those steps pass.

Manim, PyMC, SINDy, optimization, ORC and TFC workflows, mixtures, training
infrastructure, deployment, additional backends, and standalone installers are
deferred to separately reviewed milestones.
