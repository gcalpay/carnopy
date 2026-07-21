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
not require another native VTK qualification run. Stage 1 is complete and
Stage 2 is active.

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
| 2 | Active | Add the modern QML workspace and dataset workflow |
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

## Stage 2: Modern QML dataset application

Stage 2 delivers the first packaged, clickable QML application over the Stage 1
controllers. The public `carnopy-app` and `carnopy-gui` launchers remain on
Widgets until Stage 3 parity. Stage 2 does not add generation, inspection,
table preview, rendering, native VTK, sweep, preparation, jobs, or recovery
workflows.

### Approved visual and interaction direction

- Optimize for a dense desktop scientific workbench, with 1440 by 900 logical
  pixels as the primary design viewport. Keep the window freely resizable and
  maximizable; 1440 by 900 is not a maximum resolution.
- Use a persistent collapsible left rail, a slim document command bar, a
  responsive card grid, and an adaptive right inspector. The inspector shows
  page-specific issues and help above stable document validity, file state, and
  next actions.
- Use a native operating-system title bar. Follow the operating-system theme on
  first launch and persist explicit System, Light, and Dark choices.
- Use moderately expressive functional motion with a reduced-motion setting.
  Motion must remain fast, interruptible, and never delay an available control.
- Use a navy navigation surface, restrained emerald primary actions, and blue
  informational accents. Status must never rely on color alone.
- Keep the full navigation structure visible. Unavailable entries are muted,
  explained, non-interactive, and excluded from keyboard focus. Use this order:
  Workspace, Dataset, Visualization, YAML Preview, Run, Inspect, Activity and
  Recovery, Model Sweeps, ML Preparation, and 3D. Anchor Settings and Help at
  the bottom.
- Reserve the future 3D workflow in the visual composition and record a future
  fullscreen/restore control with Escape to exit. Do not show a fake viewport,
  fake scientific data, smoothing controls, scene preparation, or VTK behavior
  before Stages 6 and 7.
- The controlled design gate selected **Precision Grid** as the primary visual
  treatment from three original wide-desktop Dataset treatments with identical
  information architecture, content, validation state, viewport, and functional
  scope. The dense workbench is the locked primary layout, and the numbered
  next-steps progression is the only pre-approved element borrowed from the
  spacious-dashboard concept. No other elements are borrowed and no undefined
  blend is permitted. Refine Precision Grid for workspace landing, System,
  Light, and Dark themes, 1024 by 768, 1920 by
  1080, narrow layout, collapsed rail, and inspector drawer states. Store
  working references only in ignored `prerelease/gui2-stage2-design/`; do not
  package or commit them. The clickable QML shell becomes authoritative
  immediately after visual approval.
- Use the maintainer-provided untracked
  `logo-ideas/minimal-green-v1.png` unchanged as the explicitly approved
  provisional Stage 2 application mark. Copy the exact PNG bytes into the
  installed branding resources, record their SHA-256, and keep `logo-ideas/`
  ignored. The generated vector candidates are rejected and must not be
  packaged or used as a tracing source. Final logo refinement is intentionally
  deferred and may replace the provisional resource through a separately
  reviewed change. Bundle IBM
  Plex Sans Regular, Medium, and SemiBold for the interface and IBM Plex Mono
  Regular and Medium for YAML, paths, hashes, logs, and aligned technical
  values. Bundle only the audited Lucide SVG subset actually used. Record exact
  upstream revisions, licenses, packaged paths, filenames, and SHA-256 hashes in
  a machine-readable third-party resource manifest.

Responsive shell breakpoints use logical pixels: wide at 1280 and above,
compact from 800 through 1279, and narrow below 800. Actual card columns derive
from the remaining central-content width after rail and inspector allocation,
using a 300-logical-pixel minimum card width and at most three columns. Follow
operating-system DPI scaling, preserve normal geometry and maximized state,
clamp restored geometry to available screens, and keep wide-layout preferences
separate from transient responsive overrides. Do not add a resolution selector,
window-size presets, or application-specific zoom. Verify 1024 by 768, 1440 by
900, 1920 by 1080, 2560 by 1440, 3840 by 2160, and a 768-logical-pixel narrow
window at relevant 100, 150, and 200 percent scaling.

### Qt, QML, and packaging baseline

- Raise the application dependency to
  `PySide6-Essentials>=6.11.1,<6.12` in both `app` and `all`; update the lock,
  dependency metadata tests, CI, installed-package tests, and documented
  platform baseline. Keep the companion native bridge on its exact qualified
  6.11.1 pin.
- Keep Carnopy's own Basic Controls design system responsible for appearance.
  Qt 6.11 provides the runtime and tooling but is not itself the visual design.
- Start the internal QML application in this order: create the Qt GUI
  application; set organization and application names; select Basic Controls;
  create settings and controllers; register and verify fonts; configure
  installed QML import paths; connect engine warning capture; then load the
  root object.
