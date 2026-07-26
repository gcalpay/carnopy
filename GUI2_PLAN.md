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
- `carnopy-gui` and `carnopy-app` will both launch one QML application in
  `0.1.0a4`.
- Widgets remain temporarily as a parity oracle, then are removed before the
  release. GUI-2 will not ship a frontend selector or two desktop applications.
- Stage 2 completion is not the `0.1.0a4` release boundary. Step 19 activates
  Stage 3 while both public launchers still use Widgets. `0.1.0a4` is planned
  after Stage 3 reaches tested GUI-1 capability parity, switches both public
  launchers to QML, removes the obsolete Widgets presentation, and passes the
  bounded alpha-release gate recorded below. It does not wait for Stages 4
  through 8. No calendar date is committed.
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
- Use a native operating-system title bar. New or migrated profiles without a
  valid stored choice start in Dark. Persist explicit System, Light, Warm, and
  Dark choices.
- Use moderately expressive functional motion with a reduced-motion setting.
  Motion must remain fast, interruptible, and never delay an available control.
- Use the approved Stage 2 Dataset reference as the visual authority. Its dark
  canvas is `#0F0F0F`; restrained emerald indicates selected, valid, confirmed,
  or calculated state, amber indicates unsaved or attention state, and red
  indicates error. Status must never rely on color alone.
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
  package or commit them. This restriction applies to exploratory working
  files; the later explicitly approved Dataset reference is committed as
  documentation. The clickable QML shell becomes authoritative immediately
  after visual approval.
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
gate for this bounded workflow. It does not by itself qualify `0.1.0a4`; the
bounded post-Stage-3 gate owns that decision. It also does not replace Stage
8's later native-3D qualification across installed distributions, applicable
Python and operating-system combinations, native resources, security, and
publication rehearsal.

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
  only approved additive public configuration change is the Step 8 sampler
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

### Approved scientific-workbench refinement

The [approved dark Dataset workbench reference](docs/assets/gui2-stage2-dataset-dark.png)
is authoritative for the remaining Stage 2 visual work. Its SHA-256 is
`d6b0ed719218be659ad5d2b940f1f11eab61802d641b4896dee9b96084ad8d48`.
It is a documentation reference, not a packaged runtime resource or application
data source. The following decisions supersede conflicting palette, appearance,
or completion wording earlier in this Stage 2 record without rewriting the
implemented history of Steps 1 through 10.

#### Palette, motion, and native window

- Reproduce the reference rather than interpreting it into another dark
  palette. Dark canvas is `#0F0F0F`. Define only the roles needed by the
  reference: canvas, surface, raised surface, divider, primary text, muted
  text, hover, focus/green, amber, and red. Light and Warm use the same minimal
  role set. Do not add gradients, glass, blur, decorative shadows, or another
  palette exploration.
- Green means selected, valid, confirmed, or calculated. Amber means unsaved or
  attention. Red means error. Hover is a soft full-target surface lift without
  movement.
- Local transitions last 120 through 160 ms. Drawers and toasts last 180
  through 220 ms. Reduce Motion makes them immediate. Widths never animate.
- The reference's window controls are illustrative. Carnopy retains the native
  operating-system title bar and its minimize, maximize, close, move, and
  resize behavior.
- The 1920 by 1080 reference depicts the three-column wide Dataset state.
  1440 by 900 remains required and may use two Dataset columns while the rail
  and inspector are visible. Columns derive from remaining central width with
  a 300-logical-pixel minimum and a maximum of three; card heights are not
  hardcoded from the image.

#### Header and responsive shell

- Wide mode shows labeled New, Import, Save, and Save As actions. Compact mode
  shows the corresponding icon buttons with tooltips. In narrow mode Save
  remains visible while New, Import, Save As, and guarded Close Configuration
  move into overflow.
- Appearance controls use a first-party Carnopy trio reconstructed from the
  approved reference: a white full sun for Light; an amber half-sun with three
  outward rays, one horizon, and two reflection lines for Warm; and a white
  crescent moon for Dark. The pinned Lucide sunset asset is not used because it
  does not match the approved geometry. The active theme receives an emerald
  frame.
- System remains available in Settings. While System is active, the effective
  sun or moon is framed and gains a small Auto/monitor marker. Selecting a
  header icon exits System. Show all three icons at logical widths of 800 and
  above and use one appearance menu below 800.
- With the inspector docked, its left boundary continues through the header
  immediately before the appearance icons. With the inspector collapsed or
  overlaid, remove the stale divider and keep the icons right-aligned.
- Wide mode at 1280 and above uses a collapsible persistent rail and docked
  inspector. Compact mode from 800 through 1279 uses an icons-only rail and an
  overlay inspector drawer. Narrow mode below 800 uses an overlay navigation
  drawer and near-full-width inspector sheet.
