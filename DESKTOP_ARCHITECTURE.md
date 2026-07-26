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
  Dataset, Visualization, YAML Preview, Run, Inspect, Settings, and Help surfaces,
  including worker-validated Save and Save As plus exact-saved-configuration
  validation and generation;
- typed blocking state, revision-bound standalone validation, operation
  feedback, exact Dataset row projections, and composition-owned document and
  shutdown decisions are shared with the authoritative controllers rather than
  reimplemented in QML;
- saved-config validation and generation state are owned by one
  `DatasetExecutionController`; both the private QML Run workflow and the
  public Widgets Run page are view adapters over it;
- source discovery, worker inspection, typed source summaries, logical-array
  metadata, table selection, and bounded preview state are owned by one
  `InspectionController`; the private QML Inspect workbench and public Widgets
  Inspect/source pages are view adapters over it;
- private Run-activity loading, typed projection, record-only removal,
  interrupted-state projection, and identity-checked staging recovery are owned
  by one `ActivityController`; the public Widgets Jobs page is a view adapter
  over it;
- configured plot-evidence projection is owned by one
  `ConfiguredPlotResultsController`, while inspected-data plot editing and
  rendering are owned by one `SessionPlotController`; the public Widgets Plot
  page is a temporary view adapter over the latter;
- QML plot-result viewing and exploration, the QML Activity page, launcher
  migration, and Widgets retirement belong to the remaining Stage 3 steps.

The development version is `0.1.0a4.dev0`. The two public launchers switch to
QML only after Stage 3 reaches tested GUI-1 parity; Carnopy will not ship two
normal desktop applications or a frontend selector. The resulting QML parity
application is the planned `0.1.0a4` alpha checkpoint. Later sweep,
preparation, and native-3D stages are not prerequisites for that release.

## Authority map

Use the narrowest applicable authority:

| Source | Authority |
| --- | --- |
| `AGENTS.md` and its routed agent guides | Public scientific, data, architecture, packaging, and contribution contracts |
| `.agents/local.md` | Checkout-local execution, environment, credential, dependency, and Git restrictions |
| `GUI2_PLAN.md` | Temporary GUI-2 scope, sequencing, decisions, and acceptance status |
| `DESKTOP_ARCHITECTURE.md` | Durable implemented desktop structure and evolution |
| `README.md` | User-facing installation and workflow guidance |
| `graphify-out/` | Generated navigation aid; never stronger than source or tracked contracts |

When these disagree, do not silently blend them. Repository source and tests
establish current behavior, while `AGENTS.md`, its task-routed authoritative
guides, and an active approved stage plan constrain what may change.

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
          +------- DatasetExecutionController
          |
          +------------ InspectionController
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
- `VisualizationDraft`;
- `DatasetConfigController`;
- `DatasetExecutionController`;
- `InspectionController`;
- `ActivityController`;
- `ConfiguredPlotResultsController`;
- `SessionPlotController`; and
- the shared verified-plot preview registry.

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

Execution startup has an additional private reservation boundary. Reserving a
UUID prevents another request from starting but does not advertise global busy
state. `DatasetExecutionController` atomically writes the initial Run-activity
record, then promotes that exact UUID into an active worker session in the same
Qt call stack. Failure before promotion abandons the reservation and starts no
worker. Other workflows continue to use the coordinator's ordinary
`start_request()` convenience path.

### `DatasetExecutionController`

`DatasetExecutionController` is the authoritative saved-configuration
execution workflow. It owns:

- the exact clean `SavedConfigSnapshot` submitted to the worker;
- validation-only and dataset-generation request startup;
- phase, progress, cooperative cancellation, and explicit force-stop state;
- typed terminal result and failure projections;
- the relationship between a result and the current saved configuration
  baseline; and
- schema-version-1-compatible Run-activity record creation and updates.

Request startup is one synchronous transaction:

```text
reserve request UUID
→ atomically persist initial activity record
→ start the worker with that UUID
```

The initial write completes before worker startup. Progress is reflected live
but persisted no more than four times per second; phase and terminal changes
are written immediately. A later activity-write failure is exposed separately
through `activityPersistenceIssue` and never changes the scientific worker
outcome. Existing schema-version-1 records remain readable because new
projections are additive.

Result identity is compared with the saved baseline path and SHA-256, the
active workspace, and the current on-disk file. Unsaved draft edits do not make
a result historical; a later Save, file replacement, document replacement, or
workspace change can. This distinction prevents mutable editor state from
rewriting the identity of an already executed scientific configuration.

### `InspectionController`

`InspectionController` is the authoritative read-only source-inspection
workflow. It owns:

- direct-child workspace source discovery, bounded disclosure, and
  inspectability feedback;
- the active worker inspection request and exact source revision;
- source-kind-aware identity, backend, row, diagnostic, table, and integrity
  projections;
- three independent dataset failure aggregates for layer, code, and property;
- one typed row per logical array, including distinct shapes and dtypes within
  a shared artifact;
- selected table identity, 500-row worker blocks, and 100-row local pages; and
- the copied inspected plot context consumed temporarily by the Widgets Plot
  page.

Workspace candidates are sorted by `st_mtime_ns` descending with resolved path
as the deterministic tiebreaker, revealed 20 at a time, and never discovered
through recursive traversal or symbolic links. Table row positions shown in
the frontend are one-based presentation positions; source order and worker
payload rows are unchanged.

`carnopy.app.source_inspection` and `carnopy.app.table_preview` are permanent
worker-only modules. They may import pandas, PyArrow, visualization inspection,
and data-reading implementations inside worker request handling.
`InspectionController`, `inspection_models`, `table_model`, Widgets adapters,
and future QML views import none of those modules and never open table or array
bytes. They consume only JSON-compatible worker payloads. The first bounded
preview is queued after an explicit successful inspection because the request
coordinator releases its active session only after delivering the terminal
result.

### `ActivityController`

`ActivityController` is the authoritative read side of private Run activity and
staging recovery. It owns:

- schema-version-1-compatible record loading and stable-role projection;
- record selection, typed summaries, and preformatted raw diagnostics;
- effective `Interrupted` projection for a stored `running` record that has no
  matching live execution session, without rewriting that record;
- deletion of the selected private activity JSON only; and
- recognized direct-child staging discovery, selection, rescan, identity
  revalidation, and removal.

It never starts a request, updates execution records, owns a generated run, or
deletes generated artifacts. `DatasetExecutionController` remains the sole
write-side owner. Recovery removal compares the selected path, device, and inode
with a fresh scan and then uses the filesystem helper's containment, type,
symlink, and identity checks immediately before deletion. A replacement is
reported and retained rather than being adopted as a new deletion target.

`DesktopController` supplies the active workspace once and refreshes Activity
after execution record changes. The temporary Widgets Jobs page is only a view
adapter over this controller; the later QML Activity page will bind the same
models and actions.

### Configured and session plot controllers

`ConfiguredPlotResultsController` is the read-only owner of configured plot
results. Discovery starts from a successful schema-version-1 generation record
loaded by `ActivityController`; it never scans a figure directory or treats
unrecorded files as configured outcomes. For the record's exact report and
ordered outcomes, the lightweight `plot_artifacts` verifier checks:

- workspace containment and absence of symbolic-link path components;
- run, spec, generation-context, source-directory, and visualization identity;
- the ordered canonical request at each outcome position and its unique name;
- report/result counts and each completed outcome's exact sidecar request;
- source dataset path and well-formed recorded SHA-256 identity; and
- image/sidecar pairing, format, and image SHA-256.

The resulting UI label is limited to recorded-provenance consistency; it is not
independent scientific validation. PNG and SVG previews receive opaque tokens
bound to workspace identity, canonical path, expected image hash, format, and
verification revision. The QML image provider resolves only those tokens and
revalidates bytes on each read. PDF is revalidated immediately before an
explicit external open.

Image-plus-sidecar export is a no-overwrite pair operation. It revalidates the
source evidence, stages both destination files in their final directory,
copies the image, and rewrites only the exported `image.path` and
`image.sidecar_path` fields in deterministic sidecar JSON before exclusive
promotion. It does not claim two-file crash atomicity.

`SessionPlotController` owns one inspected-dataset `PlotDraft`, one worker
render session, structured failure state, the last committed request/result,
and its preview token. A successful render revalidates the result and sidecar
before it commits and destroys the temporary draft. Local invalidity focuses a
typed field and row. Worker failures retain the draft and expose their
structured category/code/message; field focus occurs only when a structured
field exists. Cancel returns to the prior committed result. Session edits are
transient, not YAML dirty: they block source/workspace replacement and
shutdown, but do not block unrelated Dataset edits or Save.

Both controllers use `carnopy.visualization.requests` for lightweight canonical
request identity. They do not import visualization configuration/models,
renderers, source inspection, table readers, pandas, PyArrow, NumPy, CoolProp,
or Matplotlib. The temporary Widgets Plot page consumes
`SessionPlotController`; Stage 3 Step 8 will bind these same controllers into
QML.

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
   under its fixed owner. Execution may first reserve a UUID and persist its
   initial activity record; other workflows start directly.