- Treat QML load failures, missing mandatory fonts or resources, any QML warning
  during initial loading, and zero root objects as startup failure. Capture and
  surface later runtime warnings without unconditionally crashing the
  application. Carnopy-owned startup warnings fail supported-environment tests,
  and supported automated interaction tests must remain warning-free.
- Package QML, fonts, icons, branding, licenses, and provenance through
  installed-package resources. Tests must compare installed third-party bytes
  against the resource manifest.
- Add a non-writing QML formatting and lint gate using the selected PySide6 6.11
  tools. Extend the dedicated app CI job, add focused Linux, Windows, and macOS
  QML startup coverage, and extend installed wheel smoke tests without removing
  the existing Widgets smoke.
- Preserve `--qt-platform auto|xcb|wayland`. Exercise QML through a private
  module or test entrypoint; do not add a public frontend selector or switch the
  public launchers during this stage.

The machine-readable third-party manifest must include a schema version and,
for each upstream project, its exact tag or commit, source URL, SPDX license
identifier, packaged license path, every vendored filename, and the SHA-256 of
every vendored file. Source, wheel, sdist, and installed-runtime tests must
agree with that manifest.

Update the existing repository surfaces deliberately rather than relying on
implicit package-data behavior: `.github/workflows/ci.yml`,
`.github/workflows/publish.yml`, `scripts/check_distribution.py`,
`scripts/smoke_installed.py`, `tests/test_workflows.py`, the release-tool and
packaging-metadata tests, and the wheel/sdist inventories. The existing Linux
app job continues to own strict app typing and all Widgets regressions and also
runs the QML formatting, lint, engine, interaction, and GUI-process isolation
checks. Add a focused QML matrix on `ubuntu-latest`, `windows-latest`, and
`macos-latest` for font/resource loading, warning-free root creation, responsive
shell state, one controller interaction, and clean teardown under the pinned Qt
line. Installed app and `all` wheel smokes must exercise both the unchanged
public Widgets launcher and the private QML entrypoint.

Stage 2 cross-platform coverage is an early source and installed-resource smoke
gate for this bounded workflow. It does not replace Stage 8's complete release
qualification across installed distributions, all supported Python and
operating-system combinations, optional capabilities, native resources,
security, and publication rehearsal.

### Controller ownership and private interfaces

- Reuse exactly one `DesktopController`, `WorkerClient`,
  `DesktopRequestCoordinator`, `WorkspaceController`,
  `DatasetConfigController`, `DatasetDraft`, and `VisualizationDraft`. Connect
  workspace activation to configuration context once in the composition layer
  and remove the duplicate Widgets-side connection without changing Widgets
  behavior.
- Bind QML delegates directly to the existing Qt model roles and mutation
  slots. Do not copy authoritative choices, selections, samplers, mappings, or
  plots into JavaScript arrays and do not create a second configuration store.
- Add a private settings controller over the same `QSettings` instance for
  `themeMode`, `effectiveTheme`, `reducedMotion`, `railCollapsed`,
  `inspectorCollapsed`, window geometry/maximized state, and layout reset.
  System-theme changes update the running application. Responsive overrides
  never overwrite stored wide-layout preferences.
- Expose private QML-readable busy and active-owner state and an invokable,
  guarded desktop shutdown path. Keep request ownership and one-active-request
  behavior in the existing coordinator.
- Extend `SamplerDraft`, `DatasetDraft`, and `PlotDraft` with stable structured
  first-invalid-field projections. Extend `DatasetConfigController` with typed
  `yamlAvailable`, `blockingSection`, `blockingField`, `blockingRow`, and
  `blockingIssue` properties. Rows use `-1` when no row applies. Add narrow typed
  `operationFailed`, `saveSucceeded`, `importSucceeded`, and
  `attentionRequested` signals while retaining the current status and warning
  adapters for Widgets. No controller or QML code may infer a field by parsing
  English issue text.
- Keep GUI additions private to `carnopy.app`. Do not change the public CLI,
  Python API, YAML structure, normalized-configuration schema, worker protocol,
  or scientific identity definitions. The definition-first sampler correction
  below may change normalized bytes for representations that were not previously
  unit-invariant; it must make equivalent canonical sampler keys identical. The
  only approved additive public configuration change is the Commit 8 sampler
  unit and starter-template extension recorded below.

### Workspace and document workflow

- Implement unavailable, loading, workspace landing, and document editing
  states. Normal startup shows the in-shell landing and recent workspaces; only
  explicit `--workspace` opens immediately.
- Create Workspace chooses an existing parent and a new single-component child
  name, or accepts a complete non-existing expert path. Initialize Existing and
  Open use existing-directory selection. Do not broaden Create to accept an
  existing empty directory.
- Require explicit confirmation for every Initialize Existing operation,
  including empty directories. Preserve the trusted two-phase preflight and
  commit, inode identity, marker, same-workspace, busy, dirty, and no-overwrite
  behavior.