- Crossing a breakpoint closes transient navigation and inspector drawers and
  restores focus to the appropriate opener. Entering wide mode restores the
  persisted wide rail and inspector preferences. Leaving wide mode never
  overwrites those preferences.
- One shared action owns each rail or inspector toggle. Exactly one activation
  causes exactly one state change.

#### Dataset presentation

Number Dataset sections dynamically in this order:

1. Backend and mode.
2. Fluids.
3. Properties.
4. One section for each sampler in canonical grid order.
5. Dataset outputs as the final section.

Use **Sampling grid** in user-facing grouping; stable internal field
identifiers may retain axis terminology. Present models as Helmholtz Equation
of State (HEOS), Peng–Robinson (PR), and Soave–Redlich–Kwong (SRK).

- Selected fluids appear as requested-alias chips. Show `Canonical backend
  identities:` beneath them using the existing `canonical` model role.
- Add Fluid and Edit Properties open the same style of bounded, searchable,
  compatibility-aware popover. Changes apply immediately and remain applied
  when the popover closes through Done, Escape, or outside click. Focus returns
  to the invoking control.
- Selected-item overflow provides Move up, Move down, and Remove. Retained
  incompatible values remain visible with their issue.
- Show at most four fluid chips and then `+N more`; show at most six property
  rows and then `+N more`. The summary opens the corresponding popover.
  Preserve selected order. Use one bounded popover `ListView`; do not nest a
  popover scroll area inside the page scroll area.
- Search is case-insensitive across label, value, and canonical text. Keyboard
  navigation and selection, outside-click closure, Escape, Done, immediate
  add/remove, retained incompatibility, ordering, `+N more`, and focus
  restoration require behavioral tests.

Add private `label`, `symbol`, and `unit` roles while reusing `canonical`.
Symbols and units are presentation only and do not change serialized units,
schema tokens, metadata, or worker behavior.

| Property | Label | Trusted symbol markup | Presentation unit |
| --- | --- | --- | --- |
| `specific_enthalpy` | Specific enthalpy | `h` | `J·kg⁻¹` |
| `specific_entropy` | Specific entropy | `s` | `J·kg⁻¹·K⁻¹` |
| `specific_internal_energy` | Specific internal energy | `u` | `J·kg⁻¹` |
| `mass_density` | Mass density | `ρ` | `kg·m⁻³` |
| `isobaric_specific_heat_capacity` | Isobaric specific heat capacity | `cₚ` | `J·kg⁻¹·K⁻¹` |
| `isochoric_specific_heat_capacity` | Isochoric specific heat capacity | `cᵥ` | `J·kg⁻¹·K⁻¹` |
| `dynamic_viscosity` | Dynamic viscosity | `μ` | `Pa·s` |
| `kinematic_viscosity` | Kinematic viscosity | `ν` | `m²·s⁻¹` |
| `thermal_conductivity` | Thermal conductivity | `k` | `W·m⁻¹·K⁻¹` |
| `prandtl_number` | Prandtl number | `Pr` | `1` |
| `speed_of_sound` | Speed of sound | `a` | `m·s⁻¹` |
| `molar_mass` | Molar mass | `M` | `kg·mol⁻¹` |
| `critical_temperature` | Critical temperature | `T<sub>c</sub>` | `K` |
| `critical_pressure` | Critical pressure | `p<sub>c</sub>` | `Pa` |
| `triple_point_temperature` | Triple-point temperature | `T<sub>tr</sub>` | `K` |
| `surface_tension` | Surface tension | `σ` | `N·m⁻¹` |

The property-symbol component deliberately renders only these trusted static
symbols using Qt rich or styled text. It never renders user-provided text as
markup. Accessible names use the complete property labels, including
`critical temperature`, `critical pressure`, and `triple-point temperature`.

#### Lightweight Dataset projection

Add private, lightweight `sampler_point_count(sampler)` and
`projected_row_count(mode, fluid_count, sampler_counts)` helpers. Share
stepspace reachability behavior and the 1,000,000-row limit with production
normalization. The GUI does not import NumPy or materialize grids for these
projections.

Expose `SamplerDraft.sampleCount` and the following `DatasetDraft` projections:
`gridCombinationsPerFluid`, `projectedRowsPerFluid`, `projectedRows`,
`projectionAvailable`, and `projectionIssue`.

- `gridCombinationsPerFluid` is the product of required sampler counts before
  mode-specific expansion.
- `projectedRowsPerFluid` doubles grid combinations only for
  `saturation_table`; otherwise it equals grid combinations.
- `projectedRows` multiplies the per-fluid projection by the
  canonical-unique selected-fluid count.
- A valid complete sampler exposes its exact count. An incomplete or invalid
  sampler returns zero from the first unavailable count stage and exposes the
  structured sampler issue. An unreachable stepspace is not estimated or
  materialized and retains its reachability issue.
