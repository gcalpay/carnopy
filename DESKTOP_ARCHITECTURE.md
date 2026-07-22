# Carnopy desktop architecture and evolution

This document is the durable architectural record for Carnopy's desktop
application. It explains the implemented system, the boundaries contributors
must preserve, and the major steps by which the desktop evolved. It is not a
replacement for the public scientific and packaging contracts in
[`AGENTS.md`](AGENTS.md), and it is not an implementation backlog.

While GUI-2 is active, [`GUI2_PLAN.md`](GUI2_PLAN.md) remains the source of truth
for planned work, acceptance gates, and stage status. This document records
only architecture that exists in the repository or an explicitly identified
historical boundary. Update it when an accepted change alters ownership,
process isolation, frontend status, persistence, packaging, or a major
workflow. Every implementation handoff must still review and synchronize the
applicable tracked documentation. While GUI-2 is active, its plan records each
implemented boundary; a small fix that does not alter durable architecture need
not expand this document, but it must not leave the active plan or user-facing
guidance stale.

## Current state

The desktop has two frontend implementations during the GUI-2 migration:

- `carnopy-app` and `carnopy-gui` still launch the completed Qt Widgets
  application from the `0.1.0a3` line;
- `python -m carnopy.app.qml_launcher` launches the private GUI-2 QML
  application used for development and qualification;
- both frontends reuse the same authoritative QtCore controllers and private
  worker boundary;
- the QML application currently implements the responsive shell, Workspace,
  Dataset, Visualization, YAML Preview, Settings, and Help surfaces, including
  worker-validated Save and Save As;
- typed blocking state, revision-bound standalone validation, operation
  feedback, exact Dataset row projections, and composition-owned document and
  shutdown decisions are shared with the authoritative controllers rather than
  reimplemented in QML;
- generation, inspection, table preview, plotting, jobs, recovery, and Widgets
  retirement belong to later GUI-2 stages.

The development version is `0.1.0a4.dev0`. The two public launchers switch to
QML only after Stage 3 reaches tested GUI-1 parity; Carnopy will not ship two
normal desktop applications or a frontend selector.

## Authority map

Use the narrowest applicable authority:

| Source | Authority |
| --- | --- |
| `AGENTS.md` | Public scientific, data, architecture, packaging, and contribution contracts |
| `.agents/local.md` | Checkout-local execution, environment, credential, dependency, and Git restrictions |
| `GUI2_PLAN.md` | Temporary GUI-2 scope, sequencing, decisions, and acceptance status |
| `DESKTOP_ARCHITECTURE.md` | Durable implemented desktop structure and evolution |
| `README.md` | User-facing installation and workflow guidance |
| `graphify-out/` | Generated navigation aid; never stronger than source or tracked contracts |

When these disagree, do not silently blend them. Repository source and tests
establish current behavior, while `AGENTS.md` and an active approved stage plan
constrain what may change.

## Permanent boundaries

The desktop is a presentation frontend for existing Carnopy workflows. It is
not a second scientific implementation.

1. **Scientific isolation.** The GUI process must not import CoolProp,
   generation pipelines, pandas, PyArrow, Matplotlib renderers, or native
   scientific rendering implementations. The worker process owns those imports.
2. **One private worker per request.** Controllers communicate with a
   short-lived worker through the private versioned JSON Lines protocol. They
   do not invoke or parse the public CLI.
3. **One active desktop request.** A composition-owned coordinator admits and
   routes one request globally. Individual pages cannot create competing
   worker ownership.
4. **Worker authority.** Local draft validation provides immediate editing
   feedback. Import, Save, Save As, generation, inspection, and rendering retain
   worker-side validation at their established trust boundaries.
5. **Portable configuration.** YAML remains the portable configuration
   authority. QML and Widgets edit the same drafts and deterministic document;
   neither owns a private configuration copy.
6. **Immutable scientific output.** Finalized run directories remain immutable.
   Desktop staging and promotion preserve the existing no-overwrite, integrity,
   and provenance rules.