- With a workspace but no document, show only the three New Dataset mode cards
  and Import Existing Configuration. With a real document, activate Dataset,
  Visualization, YAML Preview, Save, Save As, and Close Configuration.
- Put workspace/configuration breadcrumbs and document actions in the command
  bar; keep page-specific actions inside their page.
- Present the Dataset editor as a stable responsive card grid for model, mode
  and coordinate, fluids, samplers and units, properties, output formats, and
  reference-state/document summary. Bind directly to the existing model roles;
  display `display` and pass `value` to mutation slots.
- Present Visualization as inline master-detail editing over the authoritative
  shared settings, ordered plot snapshots, and one temporary `PlotDraft`. Do
  not render a preview in Stage 2.
- Present YAML as a read-only authoritative projection with line numbers,
  search, copy, file/dirty state, and typed navigation to a blocking Dataset or
  Visualization field. When invalid, expose `yamlAvailable=false`, an empty
  preview, and typed blocking section, field, and issue values. Never show stale
  or best-effort YAML as current.
- Keep live local checks visibly distinct from worker authority. Save and Save
  As perform exact-YAML worker validation before any write. Preserve imported
  reformat confirmation, external-change detection, atomic verified replacement,
  Save As no-overwrite, in-flight-change rejection, and baseline refresh only
  after successful writing. Do not add autosave or a recovery snapshot format.

### Scientific numeric and unit-entry contract

- Preserve `K` and `degC`. Preserve `Pa`, `kPa`, `MPa`, and `bar` and add the
  public pressure tokens `hPa` and `atm`. QML and Widgets display human-readable
  symbols while YAML retains these stable tokens. Use the exact scale factors
  `1 hPa = 100 Pa` and `1 atm = 101325 Pa`; both pass through the same fixed
  Decimal boundary and exact canonical-key rules as every existing unit. Do not
  add Fahrenheit or psi: their affine or nonterminating representations add
  avoidable unit-toggle and presentation complexity to the current scope.
- Use practical starter grids without changing sampler syntax: HEOS, Propane and
  Isobutane, and CSV plus Parquet remain the defaults for all dataset modes;
  property tables use temperature linspace from -50 through 50 degC with 101
  points and pressure linspace from 101325 through 506625 Pa with 41 points,
  exactly 1 through 5 atm in 0.1-atm increments; saturation tables use the same
  101-point temperature coordinate; vapor-mass-fraction tables use that
  temperature coordinate plus stepspace from 0 through 1 with step 0.1.
  Coordinate replacement uses one ambient fallback point of 293.15 K for
  temperature or 101325 Pa for pressure. These are starter declarations, not
  claims of universal ML adequacy or guaranteed valid saturation states.

- Production sampling and GUI unit conversion share one lightweight,
  deterministic binary64 sampler canonicalizer. It supports every valid public
  sampler, uses the existing `.15g` stabilization and positive-zero
  normalization, and has no tolerance or configurable precision mode. Do not add
  float32 sampling.
- For every finite numeric operand, including unit scales, offsets, and logspace
  bases, first convert to binary64 and stabilize it through `.15g`. Construct
  private `Decimal` operands from that stabilized decimal text, never directly
  from the binary float; calculate with a fixed
  `Context(prec=50, rounding=ROUND_HALF_EVEN)`; then convert the result back to
  binary64 through the same `.15g` stabilization. Never serialize or retain
  Decimal state as a second numeric authority.
- A canonical sampler key is an immutable exact representation containing the
  axis, sampler kind, canonical SI definition fields, integer count fields, and
  stabilized numeric text. Production normalization canonicalizes each sampler
  definition to SI, materializes that canonical sampler exactly once, and
  stabilizes the resulting SI grid. It preserves the selected unit and declared
  sampler values under `original_grid`; YAML and metadata continue to retain the
  user's declaration.
- Equal canonical sampler keys must produce exactly identical worker-normalized
  SI grids, normalized executable bytes, normalized hashes, and `spec_id`.
  Permanent production tests prove those consequences. The GUI process may use
  only the lightweight canonicalizer and exact key comparison; it must not import
  NumPy, materialize grids, calculate normalized bytes or hashes, or calculate
  `spec_id`.
- Add one atomic `requestUnitChange(targetUnit)` operation shared by QML and
  Widgets. Parse and validate every required field and the target unit before
  mutation, derive a complete candidate from the private anchor, and commit the
  unit and all converted fields together only when
  `candidate_key == anchor_key`.
- Permit compatible conversion as follows: explicit converts every value;
  linspace converts start and stop; stepspace converts start and stop but scales
  step without an offset; geomspace permits only scale-only conversions;
  logspace permits only scale-only conversions representable by an exponent
  shift. Refuse affine geomspace and logspace conversions. Preserve the public
  logspace requirement that base is finite and greater than one. Calculate the
  exponent shift from the old/new scale ratio and base in the fixed Decimal
  context.