- With zero selected fluids, per-fluid counts remain available but total is
  zero and unavailable with a request for at least one fluid. Duplicate,
  unavailable, or incompatible fluids prevent a total claim and preserve the
  first fluid issue.
- A total above 1,000,000 remains exactly visible and `projectionAvailable`
  remains true, but `projectionIssue` is blocking and the Dataset draft is
  locally invalid.

The approved Property Table defaults project 4,141 grid combinations per
fluid, 4,141 rows per fluid, and 8,282 total rows. Permanent tests compare GUI
projection with production normalization for every sampler kind and mode.

#### Revision-bound worker validation

Reuse `validate_dataset_config`; do not add a protocol type. Privately expose
`canValidate`, `workerValidationState`, `workerValidationIssue`, and
`workerValidationIssues`.

| State | Exact meaning |
| --- | --- |
| `unavailable` | No document exists, so no exact YAML can be submitted. |
| `blocked` | A document exists, but local invalidity or an active plot edit prevents exact YAML submission. |
| `not_run` | Current YAML is locally valid and has never received a validation attempt. |
| `running` | A request is active for the captured current YAML bytes and SHA-256. |
| `valid` | The worker accepted bytes exactly matching the current document. |
| `invalid` | The worker rejected bytes exactly matching the current document as an invalid Carnopy configuration, identified by `category="config"` and `code="invalid_config"`; detailed validation issues may be empty. |
| `failed` | Another worker, transport, protocol, or operational failure occurred; no validity conclusion was reached. |
| `stale` | A prior result or in-flight request belongs to different document bytes. |

Transitions are exact:

- No document is `unavailable`. A new, imported, or replaced locally valid
  document is `not_run`; import loading is not validation unless the exact
  current preview bytes were validated.
- Local invalidity or an active plot edit is `blocked`. Starting standalone or
  Save validation captures exact bytes and hash and becomes `running`.
- A matching accepted result is `valid`. A matching
  `config`/`invalid_config` rejection is `invalid`, even when
  `details.issues` is missing or empty. Any other matching failure is `failed`.
- Editing after `valid`, `invalid`, or `failed` becomes `stale` when locally
  valid and `blocked` otherwise. Editing while running becomes `stale` and the
  late result is ignored. Reverting text does not resurrect an older result.
  When a blocked draft becomes valid, use `stale` if an earlier attempt exists
  and `not_run` otherwise.

`canValidate` requires an open document, both drafts locally valid, no active
plot edit, and an idle coordinator. Only the bottom inspector action invokes
standalone validation. It is informational and never enables, disables, gates,
or authorizes Save. `canSave` retains its existing local, lifecycle, and
coordinator rules. Every Save and Save As performs a fresh authoritative
worker validation of the exact bytes immediately before writing and never
consumes a cached standalone result. A matching Save result may update the
displayed state. Validation state is transient, nonserialized, excluded from
dirty state, and excluded from scientific identity.

#### Theme state and migration

Use one mode string throughout Python and QML: `system`, `light`, `warm`, or
`dark`. Replace `Theme.qml`'s Boolean with that mode; do not add per-theme
booleans.

- A missing stored value defaults to Dark. Preserve an existing valid mode.
  Replace an unknown or corrupt mode with Dark and persist the correction.
- System resolves live to Light or Dark only. System color-scheme changes and
  explicit mode changes update QML and the QML runtime's `QPalette` in the same
  event turn.
- Layout reset preserves theme and reduced motion. Existing geometry, screen,
  rail, and inspector setting namespaces remain unchanged.
- Apply the palette only to the QML runtime and restore the previous
  application palette during teardown. Qt fallback dialogs require readable
  Highlight and HighlightedText roles; true native dialogs remain OS-themed.
- Record the custom sun, sunset, and moon icons as first-party resources with
  hashes. Existing Lucide navigation assets retain their provenance.

### Stage 2 delivery and acceptance

The delivery hierarchy is `stage → step → commit`. A stage contains multiple
bounded implementation steps, and a step may require more than one Git commit.
The conventional-commit text attached to each numbered step below is the
recommended primary commit message, not the step's identity.

Use this exact step sequence. Each implementation step must be independently
reviewable and must pass its focused gate before the next begins.

Documentation synchronization is part of every implementation boundary. Before
each implementation handoff, update this section's current-status record and
every permanent document made stale by the change. Include those edits in the
same coherent implementation step, normally in its final commit, unless this
sequence explicitly assigns a separate documentation-only boundary. Do not
leave status recording until the maintainer notices a stale plan. When no
permanent document changes, the handoff must say which documents were reviewed
and why they remain accurate. This requirement does not make Graphify refresh
mandatory; public graph artifacts retain the separate intentional-refresh
policy below.