7. **No public API expansion.** Desktop progress, cancellation, request
   envelopes, drafts, and controllers remain private application interfaces.
8. **Reference-state clarity.** Dataset generation resets each requested fluid
   to CoolProp `DEF` once before row evaluation. Absolute enthalpy, entropy, and
   internal-energy values are meaningful only within the recorded compatible
   backend, model, version, and reference-state context.

## Runtime topology

```text
Public Widgets frontend               Private QML frontend
MainWindow + page adapters            QQmlApplicationEngine + QML views
             |                                      |
             +---------------+----------------------+
                             |
                    DesktopController
                   composition and facade
                             |
          +------------------+------------------+
          |                  |                  |
 WorkspaceController  DatasetConfigController  QmlSettingsController
          |                  |
          |          DatasetDraft + VisualizationDraft
          |                  |
          +---------- DesktopRequestCoordinator
                             |
                         WorkerClient
                       QProcess transport
                             |
             python -m carnopy.app.worker
                  private JSON Lines v1
                             |
       existing validation, generation, inspection,
          preparation, visualization, and I/O code
```

The frontend layer renders state and forwards user intent. QtCore controllers
own workflows and expose models, typed properties, and narrow signals. The
worker imports and executes scientific or data-heavy code only after receiving
a validated private request envelope.

## Composition and ownership

### `DesktopController`

`DesktopController` is the application composition root and the authoritative
cross-controller facade. One instance owns:

- the stable `QSettings` identity;
- `QmlSettingsController`;
- `WorkerClient`;
- `DesktopRequestCoordinator`;
- `WorkspaceController`;
- `DatasetDraft`;
- `VisualizationDraft`; and
- `DatasetConfigController`.

It binds workspace activation to configuration context exactly once. QML may
edit a child draft through explicit local-edit requests, but workspace changes,
document replacement, mode or coordinate replacement, Save, and shutdown must
pass through composition-level decisions and guards. This prevents a view from
bypassing dirty-state, active-edit, or worker-busy rules.

### `DesktopRequestCoordinator`

The coordinator owns the global active request, including:

- request UUID and protocol type;
- one owner: `configuration`, `execution`, `inspection`, or `plot`;
- cancellation policy and force-stop state;
- terminal worker event and process outcome;
- stderr and cleanup status; and
- an optional parent-side finalizer.

It rejects unsupported owner/request combinations and concurrent requests.
Stale or foreign events are not delivered to another controller. Cooperative
cancellation becomes available only when the worker reports a cancellable
phase. Force stop is explicit and remains distinguishable in the terminal
envelope.

### `WorkerClient`

`WorkerClient` is transport, not workflow logic. It starts one `QProcess`,
writes one request envelope, parses worker events, collects stderr and exit
status, and emits one transport outcome after process termination. It does not
decide which page owns a request or how workflow-specific staging is finalized.

The protocol models live in `carnopy.app.protocol`. Protocol versioning,
request UUIDs, typed request names, and terminal events prevent controllers
from treating arbitrary worker output as a successful operation.

## Worker request lifecycle

The normal lifecycle is:

1. A controller asks `DesktopRequestCoordinator` to start a supported request
   under its fixed owner.
2. The coordinator rejects the request if another one is active, creates an
   owner-scoped session, and delegates transport to `WorkerClient`.
3. The worker validates the protocol envelope, emits `accepted`, and reports
   phase/progress events where supported.
4. The coordinator routes events only to the matching session.
5. A terminal `result`, `error`, or `cancelled` event is retained while the
   client waits for actual process exit and stderr completion.
6. The coordinator combines the terminal event, transport status, force-stop
   state, and finalizer result into one `RequestOutcome`.
7. The owning controller updates its durable state or reports structured
   failure. The coordinator then permits another request.

This separation matters because a valid-looking result event is insufficient
if the process exits abnormally, cleanup fails, or the request belongs to a
different workflow.

## Workspace lifecycle

A workspace is a user-selected local directory with this managed structure:

```text
<workspace>/
  configs/
  outputs/
  figures/
  .carnopy-gui/
    workspace.json
```