- If the target unit cannot express an exact `.15g` representation whose
  canonical key equals the anchor, reject the toggle atomically, preserve the
  current unit and every raw field, and emit a structured failing field and
  message. This does not make the original sampler invalid, alter dirty state,
  or narrow public sampler support; only this unit-only representation change is
  unavailable.
- Loading, importing, new-document creation, sampler-kind replacement, and reset
  establish a private anchor only when the resulting sampler is valid. Invalid
  or incomplete edits retain the last valid anchor but make a toggle fail
  without overwriting those edits. A successful toggle derives from but does not
  replace the anchor. The next complete valid non-unit edit establishes a new
  anchor in the displayed unit. Removing the sampler or closing the document
  clears it. The anchor is private, non-serialized, excluded from dirty state,
  and never configuration authority.
- Tests cover successful exact toggles and expected exact-representation
  rejections, repeated changes, `.15g` boundaries, stepspace reachability,
  negative zero, large and small magnitudes, invalid partial input, affine
  refusals, and logspace bases greater than one. Existing stepspace reachability
  tolerances remain public materialization behavior and are not used as a unit
  equivalence comparator.

Implementation stops only if canonicalization is nondeterministic, equal keys
produce different production grids/bytes/hashes/`spec_id`, an accepted toggle
changes canonical identity, or a rejected toggle mutates state. A compatible
target that cannot exactly represent one sampler is an expected rejection, not
a stop condition.

### Authoritative active-edit and feedback behavior

- Add an authoritative `hasActivePlotEdit` projection. QML may call child drafts
  and models directly only for local field editing; workspace, document
  replacement, Save, mode/coordinate replacement, and shutdown operations must
  use invokable composition-level facade slots owned by `DesktopController`.
  Destructive child-controller methods must not remain directly invokable from
  QML.
- Run the active-edit guard before workspace preflight and again before workspace
  commit, and before Save, Save As, New, Import, Close Configuration, mode or
  coordinate replacement, document or workspace replacement, and shutdown.
  Block visualization enable/disable, shared format, fluids, filters, display
  units, plot removal, and plot movement while the temporary editor is active.
- Keep cross-controller guard ownership in the desktop composition layer rather
  than making `WorkspaceController` depend on visualization state. Rejected
  operations make no durable change and emit a typed request to navigate to and
  focus the active editor. The temporary plot draft is unresolved transient
  state, not durable configuration dirty state, and requires explicit Commit or
  Cancel.
- Use stable field identifiers instead of English issue parsing:
  `dataset.model`, `dataset.mode`, `dataset.fluids`,
  `dataset.grid.<axis>.<field>`, `dataset.properties`,
  `dataset.outputs.dataset_formats`, `visualization.enabled`,
  `visualization.format`, `visualization.fluids`, `visualization.filters`,
  `visualization.display_units`, `visualization.plots`, `plot.<field>`,
  `plot.filters`, and `plot.display_units`. Report an ordered model row
  separately rather than embedding it in a message or field identifier.
- Add narrow typed operation signals for failures, successful Save, successful
  Import, and attention requests while retaining the existing Widgets adapters.
  Do not add a generic event bus.
- Use layered feedback: inline issues, inspector aggregation, persistent
  blocking banners, brief success toasts, and modal dialogs only for
  consequential decisions. Settings provides theme, reduced motion, and layout
  reset; Help explains shortcuts, workflow, local versus worker validation,
  scientific isolation, and verified platform status.

### Stage 2 delivery and acceptance

Use this exact commit sequence. Each implementation commit must be independently
reviewable and must pass its focused gate before the next begins.

After Commit 3 and before Commit 4, complete the ignored design-reference gate.
That gate selected Precision Grid, retained only the numbered next-steps
progression as a named borrowed element, selected moderately expressive motion,
and approved `minimal-green-v1.png` unchanged as a provisional packaged mark.
The generated vector candidates were rejected and final logo refinement was
deferred. This completed gate does not reopen the settled layout, scope, Qt,
packaging, workflow, or scientific decisions.

Current implementation status as of 2026-07-19:

- Commits 1 through 4 are implemented in the Stage 2 branch history. The design
  and branding gate required between Commits 3 and 4 is complete under the
  provisional-logo decision recorded above.
- The Commit 5 boundary is implemented and its focused verification passes. It
  provides the shared-QSettings appearance controller, Precision Grid design
  tokens, the responsive wide/compact/narrow shell, persistent wide-layout rail
  and inspector preferences, clamped window geometry, moderately expressive
  reduced-motion-aware transitions, the exact locked navigation names, disabled
  future-workflow affordances, Settings and Help pages, the used Lucide resource
  inventory, and focused QML/runtime/distribution regressions.
- The Commit 6 boundary is implemented and its focused and repository-wide
  verification passes. It adds the authoritative unavailable/loading/landing/
  editing workspace state, direct recent-workspace model binding, correct
  parent-plus-new-name and expert-path Create flows, existing-folder Initialize
  and Open flows, confirmation for every Initialize operation, and an in-shell
  workspace landing page. `DesktopController` now owns the QML/Widgets workspace
  facade, binds workspace activation to `DatasetConfigController` exactly once,
  and guards active plot edits both before preflight and again before commit.
  The child workspace and configuration-context mutation methods used by that
  facade are no longer QML-invokable slots. Widgets use the same facade without
  changing their active public workflow.