Verification is proportional to the boundary. Run focused static and behavioral
checks while implementing a step, then run the complete repository,
distribution, and preflight gates once at the stage-acceptance boundary unless a
failure or cross-cutting change requires an earlier full run. Do not repeatedly
run `pytest` and then `preflight.py` in one intermediate turn merely to execute
the same suite twice. When the only remaining work is a long aggregate gate,
the handoff may give the exact command to the maintainer instead of consuming an
interactive implementation turn; acceptance still waits for the reported
result.

Every implementation handoff must also recommend the parent model and reasoning
effort for the next step from the exact locally approved ladder. The
recommendation is advisory: the maintainer selects the setting before work
continues, and the agent must not change it silently. Base the recommendation on
the next step's actual difficulty, write/read scope, scientific risk, and
cross-file coupling rather than on the effort used for the completed step.
Project subagents retain their separately pinned profiles; this handoff rule
does not override them.

After Step 3 and before Step 4, complete the ignored design-reference gate.
That gate selected Precision Grid, retained only the numbered next-steps
progression as a named borrowed element, selected moderately expressive motion,
and approved `minimal-green-v1.png` unchanged as a provisional packaged mark.
The generated vector candidates were rejected and final logo refinement was
deferred. This completed gate does not reopen the settled layout, scope, Qt,
packaging, workflow, or scientific decisions.

Current implementation status as of 2026-07-23:

- Steps 1 through 4 are implemented in the Stage 2 branch history. The design
  and branding gate required between Steps 3 and 4 is complete under the
  provisional-logo decision recorded above.
- The Step 5 boundary is implemented and its focused verification passes. It
  provides the shared-QSettings appearance controller, Precision Grid design
  tokens, the responsive wide/compact/narrow shell, persistent wide-layout rail
  and inspector preferences, clamped window geometry, moderately expressive
  reduced-motion-aware transitions, the exact locked navigation names, disabled
  future-workflow affordances, Settings and Help pages, the used Lucide resource
  inventory, and focused QML/runtime/distribution regressions.
- The Step 6 boundary is implemented and its focused and repository-wide
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
- The Step 7 boundary is implemented and its focused and repository-wide
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
- Step 7 verification includes the 22-file non-writing QML format/lint gate,
  warning-free engine and interaction tests, exact success and rejection
  families for every sampler kind, anchor lifecycle and structured-field
  regressions, unchanged Widgets bindings, full Ruff and mypy gates, 673 passing
  repository tests, `preflight.py`, and environment compatibility checking.
  Native human inspection of the Dataset page and both successful and rejected
  unit toggles remains required before the maintainer accepts this commit.
- The separately approved Step 8 boundary is implemented in the Stage 2
  branch history.
  Public input units now additionally accept `hPa` and `atm` through the same
  exact sampler canonicalization boundary. Packaged starters
  and byte-identical repository examples use HEOS, Propane and Isobutane, CSV
  and Parquet, the approved 101-by-41 property grid whose pressure axis is
  101325 through 506625 Pa (exactly 1 through 5 atm), 101-point saturation
  coordinate, and 101-by-11 vapor-fraction grid.
- Step 8 verification includes exact new-unit canonical-key and production
  identity regressions, worker/QML capability projection, starter-template and
  safe-toggle tests, all static gates, and 686 passing repository tests,
  `preflight.py`, and environment compatibility checking. Authoritative CLI
  validation projected 8,282 property rows, 404 saturation rows, and 2,222
  vapor-fraction rows. Non-repository rehearsal generation completed all three
  starters with zero invalid rows; the final atmospheric property starter was
  regenerated separately with all 8,282 rows valid.
- The Step 9 boundary is implemented in the Stage 2 branch history. The QML
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
- Step 9 verification includes the 25-file non-writing QML
  format/lint gate, warning-free QML Add/invalid Commit/valid Commit/Cancel
  interaction tests, structured validation and mapping-row regressions,
  composition lifecycle tests, unchanged manual-plot and Widgets regressions,
  full Ruff and mypy gates, 694 passing repository tests, `preflight.py`, and
  environment compatibility checking. Native human inspection of the
  Visualization page remains required before the maintainer accepts this
  commit.
- The Step 10 boundary is implemented in the Stage 2 branch history. The configuration
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
- Step 10 focused verification includes the 29-file non-writing QML gate,
  warning-free QML YAML/search/blocker/decision interactions, controller and
  unchanged Widgets regressions, source and installed-resource inventory tests,
  workflow-policy tests, the full 705-test repository suite, `preflight.py`,
  environment compatibility checking, an outside-checkout installed-wheel QML
  smoke, and the complete local source/build/Twine/distribution-inventory gate.
  The CI and release workflows include a Python 3.12 installed-wheel QML smoke
  on Linux, Windows, and macOS covering warning-free startup, responsive state,
  YAML-page creation, one settings-controller interaction, and teardown. Those
  remote jobs passed after the human commit and push. Native dialogs remain
  outside headless CI, and this smoke is not Stage 8 platform qualification.