2. The coordinator rejects the request if another request or reservation is
   active, creates an owner-scoped session, and delegates transport to
   `WorkerClient`.
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

Dataset-only searchable fluid and property views are source-ordered Qt proxy
models over those authoritative choice models. They filter existing display,
schema-value, canonical, and label roles without copying or reordering state.
QML applies selection through the desktop facade, while ordered selected-value
models continue to own presentation order, incompatibility issues, and move or
remove operations. The popup is window-overlay content rather than another
scroll container inside the Dataset page.

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
Stage 3 Step 7 extracts configured-result evidence and session-only manual
plotting into authoritative controllers while preserving the worker-only
rendering boundary. Step 8 will expose both workflows through QML Visualization;
Inspect remains the source-selection and table/diagnostic workbench.

The QML YAML Preview page is a read-only projection of the complete document.
It provides line numbers, search, selection/copy, file and dirty-state context,
and typed navigation to the first blocking Dataset or Visualization field. It
does not edit YAML or retain stale text. Command-bar New, Import, Save, Save As,
and Close actions cross the root runtime bridge into `DesktopController`; QML
owns only the consequential decision dialogs and native file selection, not the
underlying workflow.

## Frontends

### Public Qt Widgets frontend

`carnopy.app.window.MainWindow` remains the public frontend during the Stage 3
parity migration.
Widgets pages are adapters over shared controllers for workspace,
configuration, execution, sources, jobs, recovery, plot requests, and image
preview. The Run page now consumes `DatasetExecutionController`; it no longer
starts workers or emits persistence events. The Jobs page consumes
`ActivityController`; it no longer loads JSON, decides interruption state, or
owns staging recovery. The Inspect and generated-source pages project the shared
`InspectionController`; they no longer start inspection or preview sessions,
discover sources, or retain authoritative table state. Widgets retain native
file dialogs and existing manual workflows as a parity oracle until Stage 3.
The Plot page now projects `SessionPlotController`; it no longer owns the
temporary plot draft, worker session, committed result, or artifact evidence.

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
The selected QML palette is applied before the QML engine is constructed so
fallback controls cannot cache the pre-Carnopy application highlight. Native
dialog placement itself remains compositor-owned; the transient parent is the
portable centering and modality contract.
Window close is routed through the composition-owned active-edit, worker-busy,
and dirty-document guards before runtime teardown.

The QML Run page follows that same queued root-signal boundary for Validate,
Generate, Cancel, and Force Stop. It projects the authoritative execution
controller's exact saved snapshot, progress, terminal result, activity
persistence, and saved-baseline relation without parsing worker envelopes.
Successful generation stays on Run. Its future `Inspect Run` and `View Plots`
actions remain visibly unavailable until the exact cross-page actions and
configured-result controller are introduced; QML does not simulate those
workflows.

The QML Inspect workbench consumes only the typed Qt models owned by
`InspectionController`. Workspace discovery is direct-child, symlink-excluding,
newest-first, and revealed 20 entries at a time. Explicit source inspection can
automatically request the first reported table, but never inspects another
source automatically. A virtualized table presents 100-row local pages backed
by bounded 500-row worker blocks, preserves emitted order, and labels positions
one-based. Summary, logical-array, and source-kind diagnostic projections remain
separate; QML never infers correlations among independent failure aggregates or
opens array bytes. Native external file/folder selections are deferred until
their dialog is hidden before crossing the queued root facade, and the facade
normalizes `file:` URLs before inspection. Workspace-source rows are the normal
path for generated outputs; the external actions intentionally accept sources
outside the active workspace.

Run navigation requires the execution controller's exact saved snapshot,
whereas Inspect requires only an active workspace so historical outputs remain
available without a current configuration. Dataset draft validation and Run
saved-snapshot validation are optional diagnostics. Neither authorizes Save or
generation; those operations retain their own fresh worker-authoritative
validation at the existing trust boundaries.

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
Workbench pages are instantiated lazily on first visit and then retained until
runtime teardown. Navigation changes page visibility rather than destroying a
page whose virtualized delegates may still be incubating; this also preserves
local view position and focus state without duplicating controller ownership.
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

Appearance uses one mode string across Python and QML:

```text
system
light
warm
dark
```