The private marker contains workspace schema version 1. The three user
operations intentionally differ:

| Operation | Input | Result |
| --- | --- | --- |
| Create Workspace | Existing parent plus a new child name, or an expert non-existing path | Creates the new root, managed directories, and marker |
| Initialize Existing | Existing ordinary directory, after explicit confirmation | Adds managed directories and marker without deleting unrelated contents |
| Open Workspace | Existing initialized Carnopy workspace | Verifies the marker and all required directories, then activates it |

Preflight is non-writing. Commit revalidates the plan; existing-directory
operations also recheck device and inode identity after confirmation. The
composition layer runs lifecycle guards before preflight and again before
commit. Recent workspaces are canonical paths stored under the stable Carnopy
application identity.

## Dataset configuration ownership

`DatasetConfigController` owns the complete document workflow, not a Widget or
QML page. It coordinates:

- workspace context and capability discovery;
- New, Import, document replacement, and close;
- deterministic merging of `DatasetDraft` and `VisualizationDraft`;
- local validity, dirty state, and YAML preview;
- worker-authoritative import and exact-YAML Save validation;
- Save versus Save As, imported-reformat confirmation, and external-change
  protection;
- atomic workspace-owned replacement and no-overwrite new writes; and
- saved execution snapshots.

`DatasetConfigDocument` retains the complete YAML payload independently of the
structured drafts. This preserves unknown or non-edited document sections and
allows the controller to merge authoritative draft sections into the complete
document rather than reconstructing a partial file.

Workspace initialization itself does not load a backend. After activation,
`DatasetConfigController` prepares the configuration editor with a local
`describe_capabilities` worker request. For the current single-backend
milestone, that worker imports the installed CoolProp package, enumerates fluid
names and aliases, and builds the supported model, property, and visualization
choices. It performs no network request. Results are cached only for the life
of the application process. If Carnopy later approves another backend, the
capability request and cache identity must become explicitly backend/model-
aware; the current CoolProp-only path is not a general plugin architecture.

The document is updated only from locally valid dataset and visualization
state. A successful worker validation and file write refreshes baselines;
failed validation or writing does not declare the draft saved.

The controller projects YAML availability and its first blocker as typed state:
`yamlAvailable`, `blockingSection`, `blockingField`, `blockingRow`, and
`blockingIssue`. Invalid draft state always exposes an empty YAML preview; the
last valid serialization and a best-effort replacement are never presented as
current. Stable field and row identifiers drive navigation in both QML and
Widgets adapters without parsing issue prose.

Save and Save As submit the exact visible complete-document YAML to the worker
before any write. Imported-document reformat consent, external-change choices,
no-overwrite Save As, atomic verified replacement, in-flight mutation checks,
and baseline refresh retain the established controller and document ownership.
Typed `operationFailed`, `saveSucceeded`, and `importSucceeded` signals provide
QML feedback while the existing Widgets signals remain available during the
migration.

Standalone worker validation is transient and revision-bound. The controller
captures the exact visible YAML bytes and SHA-256 and reports `unavailable`,
`blocked`, `not_run`, `running`, `valid`, `invalid`, `failed`, or `stale`.
Edits invalidate the relationship to any prior or in-flight result, and late
results for other bytes are ignored. A `config`/`invalid_config` response is
invalid even when its detailed issue list is empty. This state never authorizes
Save: every Save and Save As starts fresh worker validation of the exact bytes
immediately before writing.

### `DatasetDraft` and `SamplerDraft`

`DatasetDraft` owns model, mode, coordinate choice, ordered fluids, properties,
output formats, sampler drafts, compatibility, local validity, structured
first-invalid projection, and its dirty baseline. Its list models are the
single source used by both frontends.

`SamplerDraft` owns raw declared sampler values and units. Unit changes use one
private valid-definition anchor and the lightweight canonical sampler identity:

- every calculation begins from `.15g`-stabilized binary64 text;
- private Decimal work uses the fixed reviewed context;
- a unit-only candidate commits only when its canonical key exactly equals the
  anchor key;