- Steps 11 through 17 are implemented in the Stage 2 branch history. Step
  11 locked the approved scientific-workbench reference and visual contracts;
  Step 12 made guarded close and SIGINT handling deferred, idempotent, and
  free of Python-override teardown tracebacks; and Step 13 made rail and
  inspector actions single-owner, first-click reliable, keyboard operable, and
  deterministic across responsive breakpoints.
- A focused corrective change after Step 13 keeps the shell interactive
  while capabilities load and exposes explicit preparation feedback. Workspace
  creation, initialization, and opening remain filesystem operations. After a
  workspace is activated, `DatasetConfigController` separately asks the local
  worker for the current CoolProp capabilities. That worker imports the
  installed package, enumerates fluids and aliases, and constructs the current
  model, property, and visualization choices without contacting a network
  service. The result is cached only for the application process. Milestone 1
  still has one backend, CoolProp; a future approved backend must make
  discovery and caching explicitly backend/model-aware rather than silently
  reusing this single-backend bootstrap.
- Step 14 implements revision-bound standalone validation with exact YAML
  bytes and SHA-256 binding, the approved typed states, stale-result rejection,
  empty-issue `config`/`invalid_config` handling, and Save independence. A
  standalone result remains informational; every Save and Save As starts a
  fresh authoritative validation.
- Step 15 implements shared lightweight sampler counts and Dataset row
  projections, the pre-materialization 1,000,000-row guard, and presentation-
  only property labels, scientific symbols, formatted trusted subscripts, and
  units. The approved Property Table projects 4,141 grid combinations and rows
  per fluid and 8,282 rows across the two canonical-unique default fluids,
  without importing NumPy or materializing a grid in the GUI process.
- Step 15 verification covers 30 QML files, the focused scientific and QML
  regressions, all static gates, 767 passing repository tests, `preflight.py`,
  and environment compatibility. The latest pushed branch passed all PR
  checks, including installed-QML startup smokes on Linux, Windows, and macOS.
  Those checks remain Stage 2 smoke coverage rather than Stage 8 platform
  qualification.
- Step 16 is implemented. Python and QML now use the single
  `system|light|warm|dark` mode contract; a missing QML preference resolves to
  Dark without mutating shared Widgets settings, corrupt stored values are
  repaired to Dark, and existing valid choices remain intact. Theme changes
  update the QML role palette and the runtime-only Qt fallback `QPalette`
  synchronously, and QML teardown restores the application's prior palette.
  Warm uses a deliberately amber, sunlit canvas and surface scale rather than
  a near-Light neutral treatment.
  The responsive command header exposes the approved first-party sun, sunset,
  and moon controls, including the System Auto marker and the continuous
  inspector boundary in the docked wide state. The three icon bytes and hashes
  are covered by the packaged-resource manifest and distribution inventories.
  Focused settings, runtime, shell, packaging, and resource tests cover
  migration, live switching, System resolution, palette restoration,
  responsive selector placement, and installed-byte provenance.
  Native uniform-grid sizing keeps responsive card rows equal-height and keeps
  both shared Visualization columns inside their card instead of allowing an
  expanding child layout to cover or clip adjacent content.
- Step 17 is implemented. Dataset fluid and property choices now use
  source-ordered Qt proxy models over the authoritative draft models, so
  case-insensitive search across labels, schema values, and canonical backend
  identities does not copy choice state into QML. Selection changes apply
  immediately through the desktop facade; selected incompatible values remain
  available for removal with their issue. The page shows bounded ordered
  summaries, `+N more` access, and per-item move/remove actions. Done, Escape,
  outside click, pointer activation, and keyboard activation retain changes and
  restore focus. The one bounded popup list lives on the window overlay while
  summary lists are noninteractive, avoiding nested page scrolling.
- Step 18 is implemented. The current QML pages use the approved minimal role
  palette, flat section hierarchy, compact controls, semantic hover/focus
  treatment, and reference-matched dark workbench structure. The Dataset page
  presents one ordered responsive workbench grid: Backend and mode, Fluids,
  Properties, canonical sampler cards, and Dataset outputs. It uses three
  aligned columns at 1920 logical pixels and two at 1440, followed by the
  Configuration summary and Document surfaces. Sampler fields have explicit
  labels, selected-fluid and property counts are live, and the Warm palette is
  visibly amber rather than a near-Light neutral treatment.
- The command header exposes labeled New, Import, Save, and Save As actions at
  wide sizes and keeps Save visible while the remaining document actions move
  into the narrow overflow. The Context inspector uses one flat divided
  hierarchy, selector hover remains readable in every theme, and the
  Visualization layout no longer clips or paints its mapping controls beyond
  the shared-settings card. Disabled navigation descriptions now follow the
  current Stage 3 ownership instead of obsolete Stage 4/5 timing.