Dark is the default for missing or invalid stored state. System resolves live
to Light or Dark without creating another serialized mode. The running QML
window and Qt fallback controls change in the same event turn; the QML runtime
owns that application-palette override and restores the prior `QPalette` during
teardown, so the still-public Widgets launchers do not inherit QML styling.
Warm uses an amber canvas and surface scale that remains visibly distinct from
Light while retaining the same semantic green, warning, and error roles.
The wide header places the first-party sun, sunset, and moon controls on the
inspector side of the continuous dock boundary. Compact and narrow layouts use
the same action contract through the command bar, with a single menu below 800
logical pixels. The custom appearance icons are first-party manifest records;
the navigation icon subset remains separately attributed to Lucide.
Responsive card collections use Qt's native uniform grid sizing. Cards in one
row share height, and shrinkable equal-width Visualization columns remain
inside their owning card at supported layouts.

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
| 2 | Package the Precision Grid QML Workspace, Dataset, Visualization, and YAML/Save workflows | Complete; automated, remote, and native acceptance passed |
| 3 | Migrate remaining GUI-1 workflows, reach parity, switch both launchers to QML, remove Widgets, and qualify `0.1.0a4` | Active |
| 4 | Add controlled sweep and preparation worker operations | Pending |
| 5 | Add structured sweep and preparation QML workflows | Pending |
| 6 | Build exact emitted-value 3D scene contracts | Pending |
| 7 | Integrate native interactive 3D into QML | Pending |
| 8 | Complete native-3D platform, distribution, documentation, and later-release qualification | Pending |

Stage 2 has also established definition-first sampler canonicalization, exact
anchor-based GUI unit changes, Qt 6.11.1 as the QML baseline, packaged QML
resources, responsive settings, trusted workspace flows, structured Dataset
and Visualization editing, typed YAML and operation state, worker-validated
Save flows, practical starter grids, `hPa`/`atm` input units, safe native-window
teardown, reliable responsive shell actions, revision-bound standalone
validation, exact Dataset projections, scientific property presentation, and
the Dark-default Light/Warm/Dark/System QML appearance contract with
runtime-only fallback-control palette synchronization. Dataset fluid and
property selection now uses searchable proxy views over the existing draft
models, bounded ordered summaries, retained incompatible values, and
keyboard-accessible immediate selection without nested scrolling. The
approved scientific-workbench styling now supplies the flat semantic palette,
responsive three-column 1920 and two-column 1440 Dataset layouts, labeled
sampler controls, wide and narrow command treatments, flat divided inspector,
readable selector hover, visibly amber Warm mode, and bounded Visualization
layout. Final responsive containment keeps sampler fields inside their cards
without forcing unrelated card grids to abandon aligned row heights. These
additions do not imply QML parity or public-launcher migration.

Stage 2 acceptance passed on 2026-07-23. The complete local gate covered 785
tests, preflight, environment compatibility, isolated wheel/sdist construction,
Twine, and exact distribution inventories. PR #15 passed its Python, desktop,
security, dependency, distribution, and installed-QML checks, including startup
smokes on Ubuntu, Windows, and macOS. The maintainer accepted the native QML
application on Ubuntu 24.04.4 under WSL2/WSLg with Qt 6.11.1. Those remote
startup smokes and one native Linux acceptance do not claim full Stage 8
platform qualification.

One initial local acceptance-suite process ended in a Qt segmentation fault.
The affected test and the complete 785-test suite subsequently passed in four
consecutive runs, alongside the green remote desktop checks. No deterministic
failure was reproduced. This remains test-harness evidence to watch if it
recurs, not a reason to weaken teardown behavior or add an ungrounded
workaround.

## Known current limitations

- The public desktop experience is still Widgets; the modern QML launcher is a
  private development entry point.
- The QML application can configure and save YAML and can validate or generate
  from the exact saved configuration through the authoritative execution
  controller. It can also explicitly inspect workspace or external dataset,
  sweep, and preparation sources and present their typed summaries, logical
  arrays, diagnostics, and bounded tables. Configured plot results and session
  rendering remain later Stage 3 workflows.
- QML plotting, Activity and Recovery, sweep creation, preparation creation,
  and 3D presentation are not implemented.
- Native folder dialogs and compositor behavior require human acceptance;
  headless tests do not automate them.
- The current WSLg development host can use CPU rendering through Mesa
  llvmpipe, which affects perceived QML scrolling and animation performance.
  A database would not correct that rendering limitation.
- The packaged Carnopy mark is provisional and will be refined through an
  explicit branding decision rather than automatic tracing.

## Maintenance posture and navigation freshness

The temporary source growth during GUI-2 is deliberate but not permanent. QML
views and interaction tests coexist with the Widgets parity oracle until Stage
3. Stage 3 is therefore a deletion gate: after equivalent QML behavior is
verified, remove obsolete Widgets presentation modules, adapters, and
implementation-specific tests rather than preserving two frontends for a
speculative future need. Record the removed files and source/test line delta at
that boundary.