- Native interaction stabilization keeps platform dialogs and model-backed
  delegates out of direct QML-to-Python method calls. Workspace controls emit
  root-level QML request signals; `QmlApplicationRuntime` connects those signals
  to the composition facade with queued Qt connections. Recent-workspace model
  reordering is deferred until the activating delegate has unwound, and window
  close events pass through a runtime-owned composition guard before teardown.
  Create selects the parent folder before opening the QML name dialog, so it
  never nests the native chooser inside another modal surface. Initialize and
  Open likewise defer accepted-path dispatch until the native chooser reports
  hidden and the event loop advances. Folder dialogs
  declare the Carnopy window as their explicit transient parent.
- Workspace copy now distinguishes the two existing-directory operations:
  Initialize converts an explicitly confirmed ordinary directory into a Carnopy
  workspace by adding the marker and managed directories without deleting
  unrelated contents, while Open accepts only an already initialized Carnopy
  workspace. Neither operation selects a file. Exactly one inspector control is
  visible at a time: the command bar opens a closed inspector, while the visible
  inspector header closes it from the same stable right-edge region. The
  inspector header and close control stay outside its scrollable content so
  Flickable gesture recognition cannot delay or cancel the toggle. The
  inspector's Workspace card remains workspace-scoped when Settings or Help is
  selected. Settings describes the persisted rail and inspector states as
  immediate wide-layout preferences rather than startup-only choices.
- Verification at the current boundary includes the 17-file QML tooling check,
  full Ruff and mypy gates, the complete repository tests, `preflight.py`,
  environment compatibility checking, warning-free offscreen QML startup and
  deterministic QML/Dialog teardown, and the complete local source/build gate
  with successful wheel/sdist build, Twine checks, and distribution inventory
  verification. Focused real-window diagnostics also cover actual QML delegate
  clicks, capability-worker completion, and a ten-second parented native-folder-
  dialog soak without teardown. Native folder selection, cursor behavior, and
  monitor/compositor interaction still require the planned human acceptance;
  this does not claim native cross-platform acceptance or complete Stage 2.
- On the current WSLg development host, the Wayland integration can leave native
  folder dialogs detached after selection, while Mesa's automatic Zink/EGL probe
  can fail before falling back and produce a variable multi-second delay. The
  existing `auto|xcb|wayland` contract now selects XCB automatically only when
  WSLg and both display transports are detected and no explicit
  `QT_QPA_PLATFORM` override exists. Explicit Wayland remains available for
  qualification, and native Linux selection is unchanged. XCB resolves both
  observed dialog failures on this host without forcing software rendering
  globally. Scene-graph diagnostics show that this host's XCB OpenGL path uses
  Mesa llvmpipe, so remaining native 2D responsiveness must be assessed
  separately from controller latency. Qt's dedicated 2D software scene graph is
  available as a diagnostic alternative but is not selected automatically
  because Stage 7 must still qualify the final native-3D rendering path.
- Window restoration applies persisted client geometry once rather than keeping
  live QML bindings from the window back to its own persistence model. The
  runtime assigns and fits the still-hidden native window to the selected
  screen before showing or maximizing it, so a restored launch does not expose
  a compositor-visible cross-screen remap. A windowed launch receives one final
  decorated-frame fit inside that screen's logical available geometry.
  Subsequent debounced native moves and resizes update persistence without
  feeding the stored rectangle back into the running window, preventing
  decoration-offset drift and initial placement below a smaller screen's work
  area. Normal close also stores the monitor identity under the QML settings
  namespace. The next launch prefers that monitor, falls back to geometry
  intersection when it is unavailable, and does not enable geometry
  persistence until one-time restoration completes. Placement state written by
  the retired restoration path is discarded by a one-time versioned migration,
  while theme, layout, and recent-workspace settings are retained. The private
  QML launcher holds a per-user runtime lock and rejects a concurrent second
  instance instead of allowing two CPU-rendered shells to overlap and race on
  the same settings.
- The root QML palette binds every Basic Control text role to the selected
  Carnopy theme, including Switch and CheckBox labels. A workspace action
  rejected only because the capability worker is active clears that transient
  message when the worker becomes idle; persistent operation errors remain
  visible.
- The Commit 7 boundary is implemented and its focused and repository-wide
  automated verification passes. The three workspace mode cards now create real
  template-backed documents, worker-authoritative Import opens validated
  configurations, Dataset navigation activates only for an open document, and
  the responsive Dataset page binds directly to the authoritative model, mode,
  coordinate, fluid, sampler, property, and output-format models. It exposes
  structured first-invalid fields and rows without parsing English issue text.