- rejected changes are atomic and retain the current raw state and dirty state;
- the GUI does not materialize NumPy grids, normalized bytes, hashes, or
  `spec_id`; and
- production tests prove those identities as consequences of equal canonical
  keys.

The public input-unit set is temperature `K`/`degC`, pressure
`Pa`/`hPa`/`kPa`/`MPa`/`bar`/`atm`, and dimensionless vapor mass fraction.
Fahrenheit, psi, tolerances, and user-selectable float precision are not part of
the current contract.

`SamplerDraft.sampleCount` and the Dataset projections
`gridCombinationsPerFluid`, `projectedRowsPerFluid`, `projectedRows`,
`projectionAvailable`, and `projectionIssue` use the same lightweight sampler
count, stepspace-reachability, saturation-expansion, canonical-fluid, and
1,000,000-row rules as production normalization. They neither import NumPy nor
materialize grids in the GUI process. Production rejects an oversized request
before allocating a grid. Projection state is transient, nonserialized, and
excluded from configuration identity and dirtiness.

Dataset property rows add presentation-only label, symbol, and unit roles over
the existing canonical token. Trusted static symbols deliberately use styled
text for scientific subscripts; user input is never interpreted as markup.
These roles do not alter YAML property names, generated columns, metadata, or
worker behavior.

### `VisualizationDraft` and `PlotDraft`

`VisualizationDraft` owns configured-visualization enabled state, shared
format, fluids, filters, display units, ordered durable plot snapshots,
compatibility, validity, and canonical/raw baselines. Disabled visualization
retains latent settings but emits no visualization payload.

Stored plot rows are snapshots, not persistent `PlotDraft` instances. Exactly
one temporary workflow-local `PlotDraft` may exist for Add or Edit. It must be
committed or cancelled explicitly; it is transient unresolved state rather
than durable configuration dirtiness. Dataset-context replacement and other
cross-controller operations therefore pass through composition-owned
active-edit guards before workspace preflight and commit, document replacement,
Save, mode or coordinate replacement, and shutdown. Shared visualization
mutations and durable plot-list changes are also locked while the temporary
editor exists.

The QML Visualization page binds the ordered durable snapshot model directly
and presents the one active `PlotDraft` as an inline master-detail editor. Plot
fields, workflow-local fluid overrides, filters, series selections, display
units, and optional format inheritance remain separate raw draft state until
Commit. Invalid Commit retains the temporary editor and focuses a stable
`plot.*` field and optional row; controller and QML code never parse issue prose
to navigate. Widgets keep the established modal dialog over the same draft and
lifecycle.

Stage 2 edits configured plot requests but intentionally does not render them.
Reusable post-generation requests remain on Visualization. Stage 3 will expose
generated outputs and rendered artifacts through Inspect while preserving the
worker-only rendering boundary; its design must explicitly place the separate
session-only manual-plot workflow.

The QML YAML Preview page is a read-only projection of the complete document.
It provides line numbers, search, selection/copy, file and dirty-state context,
and typed navigation to the first blocking Dataset or Visualization field. It
does not edit YAML or retain stale text. Command-bar New, Import, Save, Save As,
and Close actions cross the root runtime bridge into `DesktopController`; QML
owns only the consequential decision dialogs and native file selection, not the
underlying workflow.

## Frontends

### Public Qt Widgets frontend

`carnopy.app.window.MainWindow` remains the public frontend during Stage 2.
Widgets pages are adapters over shared controllers for workspace,
configuration, execution, sources, jobs, recovery, plot requests, and image
preview. Widgets retain native file dialogs and existing manual workflows as a
parity oracle until Stage 3.

Widgets must not regain shadow draft state while QML is added. A behavior fix
at a shared boundary must be reflected in both frontends, as with safe sampler
unit changes and composition-owned workspace operations.

### Private QML frontend

`carnopy.app.qml_launcher` is intentionally not a project entry point yet. It
loads the packaged `Carnopy` QML module for development, installed-resource
smoke testing, and native acceptance.

Startup ordering is deliberate:

1. create `QApplication`;
2. apply organization `Carnopy` and application `Carnopy Desktop`;
3. select Qt Quick Controls Basic style;
4. create `QSettings` and the desktop composition;
5. verify and register mandatory resources and fonts;
6. configure installed QML import paths and warning capture;
7. load the engine and verify its root object; and
8. apply an optional initial workspace through the guarded facade.

Missing mandatory resources, font registration failures, QML startup warnings,
load failures, and zero root objects are fatal. Later runtime warnings are
logged and surfaced without unconditionally terminating the application.

QML views emit root-level request signals. `QmlApplicationRuntime` connects
them to Python with queued Qt connections, avoiding re-entrant model mutation
while delegates are handling input. Native folder dialogs have an explicit
transient parent and defer path dispatch until the dialog is hidden and the
event loop advances. Save-file selection follows the same deferred boundary.
Window close is routed through the composition-owned active-edit, worker-busy,
and dirty-document guards before runtime teardown.

Close processing is deferred out of the native event-filter callback. Teardown
is idempotent, removes the close filter before object destruction, and uses a
one-use bypass only after the composition guard accepts the close. SIGINT enters
the same guarded path. This prevents re-entrant Qt destruction and Python-
override tracebacks while preserving dirty, busy, and active-edit decisions.

### Native QML window lifecycle invariants

Window restoration regressed twice when responsibility was split between QML
and Python. A QML completion handler made the window visible or maximized on
Qt's default screen, after which a delayed Python callback moved the already
mapped native window to the remembered monitor. On WSLg/XCB this could create
an off-screen decorated frame, a compositor-visible cross-screen remap, and an
apparently frozen input surface. Starting another launcher while the first was
still alive compounded the symptom because both software-rendered shells
overlapped and wrote the same settings.

The permanent invariants are:

- `QmlApplicationRuntime` alone decides when the native window is shown or
  maximized. QML may initialize the persisted client rectangle only while the
  root remains hidden.
- The hidden window is assigned and fitted to the selected logical screen
  before it is exposed to the compositor. A windowed launch receives at most
  one later decorated-frame fit before geometry tracking is enabled.
- One per-user runtime lock rejects a concurrent QML launcher. Diagnostics must
  close every process they start; before diagnosing a frozen event loop, check
  for overlapping launcher and worker processes.
- QML placement state is versioned. A restoration-contract change must migrate
  or discard only `qml/window/*` placement keys; it must retain appearance,
  layout, recent-workspace, and unrelated Widgets settings.
- Widgets and QML deliberately share the stable application identity and
  `recent_workspaces`. Widgets `window_geometry` and QML `qml/window/*` remain
  separate, and neither frontend stores scientific draft or YAML state in
  `QSettings`.
- A clean close records the actual screen and normal client geometry. Tests
  must cover hidden-before-show ordering, obsolete-state migration,
  single-instance rejection, settings isolation, and a clean replacement
  launch after the lock is released.

### Responsive shell and settings

The approved Precision Grid shell is desktop-first and uses logical pixels:

- wide: at least 1280;
- compact: 800 through 1279;
- narrow: below 800.

Card columns depend on available central width with a 300-pixel minimum and a
maximum of three. The navigation rail and context inspector have persisted
wide-layout preferences; compact and narrow overrides do not overwrite them.
Each surface has one shared toggle action, so pointer, keyboard, settings, and
breakpoint transitions cannot apply duplicate state changes. The shell remains
interactive while capability discovery is active and shows that it is
preparing local CoolProp capabilities rather than implying network activity.
Window restoration clamps the full decorated frame to an available screen and
prefers the monitor on which the window was last closed. The runtime assigns
and fits the still-hidden native window to that monitor before showing or
maximizing it, avoiding a compositor-visible cross-screen remap on a restored
launch. A versioned migration discards placement state written by the retired
restoration path once, then subsequent clean closes again remember the actual
monitor. The private QML launcher also holds a per-user runtime lock so two
CPU-rendered native shells cannot overlap and race on the same settings.

The stable QSettings identity preserves GUI-1 recent workspaces. New settings
are namespaced:

```text
qml/theme/mode
qml/accessibility/reduced_motion
qml/layout/wide_rail_collapsed
qml/layout/wide_inspector_collapsed
qml/window/normal_geometry
qml/window/normal_screen
qml/window/maximized
qml/window/state_version
```

The shell bundles IBM Plex Sans and Mono, a hashed subset of Lucide SVG icons,
their licenses, and a provisional raster Carnopy mark. The machine-readable
resource manifest records provenance and hashes; distribution checks compare
source and installed resources. The manifest-hashed resource tree disables Git
text conversion so every platform packages the exact committed bytes rather
than rewriting vendored SVG or license line endings during checkout.

## Persistence, integrity, and failure behavior

Desktop operations preserve existing filesystem boundaries:

- imported external configuration files are never silently overwritten;
- workspace-owned replacements are validated and atomic;
- Save As refuses an existing destination;
- a source hash protects against external modification between load and Save;
- execution accepts the exact saved workspace configuration and verifies its
  hash;
- finalized dataset runs are immutable;
- worker-owned dataset staging and guarded parent-owned plot staging have
  separate cleanup rules; and
- manual plot image/sidecar promotion revalidates leases, manifests, paths,
  hashes, and inode identities.

Failures retain structured worker diagnostics. GUI status prose is for people,
not control flow: field focus and navigation use stable identifiers rather than
parsing English messages.

## Packaging and verification

The desktop remains optional through the `app` extra. It uses
`PySide6-Essentials>=6.11.1,<6.12` and does not vendor Qt or ship a standalone
installer. The companion native VTK bridge retains its separately qualified
Python and Qt bounds.

Matplotlib is a required renderer for current plotting workflows but remains an
optional packaging dependency: `viz`, `app`, and `all` install it, while the
base CLI-first distribution does not. Distribution CI therefore keeps two
complementary contracts. Base wheel and sdist smokes submit an otherwise valid
plot request and require the actionable missing-visualization-extra failure;
`app` and `all` smokes submit the same request with Matplotlib installed and
require a real image and provenance sidecar. Multi-fluid smoke sources must
select one emitted canonical fluid so source ambiguity does not mask either
renderer result.

Desktop verification is layered:

| Surface | Purpose |
| --- | --- |
| `tests/test_app_*.py` | Controller, draft, Widgets, QML engine, and interaction contracts |
| `scripts/check_qml.py` | Non-writing QML format, import, and lint checks |
| dedicated Linux app CI job | App-extra typing and desktop tests under Qt offscreen execution |
| installed smoke tests | Public Widgets launchers plus private packaged-QML startup, responsive state, YAML-page creation, one controller interaction, teardown, and resource checks |
| distribution checker | Exact wheel/sdist module, QML, font, icon, license, and provenance inventories |
| manual native acceptance | File dialogs, monitor/DPI behavior, themes, keyboard use, and perceived interaction |
| native qualification workflow | Explicit Qt Quick/VTK bridge qualification, not a routine PR requirement |

Cross-platform QML startup and focused interactions in Stage 2 are smoke
coverage, not full Windows or macOS qualification. Full platform, packaging,
and release qualification remains GUI-2 Stage 8.

## Evolution ledger

### GUI-1: `0.1.0a3` Widgets application

GUI-1 established the permanent desktop boundary in seven development stages:

1. private worker protocol, structured progress, cancellation, and worker-owned
   staging cleanup;
2. optional app packaging, public launcher, workspace lifecycle, and Widgets
   shell;
3. worker-validated dataset editor and deterministic YAML workflow;
4. saved-config execution, source inspection, bounded table previews,
   workspace-local jobs, and guarded recovery;
5. worker-rendered manual plots, no-overwrite promotion, and Qt-only PNG/SVG
   preview with explicit PDF opening;
6. CI, distribution, documentation, and release hardening; and
7. architecture boundary review and generated Graphify map.

The temporary GUI-1 plan was deleted when that migration completed. Its final
tracked content remains recoverable for archaeology with:

```bash
git show d25a1e0^:GUI_PLAN.md
git log --oneline -- src/carnopy/app
```

### GUI-2: QML and native scientific 3D

GUI-2 is delivered one stage branch and pull request at a time:

| Stage | Durable outcome | Current status |
| --- | --- | --- |
| 0 | Qualified a same-repository `QQuickVTKItem` companion bridge on the pinned Linux/Qt/VTK baseline | Complete |
| 1 | Extracted request ownership, workspace state, dataset/visualization drafts, and complete configuration workflow into QML-ready QtCore controllers | Complete |
| 2 | Package the Precision Grid QML Workspace, Dataset, Visualization, and YAML/Save workflows | Active; implemented through Commit 15, latest PR checks green, Commits 16–19 and final native acceptance pending |
| 3 | Migrate remaining GUI-1 workflows, reach parity, switch both launchers to QML, and remove Widgets | Pending |
| 4 | Add controlled sweep and preparation worker operations | Pending |
| 5 | Add structured sweep and preparation QML workflows | Pending |
| 6 | Build exact emitted-value 3D scene contracts | Pending |
| 7 | Integrate native interactive 3D into QML | Pending |
| 8 | Complete platform, distribution, documentation, and release qualification | Pending |

Stage 2 has also established definition-first sampler canonicalization, exact
anchor-based GUI unit changes, Qt 6.11.1 as the QML baseline, packaged QML
resources, responsive settings, trusted workspace flows, structured Dataset
and Visualization editing, typed YAML and operation state, worker-validated
Save flows, practical starter grids, `hPa`/`atm` input units, safe native-window
teardown, reliable responsive shell actions, revision-bound standalone
validation, exact Dataset projections, and scientific property presentation.
These additions do not imply QML parity or public-launcher migration. The
approved appearance, searchable-selector, and final workbench styling commits
remain pending.

## Known current limitations

- The public desktop experience is still Widgets; the modern QML launcher is a
  private development entry point.
- The QML application can configure and save YAML but cannot yet execute or
  render its configured visualization; rendering remains worker-owned
  later-stage functionality.
- QML generation, inspection, tables, plotting, jobs, recovery, sweep,
  preparation, and 3D are not implemented.
- Native folder dialogs and compositor behavior require human acceptance;
  headless tests do not automate them.
- The current WSLg development host can use CPU rendering through Mesa
  llvmpipe, which affects perceived QML scrolling and animation performance.
  A database would not correct that rendering limitation.
- The packaged Carnopy mark is provisional and will be refined through an
  explicit branding decision rather than automatic tracing.

## Contributor change map

When changing the desktop, start at the owner of the behavior:

| Change | Primary owner |
| --- | --- |
| Process transport or JSON Lines parsing | `carnopy.app.client` and `carnopy.app.protocol` |
| Global request admission, routing, cancel, or finalization | `carnopy.app.request_coordinator` |
| Workspace paths, marker, and trusted filesystem operation | `carnopy.app.workspace` |
| Observable workspace state and recents | `carnopy.app.workspace_controller` |
| Cross-workflow decisions and guards | `carnopy.app.desktop_controller` |
| Dataset document, merge, validation, Save, and dirty workflow | `carnopy.app.config_controller` and `config_document` |
| Dataset or sampler editable state | `dataset_draft` and `sampler_draft` |
| Configured visualization or temporary plot state | `visualization_draft`, `plot_draft`, and `mapping_draft` |
| Widgets presentation | `window` and the relevant Widgets page/editor |
| QML presentation | `qml/Carnopy/` plus narrow runtime signal wiring |
| QML startup, resources, fonts, and warning policy | `qml_runtime`, `qml_resources`, and the resource manifest |
| Scientific behavior | Existing non-app domain/pipeline module, executed by the worker |

Before editing, inspect the applicable controller, both frontend adapters, its
focused tests, `AGENTS.md`, and the active GUI-2 stage plan. If a change appears
to require scientific code in QML, a second configuration copy, a direct CLI
call, multiple simultaneous workers, or weaker file-integrity checks, stop and
re-evaluate the ownership boundary.