- Step 18 verification includes the warning-free 32-file QML source gate,
  focused runtime, settings, shell, Dataset, Workspace, Visualization, YAML,
  packaging, and distribution regressions, live width/theme changes, and
  exact 1920 three-column and 1440 two-column layout assertions. Diagnostic
  native renders covered Dark, Warm, Workspace, Dataset, Visualization, and
  YAML surfaces; those temporary images are not repository assets.
- Step 19 is complete. The final local gate passed lock, lint, formatting,
  typing, the warning-free 32-file QML check, 785 repository tests, preflight,
  environment compatibility, isolated sdist-to-wheel construction, Twine, and
  exact wheel/sdist distribution inventories. PR #15 passed quality, Python
  3.11 through 3.14, the dedicated desktop job, dependency review and audit,
  CodeQL, distribution verification, and installed-QML startup smokes on
  Ubuntu, Windows, and macOS.
- The maintainer accepted the native application on Ubuntu 24.04.4 under
  WSL2/WSLg with Qt 6.11.1 after exercising the implemented QML workflow. The
  final visual correction adds readable selector padding and prevents sampler
  fields from painting outside their card during a responsive three-to-two-
  column transition. A focused geometry regression proves the last sampler
  field remains inside its card while ordinary card grids retain aligned row
  heights.
- One initial local full-suite process ended in a Qt segmentation fault during
  the acceptance audit. The same test and the entire 785-test suite then passed
  in four consecutive complete runs, and the remote desktop and three-platform
  QML jobs passed. No deterministic repository failure was reproduced; retain
  this observation as test-harness evidence rather than silently treating it as
  a supported-platform failure or inventing a workaround.
- No generation, inspection, table preview, plot rendering, VTK, or public-
  launcher parity is inferred from Steps 11 through 18. Configured plot
  requests remain under Visualization. The approved Stage 3 contract below
  assigns source and table inspection to Inspect and places both configured
  result viewing and session-only plot exploration under Visualization. Both
  public launchers remain on Widgets at this historical boundary. Stage 2 is
  complete; Stage 3 now owns parity, public-launcher migration, Widgets
  deletion, and the bounded `0.1.0a4` release qualification.
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
11. `docs(app): lock Stage 2 visual polish contracts`
   - Commit this complete refinement contract and the approved Dataset
     reference with its SHA-256. The image remains documentation only.
12. `fix(app): defer guarded QML shutdown`
   - Own only deferred close processing, idempotent teardown, event-filter
     removal and a one-use bypass, guarded SIGINT, and dirty, busy, and
     active-edit shutdown regressions.
   - Prove stderr remains free of Python-override tracebacks during normal,
     guarded, repeated, and interrupted close paths.
13. `fix(app): make QML shell actions reliable`
   - Route rail and inspector changes through shared actions, keep one visible
     control per state, implement deterministic breakpoint transitions and
     focus restoration, synchronize preferences, and cover keyboard and
     first-click behavior.
14. `feat(app): add revision-bound configuration validation`
   - Add typed validation state, exact-byte and hash binding, standalone
     validation through the desktop facade, the single inspector Validate
     control, empty-issue `config`/`invalid_config` classification, stale-result
     rejection, and Save independence with fresh-validation tests.
15. `feat(app): expose accurate Dataset projections`
   - Add lightweight sampler counts, shared projection formulas and row limit,
     Dataset projection properties and issues, private property presentation
     roles, trusted formatted subscripts, accessibility coverage, production
     parity, and heavy-import isolation.
16. `feat(app): add QML appearance modes and palette`
   - Replace the QML theme Boolean with one mode string; add Dark-default
     migration, Light/Warm/Dark/System settings, live QML-runtime `QPalette`
     synchronization and restoration, first-party appearance icons with
     resource hashes, and the responsive header selector.
17. `feat(app): add searchable Dataset selectors`
   - Add fluid and property popovers, immediate selection, retained
     incompatibility, bounded summaries, ordering/removal overflow, keyboard
     behavior, and focus restoration without nested scroll areas.
18. `style(app): apply the approved scientific workbench`
   - Apply the reference-matched minimal tokens, flat hierarchy, Dataset
     information architecture, hover treatment, readable fallback dialogs,
     responsive two/three-column behavior, and consistent styling across the
     current QML pages. Update packaged-resource and smoke coverage as needed.
19. `docs(app): complete GUI-2 Stage 2`
   - Create this documentation-only status commit only after all automated and
     remote gates, explicit native acceptance, and maintainer approval.
   - Update this plan and `DESKTOP_ARCHITECTURE.md`, record exact verified
     platforms and limitations, mark Stage 2 complete, and make Stage 3 active
     without claiming Stage 3 parity.
   - Re-audit the concrete desktop/QML size and coupling watchlist. Record real
     follow-up work with an acceptance boundary, but do not manufacture a
     refactor solely from line counts or temporary Widgets/QML overlap that
     Stage 3 already owns.