- `SamplerDraft.requestUnitChange()` is the only Widgets/QML unit-change path.
  It keeps a private valid-definition anchor, derives every candidate through
  fixed-context Decimal operations over `.15g`-stabilized binary64 text, and
  commits only when the candidate's exact canonical key equals the anchor key.
  Affine geomspace/logspace changes and target representations that cannot
  reproduce the exact key are rejected atomically without changing raw state,
  validity, or dirty state. The GUI path remains lightweight and does not import
  NumPy or materialize production grids, bytes, hashes, or `spec_id`.
- Dataset mode and coordinate replacement are provisional composition-owned
  decisions. QML emits root requests connected by the runtime to
  `DesktopController`; the public Widgets composition uses the same facade and
  confirmation boundary. The destructive draft methods are not QML-invokable.
  Cancelled decisions restore the authoritative selection, while accepted mode
  changes retain shared Dataset state and clear configured visualization as
  already defined by Stage 1. A newly introduced temperature or pressure
  coordinate starts from one ambient point of 293.15 K or 101325 Pa rather than
  the previous unit value of one.
- All QML Dataset mutations cross a queued Qt connection before changing the
  authoritative Python drafts. This includes model, fluid, property, output,
  sampler-kind, sampler-unit, and raw sampler-text edits. Native interaction
  regressions exercise the real Add buttons and sampler signals; they prevent
  re-entrant QML model/view updates from becoming process-level crashes while
  preserving direct draft ownership and the unchanged Widgets workflow.
- Dataset model choices retain the schema values `heos`, `pr`, and `srk` while
  presenting Helmholtz Equation of State (HEOS), Peng-Robinson (PR), and
  Soave-Redlich-Kwong (SRK). Selected fluid/property rows expose named Up,
  Down, and Remove actions. Workspace initialization errors direct an already
  initialized folder to Open Workspace; initialization remains the one-time
  creation of the private marker and managed workspace directories.
- Reusable Dataset selectors preserve readable foreground/background contrast
  for highlighted and hovered rows. Page and inspector Flickables use vertical,
  pixel-aligned scrolling with attached scrollbars, short nested selected-value
  lists do not capture wheel input, and rail collapse avoids an animated
  full-workbench relayout. The Reduce Motion preference controls subsequent
  micro-transitions and notification fades and reports its active behavior; it
  does not alter direct scrolling speed.
- Capability diagnostics on the current WSLg host identified two independent
  latency sources. HEOS fluid discovery no longer instantiates every compiled
  CoolProp fluid merely to reproduce the compiled HEOS registry; selected-fluid
  validation and PR/SRK support filtering remain authoritative. A fresh HEOS
  capability request fell from approximately 17.6 to 3.5 seconds on this host.
  Native scene-graph diagnostics still report OpenGL through Mesa llvmpipe, so
  the remaining 2D rendering and scroll cost is a CPU-only host graphics
  limitation, not a database or controller-ownership issue. The dedicated Qt
  software scene graph remains an explicit diagnostic alternative and is not
  forced globally ahead of native-3D qualification.
- Capability metadata and both frontends identify the fixed generation policy
  as CoolProp DEF. It remains non-user-selectable: Carnopy resets each requested
  fluid to DEF before row evaluation, does not change reference state during
  generation, and warns that absolute enthalpy, entropy, and internal energy
  require a compatible recorded backend, model, version, and reference-state
  context. A future backend cannot silently reuse this label without providing
  its own explicit policy metadata.
- Commit 7 verification includes the 22-file non-writing QML format/lint gate,
  warning-free engine and interaction tests, exact success and rejection
  families for every sampler kind, anchor lifecycle and structured-field
  regressions, unchanged Widgets bindings, full Ruff and mypy gates, 673 passing
  repository tests, `preflight.py`, and environment compatibility checking.
  Native human inspection of the Dataset page and both successful and rejected
  unit toggles remains required before the maintainer accepts this commit.
- The separately approved Commit 8 boundary is implemented in the Stage 2
  branch history.
  Public input units now additionally accept `hPa` and `atm` through the same
  exact sampler canonicalization boundary. Packaged starters
  and byte-identical repository examples use HEOS, Propane and Isobutane, CSV
  and Parquet, the approved 101-by-41 property grid whose pressure axis is
  101325 through 506625 Pa (exactly 1 through 5 atm), 101-point saturation
  coordinate, and 101-by-11 vapor-fraction grid.
- Commit 8 verification includes exact new-unit canonical-key and production
  identity regressions, worker/QML capability projection, starter-template and
  safe-toggle tests, all static gates, and 686 passing repository tests,
  `preflight.py`, and environment compatibility checking. Authoritative CLI
  validation projected 8,282 property rows, 404 saturation rows, and 2,222
  vapor-fraction rows. Non-repository rehearsal generation completed all three
  starters with zero invalid rows; the final atmospheric property starter was
  regenerated separately with all 8,282 rows valid.