Several desktop files are large because they currently concentrate real
composition, draft, or shell responsibilities. File size alone is not a reason
to add an interface, factory, event bus, generic draft base class, or another
dependency. Before adding code, reuse an existing repository helper, then the
standard library or Qt platform behavior, and otherwise make the smallest
change that preserves scientific, lifecycle, accessibility, and data-safety
contracts. Split a module only when a concrete stable responsibility can move
with focused tests and less coupling. Reassess the QML shell and controller
hotspots after Stage 2 layout stabilization and again after Stage 3 removes the
Widgets overlap. A database, web service, or external project-management plugin
does not solve the current local capability-loading or rendering-performance
constraints and is not justified by the implemented workflow.

The 2026-07-23 maintenance audit records these concrete watchpoints without
turning them into automatic refactors:

| File | Lines | Current reason to watch |
| --- | ---: | --- |
| `qml/Carnopy/Main.qml` | 1,056 | Shell, breakpoint, focus, and application-lifecycle concerns meet here |
| `dataset_draft.py` | 1,075 | Dataset validity, capabilities, sampler ownership, and projections meet here |
| `config_controller.py` | 976 | Document/YAML, worker validation, Save, and replacement orchestration meet here |
| `visualization_draft.py` | 971 | Shared visualization state, compatibility, dirty state, and plot editing meet here |
| `plot_draft.py` | 931 | Plot-kind fields, mappings, compatibility, and validation meet here |
| `desktop_controller.py` | 828 | Cross-controller lifecycle guards and QML facade operations meet here |
| `qml_runtime.py` | 773 | Application startup, resources, palette, window state, and teardown meet here |

Step 19 rechecked this list after the Dataset layout settled and found no
independent refactor required before Stage 3. Stage 3 measures it again after
obsolete Widgets presentation code is deleted. A split is justified only when
it removes a named responsibility from one of these files without creating a
second state owner or weakening a worker boundary.

Use focused checks while a desktop step is being developed. Run the full source,
distribution, and preflight gates at stage or release boundaries, or earlier
when a cross-cutting change warrants them. This keeps verification complete
without repeatedly executing the same repository suite through both a direct
test command and the aggregate preflight wrapper.

Graphify is optional generated navigation, never implementation authority. A
refreshed public graph must record the exact source revision used to build it.
Determine freshness from Git history, not a manually edited counter:

```bash
git log -1 --format=%H -- graphify-out/graph.json
git rev-list --count <graph-source-revision>..HEAD
```

For legacy artifacts without an embedded source revision, use the latest commit
that changed the complete public artifact set (`GRAPH_REPORT.md`, `graph.html`,
and `graph.json`) as a conservative baseline. Apply these rules:

- zero intervening commits: the graph may guide navigation, with source
  verification for exact behavior;
- one through nineteen intervening commits: the graph is navigation-only and
  every conclusion must be checked against current source;
- twenty or more intervening commits, or any completed architecture stage not
  represented in the graph: the graph is hard-stale and must not be queried for
  current architecture or implementation work;
- a hard-stale graph is either refreshed intentionally and atomically or simply
  bypassed in favor of source, tests, and scoped text search.

As audited on 2026-07-23, the public graph's latest artifact commit is
`1d819a3dd639958601115758b0c6032b4596ef92`, 34 commits behind the then-current
Stage 2 branch and older than the packaged QML runtime. It is therefore disabled
as a navigation source for the remaining Stage 2 work. Refreshing after the
Stage 2 QML structure settles is preferable to rebuilding it repeatedly during
layout churn.

GitHub Issues are enabled for `gcalpay/carnopy`; the repository had no open or
closed issues in the 2026-07-23 audit. Create an issue only for reproducible,
durable work with a clear acceptance boundary. Do not convert every lint metric,
large file, temporary migration overlap, or speculative feature into backlog.

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
| Configured plot evidence, preview authorization, and safe pair export | `configured_plot_results_controller`, `plot_artifacts`, and `plot_preview_provider` |
| Inspected-data session plot edit and render lifecycle | `session_plot_controller` |
| Widgets presentation | `window` and the relevant Widgets page/editor |
| QML presentation | `qml/Carnopy/` plus narrow runtime signal wiring |
| QML startup, resources, fonts, and warning policy | `qml_runtime`, `qml_resources`, and the resource manifest |
| Scientific behavior | Existing non-app domain/pipeline module, executed by the worker |

Before editing, inspect the applicable controller, both frontend adapters, its
focused tests, `AGENTS.md`, and the active GUI-2 stage plan. If a change appears
to require scientific code in QML, a second configuration copy, a direct CLI
call, multiple simultaneous workers, or weaker file-integrity checks, stop and
re-evaluate the ownership boundary.