When these commits are implemented and committed sequentially, hunk-level
staging is not required. If work from more than one boundary exists together,
shared runtime, settings, QML, test, resource-inventory, and plan files require
hunk-level staging so every commit remains independently reviewable.

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
- deferred guarded close, idempotent teardown, SIGINT, event-filter removal,
  and stderr free of Python-override tracebacks; one-event rail and inspector
  actions, deterministic live breakpoint transitions, and first-click keyboard
  behavior;
- every revision-bound validation state and transition; exact-byte/hash
  matching; late-result rejection; empty-issue `config`/`invalid_config`
  handling; standalone validation that never authorizes Save; and fresh
  validation for every Save and Save As;
- sampler and Dataset projections for every sampler and mode, invalid and
  unreachable samplers, zero/duplicate/incompatible fluids, exact over-limit
  counts, production parity, formatted subscripts, and complete accessible
  property names;
- Dark-default theme migration, corrupt-setting repair, all four Settings
  modes, live System updates, runtime-palette restoration, custom appearance
  resource hashes, readable fallback dialogs, bounded searchable selectors,
  immediate selection, retained incompatibility, ordering, closure paths, and
  focus restoration;
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

Graphify refresh was not a Stage 2 completion requirement. It was subsequently
refreshed in commit `42ff05955e4dc6ea418a14a41bd9dda2780f7b12`; the public
report records merged Stage 2 commit
`e3550b244d2ac05d0a33cb37875c98c0cb49c7c5` as its source revision. That graph
is a useful map of the Stage 2 baseline. Once Stage 3 implementation advances,
use it only to narrow navigation and verify every exact claim against current
source and tests.

The durable freshness policy is recorded in
[`DESKTOP_ARCHITECTURE.md`](DESKTOP_ARCHITECTURE.md). Do not maintain a manual
per-commit counter. Git computes the distance from the recorded source revision
or, for legacy artifacts without one, from the latest commit touching the three
public graph outputs. A future refresh is most useful after Step 18 has settled
the QML structure; it remains a separately reviewed architecture-documentation
operation and must never remove the current public graph before a replacement is
complete and verified.

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

Current implementation status as of 2026-07-26:

| Step | Tracked state | Verification and remaining boundary |
| --- | --- | --- |
| 1. Lock the Stage 3 contract | Implemented and committed | The complete approved parity, ownership, provenance, launcher, retirement, and release contracts below are authoritative. |
| 2. Extract execution state | Implemented and committed | Focused checks and the branch's remote Desktop-app check passed. |
| 3. Add QML Run | Implemented and committed | Focused checks and the branch's remote Desktop-app check passed. |
| 4. Extract inspection state | Implemented and committed | Focused checks pass. Its remote run exposed the page-loader/delegate-incubation race recorded below. |
| 5. Add QML Inspect | Implemented and committed | Focused and native checks pass. Its remote run reproduced the same race rather than introducing a second Desktop-app failure. |
| 6. Extract Activity and Recovery | Implemented locally; human commit and push pending | Focused QML, Ruff, mypy, controller, Widgets-adapter, packaging, import-isolation, and exact Desktop-app checks pass. This boundary also carries the reviewed lifecycle correction below. |
| 7. Extract plot-result and session state | Next | Begin after the coherent Step 6/corrective push restores the remote Desktop-app check. |
| 8–13 | Planned | Not implemented. |

The two failed remote runs exposed a real QML lifecycle warning, not a
scientific, worker, inspection, or packaging failure. Rapid Dataset-to-Run
navigation replaced the central page `Loader` while `SearchableChoiceList`
still had a `ListView` delegate under incubation. Qt then reported both
`Loader: Cannot create delegate` and `Object or context destroyed during
incubation`. The local correction lazily instantiates each page on first visit
and retains it until runtime teardown, so navigation changes visibility rather
than destroying live delegates. Repeated runtime creation also avoids resetting
the already selected Basic Controls style. Warning assertions remain strict,
and a deterministic rapid Dataset-to-Run-to-Dataset regression verifies page
identity and warning-free navigation. Remote confirmation waits for the human
commit and push.

- Step 1 is complete and this tracked Stage 3 contract is the implementation
  authority.
- Step 2 is implemented. One composition-owned
  `DatasetExecutionController` now owns saved-configuration validation,
  generation, progress, cancellation, typed results, saved-baseline relation
  state, and the write side of Run activity. Request UUID reservation, initial
  schema-version-1 record persistence, and worker start occur synchronously
  without an event-loop handoff. Progress persistence is coalesced to at most
  four writes per second while phase and terminal changes persist immediately.
- The temporary Widgets Run page is now a view adapter over that controller,
  and the Jobs page no longer creates or updates execution records.
- Step 3 is implemented. The private QML frontend exposes the authoritative
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
  pandas, PyArrow, NumPy, CoolProp, or Matplotlib. The temporary Widgets Inspect
  and source-list pages are presentation adapters over the controller, and the
  existing Plot page receives only the controller's copied inspected payload
  until Step 7 extracts session plotting.