- The Commit 9 boundary is implemented in the Stage 2 branch history. The QML
  Visualization page binds the authoritative shared format, fluid, filter,
  display-unit, and ordered durable plot models, and presents the single
  workflow-local Add/Edit `PlotDraft` as an inline master-detail editor. It
  preserves disabled latent state, per-plot inheritance, raw shared/per-plot
  mapping separation, ordered snapshot ownership, and worker-only rendering.
- Stable `visualization.*` and `plot.*` field identifiers plus a separate row
  projection drive invalid-field focus without parsing English issue text.
  Invalid Commit retains the temporary editor and focuses its first structured
  issue; Cancel destroys only transient state and does not alter durable dirty
  state.
- `DesktopController` is the QML-invokable lifecycle facade for workspace
  replacement, document replacement, Save, mode or coordinate replacement, and
  shutdown. The active-plot guard runs before workspace preflight and commit,
  and before every guarded configuration operation. Shared visualization
  changes, durable plot removal or movement, and starting another editor are
  locked at both the facade and draft boundaries while one edit is active.
  Widgets retain their modal editor and use the same composition-owned
  lifecycle boundary.
- Commit 9 verification includes the 25-file non-writing QML
  format/lint gate, warning-free QML Add/invalid Commit/valid Commit/Cancel
  interaction tests, structured validation and mapping-row regressions,
  composition lifecycle tests, unchanged manual-plot and Widgets regressions,
  full Ruff and mypy gates, 694 passing repository tests, `preflight.py`, and
  environment compatibility checking. Native human inspection of the
  Visualization page remains required before the maintainer accepts this
  commit.
- The Commit 10 boundary is implemented in the working tree. The configuration
  controller now exposes typed YAML availability and blocking section, field,
  row, and issue projections. Invalid state clears `yamlPreview` instead of
  retaining stale or best-effort YAML. Typed operation-failure, Save-success,
  Import-success, and attention signals coexist with the unchanged Widgets
  adapters.
- The QML YAML Preview page is an authoritative read-only projection with line
  numbers, case-insensitive search, selection and copy, file and dirty-state
  context, an explicit unavailable state, and navigation through stable typed
  section/field/row identifiers. The command bar exposes New, Import, Save,
  Save As, and Close through root requests connected to the composition facade.
  Reformat, external-change, dirty-replacement, and dirty-shutdown choices are
  explicit consequential dialogs; QML does not duplicate the document or Save
  workflow.
- Save and Save As still submit the exact complete-document YAML to the worker
  before writing and retain imported-reformat consent, external-change
  protection, atomic verified replacement, Save As no-overwrite, in-flight
  mutation detection, and baseline refresh only after success. Window close is
  now guarded by the same composition-owned active-edit, busy, and dirty-state
  decisions as other replacement operations.
- Commit 10 focused verification includes the 29-file non-writing QML gate,
  warning-free QML YAML/search/blocker/decision interactions, controller and
  unchanged Widgets regressions, source and installed-resource inventory tests,
  workflow-policy tests, the full 705-test repository suite, `preflight.py`,
  environment compatibility checking, an outside-checkout installed-wheel QML
  smoke, and the complete local source/build/Twine/distribution-inventory gate.
  The CI and release workflows include a Python 3.12 installed-wheel QML smoke
  on Linux, Windows, and macOS covering warning-free startup, responsive state,
  YAML-page creation, one settings-controller interaction, and teardown. Those
  remote jobs remain to be observed after the human commit and push. Native
  dialogs remain outside headless CI, and this smoke is not Stage 8 platform
  qualification.
- Commit 11 has not started. No generation, inspection, plotting, VTK, or
  public-launcher parity is inferred from Commit 10. Both public launchers
  remain on Widgets, and Stage 2 remains active until the complete automated
  gates, three-platform PR checks, native manual acceptance, and explicit
  maintainer approval are complete.
- Git staging, commits, synchronization with the remote branch, and publication
  remain human-owned and are not implied by this implementation-status record.

1. `docs(app): lock GUI-2 Stage 2 contracts`
   - Record the approved design, scientific, lifecycle, Qt, delivery, and
     acceptance contracts in this plan.
   - Do not stage generated design references.
2. `fix(sampler): canonicalize SI definitions before sampling`
   - Add the lightweight exact sampler canonicalizer and fixed Decimal boundary,
     make `carnopy.sampling` importable without NumPy, canonicalize sampler
     definitions before production materialization, retain the declared
     `original_grid`, and prove exact grid/bytes/hash/`spec_id` consequences.
   - Do not add GUI unit-toggle behavior in this commit.
3. `build(app): require Qt 6.11 for QML`
   - Raise the `app` and `all` dependency bounds, update the lock, dependency
     metadata assertions, and platform-baseline documentation.
   - Preserve the native bridge's exact qualified 6.11.1 pin.
4. `feat(app): add packaged QML runtime resources`
   - Add the private launcher, application identity and startup ordering,
     warning capture, minimal installed QML module, approved branding, IBM Plex,
     the used Lucide subset, licenses, provenance manifest, non-writing QML
     tooling checks, and resource/package inventories.
   - Keep both public launchers on Widgets.
