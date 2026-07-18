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
workflow. Small fixes remain discoverable through tests and Git history.

## Current state

The desktop has two frontend implementations during the GUI-2 migration:

- `carnopy-app` and `carnopy-gui` still launch the completed Qt Widgets
  application from the `0.1.0a3` line;
- `python -m carnopy.app.qml_launcher` launches the private GUI-2 QML
  application used for development and qualification;
- both frontends reuse the same authoritative QtCore controllers and private
  worker boundary;
- the QML application currently implements the responsive shell, Workspace,
  Dataset, Settings, and Help surfaces;
- QML Visualization editing, YAML availability and validated Save flows are
  the remaining Stage 2 application slices;
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

The document is updated only from locally valid dataset and visualization
state. A successful worker validation and file write refreshes baselines;
failed validation or writing does not declare the draft saved.

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

### `VisualizationDraft` and `PlotDraft`

`VisualizationDraft` owns configured-visualization enabled state, shared
format, fluids, filters, display units, ordered durable plot snapshots,
compatibility, validity, and canonical/raw baselines. Disabled visualization
retains latent settings but emits no visualization payload.

Stored plot rows are snapshots, not persistent `PlotDraft` instances. Exactly
one temporary workflow-local `PlotDraft` may exist for Add or Edit. It must be
committed or cancelled explicitly; it is transient unresolved state rather
than durable configuration dirtiness. Dataset-context replacement and other
cross-controller operations therefore require composition-owned active-edit
guards. The QML Visualization surface and the complete guard projection are
the next Stage 2 implementation slice.

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
event loop advances.

### Responsive shell and settings

The approved Precision Grid shell is desktop-first and uses logical pixels:

- wide: at least 1280;
- compact: 800 through 1279;
- narrow: below 800.

Card columns depend on available central width with a 300-pixel minimum and a
maximum of three. The navigation rail and context inspector have persisted
wide-layout preferences; compact and narrow overrides do not overwrite them.
Window restoration clamps the full decorated frame to an available screen and
prefers the monitor on which the window was last closed.

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
```

The shell bundles IBM Plex Sans and Mono, a hashed subset of Lucide SVG icons,
their licenses, and a provisional raster Carnopy mark. The machine-readable
resource manifest records provenance and hashes; distribution checks compare
source and installed resources.

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

Desktop verification is layered:

| Surface | Purpose |
| --- | --- |
| `tests/test_app_*.py` | Controller, draft, Widgets, QML engine, and interaction contracts |
| `scripts/check_qml.py` | Non-writing QML format, import, and lint checks |
| dedicated Linux app CI job | App-extra typing and desktop tests under Qt offscreen execution |
| installed smoke tests | Public Widgets launchers plus private packaged-QML startup and resource checks |
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
| 2 | Package the Precision Grid QML Workspace, Dataset, Visualization, and YAML/Save workflows | Active; Workspace and Dataset implemented, Visualization and YAML/Save pending |
| 3 | Migrate remaining GUI-1 workflows, reach parity, switch both launchers to QML, and remove Widgets | Pending |
| 4 | Add controlled sweep and preparation worker operations | Pending |
| 5 | Add structured sweep and preparation QML workflows | Pending |
| 6 | Build exact emitted-value 3D scene contracts | Pending |
| 7 | Integrate native interactive 3D into QML | Pending |
| 8 | Complete platform, distribution, documentation, and release qualification | Pending |

Stage 2 has also established definition-first sampler canonicalization, exact
anchor-based GUI unit changes, Qt 6.11.1 as the QML baseline, packaged QML
resources, responsive settings, trusted workspace flows, structured Dataset
editing, practical starter grids, and `hPa`/`atm` input units. These additions
do not imply QML parity or public-launcher migration.

## Known current limitations

- The public desktop experience is still Widgets; the modern QML launcher is a
  private development entry point.
- The QML application cannot yet edit configured visualization or expose the
  final YAML/validated Save flows.
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