- Step 5 is implemented. The private QML frontend now exposes the bounded
  workspace source list, explicit external file/folder choices,
  Summary/Tables/Arrays/Diagnostics views, a virtualized 100-row table page,
  automatic first preview after explicit inspection, local paging, Focus
  Table, and an Inspect-specific context inspector. All operations cross queued
  root-facade signals; QML consumes only the lightweight typed models from Step
  4 and does not import or materialize source data.
- Workspace-generated outputs remain the primary Inspect source path: their
  typed workspace rows show source kind before the generated directory ID.
  External CSV/Parquet and run/bundle dialogs are explicitly for sources not
  selected from that list, and QML `file:` URLs are normalized by the
  composition facade before worker inspection.
- Run navigation is available only when the execution controller has an exact
  saved snapshot; Inspect remains available for an open workspace so historical
  outputs can be inspected without a current configuration. The Dataset draft
  check and Run saved-snapshot check are labeled as optional diagnostics.
  Generation still performs its own mandatory fresh worker validation.
- The QML runtime now applies the selected application palette before creating
  the QML engine, preventing fallback file dialogs from caching the platform
  highlight until the first theme change. Inspection fact layouts no longer
  feed a child width back into the `RowLayout` measuring it, and supported
  interaction tests remain warning-free.
- Dataset failure layer, code, and property aggregates remain visibly separate.
  Logical arrays retain per-array shapes and dtypes, and integrity wording stays
  source-kind-aware. The explicit `Explore in Visualization` affordance remains
  disabled until Step 7 introduces the authoritative session-plot controller;
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
- The temporary Widgets Jobs page is a narrow adapter over the controller, and
  importing the controller remains free of worker inspection and heavy
  scientific/data/rendering modules. Step 7 is the next active implementation
  boundary. `Inspect Run` exact
  cross-page navigation remains in Step 10, `View Plots` remains unavailable
  until Step 7, and neither public launcher has migrated.

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
- Temporary Widgets adapters consume extracted controllers only far enough to
  preserve GUI-1 behavior and parity tests. Do not backport new QML-only
  presentation behavior to a frontend deleted later in this Stage.

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

- `failureLayerCountsModel`: `layer`, `count`;
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
Configured plots
Explore inspected data
```

Configured plots contains the existing authoritative YAML configuration editor
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

`Explore inspected data` consumes the current ready Inspect selection, has no
duplicate source picker, uses a distinct workflow-local `PlotDraft`, remains
session-only, and never changes YAML. It renders only after explicit Render.

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
- Navigate to Visualization → Configured plots.
- Do not inspect or render automatically.
- If no configured visualization existed, show an explicit empty state with
  **Explore this run**.

**Explore this run**

- Explicitly inspect the generation's exact output directory.
- On success, navigate to Visualization → Explore inspected data.
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

Configured plots shows originating configuration SHA, run and visualization
identities, saved-baseline relation, and deterministic completed, failed, and
skipped cards. Failures show exact type and message and never a placeholder
graph. Explore inspected data uses an inline editor beside the preview in wide
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
- Explore inspected data requires a ready inspected dataset.
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
automatic preview, Focus Table, and paging through row 150. Session plotting is
honestly unavailable until its authoritative controller enters QML in Step 7.
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

#### Step 8 — Complete QML Visualization

Recommended commit:

```text
feat(app): add QML plot results and data exploration
```

Add Configured plots and Explore inspected data, deterministic outcome cards,
lazy previews, inline session editing, explicit Render, focus mode, Export/Open
actions, and render-another-format flow. Page entry and tab changes start no
worker.

#### Step 9 — Add QML Activity and Recovery

Recommended commit:

```text
feat(app): add QML activity and recovery
```

Add the two-tab Activity page, bounded records, typed details, exact cross-page
actions, diagnostic expansion, recovery selection, confirmation, and
accessible status presentation.

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
Inspect → Explore inspected data
```

Cover workspace/source replacement, both transient edit types, busy close,
cleanup refusal, repeated launch/close, and warning-free teardown. Do not
migrate launchers before this boundary is green.

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

If the tracked Graphify freshness threshold is exceeded after this structural
deletion, refresh only the three public graph artifacts in a separate
`docs(graph)` commit before final acceptance.

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
- Present three primary installation paths and one compact advanced-extras
  table.
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
real scientific and desktop value, present isolated desktop through `uv`,
desktop plus CLI/library through `pip`, and lightweight base CLI/library as the
three main installation paths, and place `viz`, `ml`, `analysis`, and `all` in
one compact reference table.

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
- The refreshed Graphify graph describes the merged Stage 2 baseline. It is
  navigation-only once Stage 3 advances; current source and tests remain
  authoritative.
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