5. `feat(app): add responsive QML workbench shell`
   - Add the settings controller, design tokens, responsive shell, navigation,
     inspector, command bar, reusable components, Settings, Help, logical-pixel
     breakpoints, geometry clamping, and focused shell tests.
6. `feat(app): bind QML workspace lifecycle`
   - Add unavailable, loading, landing, and editing states; correct
     Create/Initialize/Open flows; recents; two-phase confirmation;
     composition-root workspace binding; the guarded workspace facade; and
     focused regressions.
7. `feat(app): add QML dataset workflow and safe unit changes`
   - Add the Dataset card grid, direct model bindings, local issue projection,
     guarded mode/coordinate decisions, the anchor-based exact-key unit-change
     operation, ambient coordinate-replacement fallbacks, the matching Widgets
     adaptation, and exact canonical-identity tests.
8. `feat(sampler): add practical grids and engineering units`
   - Add `hPa` and `atm` as public input-unit tokens through the existing exact
     canonicalization boundary; update all public unit catalogs, capabilities,
     documentation, and normalization regressions; replace the three packaged
     starter grids with the approved practical ranges; keep repository examples
     byte-identical to their packaged templates. Explicitly leave Fahrenheit
     and psi unsupported.
   - Do not add alternate range syntax, float32 sampling, tolerance, implicit
     saturation behavior, visualization display units, or another numeric
     authority.
9. `feat(app): add guarded QML visualization editing`
   - Add inline master-detail plot editing, stable invalid-field focus,
     authoritative model locks, and the composition-owned cross-controller
     lifecycle guard.
10. `feat(app): add QML YAML and validated save flows`
   - Add typed YAML availability, search/copy and blocking-field navigation,
     typed operation feedback, worker-validated Save and Save As, reformat,
     external-change, dirty-close, QML integration tests, three-platform smoke,
     and installed-wheel verification.
11. `docs(app): complete GUI-2 Stage 2`
   - Create this documentation-only status commit only after explicit
     maintainer acceptance of the automated and native results.
   - Record the exact verified platforms and gates, mark Stage 2 complete, and
     make Stage 3 active without claiming Stage 3 parity.

Focused automated coverage must include:

- deterministic canonicalization for every valid supported sampler; exact
  canonical-key equality; identical normalized SI grids, executable bytes,
  hashes, and `spec_id` for equal keys; every permitted and refused unit
  transformation; successful exact toggles and exact-representation rejections;
  repeated toggles, invalid partial text, nonfinite values, negative zero,
  `.15g` boundaries, very small and large magnitudes, stepspace reachability,
  and logspace bases greater than one;
- warning-free QML startup, font and resource registration, heavy/scientific
  import isolation, direct model-role binding, dropdown identifier correctness,
  responsive shell modes, DPI and restored-geometry behavior, theme and motion
  settings, keyboard focus, accessible labels, and non-color-only state;
- workspace Create/Initialize/Open contracts, confirmation for every
  initialization, same-workspace and busy behavior, every active-plot-edit
  lifecycle rejection, stable invalid-field focus, empty invalid YAML, exact
  worker-validated writes, external-change and reformat decisions, baseline
  refresh, and unchanged Widgets behavior;
- exact QML/font/icon/license/provenance inventories and source, wheel, sdist,
  and installed-byte agreement.

The Stage 2 automated gate is:

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

Do not mark Stage 2 complete before explicit maintainer acceptance. Before the
status commit, run the complete repository and distribution gates, pass the
three-platform QML checks and installed-resource smokes, keep both Widgets
launchers working, and manually exercise the native application through
workspace, New/Import, Dataset, safe and refused unit changes, Visualization,
YAML, validated Save, dirty/external-change decisions, themes, keyboard access,
and responsive/DPI states. Record exact verified platform behavior only.

Graphify refresh is not a Stage 2 completion requirement. Refresh public graph
artifacts only through a separately intentional architecture-documentation
step, and never remove a valid public graph before its replacement is complete
and verified.

## Stage 3: GUI-1 parity and Widgets retirement

Extract and migrate the remaining existing desktop workflows incrementally:

- validation and generation with progress and cancellation;
- source discovery and dataset, sweep, preparation, CSV, and Parquet inspection;
- bounded table preview;
- session plot editing, worker rendering, PNG and SVG preview, and explicit PDF
  opening;
- job history and guarded staging recovery.

Preserve the existing plotting dependency and process boundary during that
migration. The `app` extra already includes Matplotlib, rendering stays in the
short-lived worker, and the QML process must not import it. Installed `app` and
`all` smokes must continue rendering a real image and sidecar, while base-wheel
and sdist smokes must continue verifying the actionable missing-`viz` failure.
For a multi-fluid source, manual plot requests select an inspected emitted fluid
identity explicitly. QML may present the corresponding requested alias for
clarity, but it must not rename immutable emitted dataset values.

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
