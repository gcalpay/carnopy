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

The source tree has one desktop presentation implementation:

- `carnopy-gui` launches the QML application and is the canonical desktop
  command;
- `carnopy-app` launches the same QML application as the documented
  `0.1.0a4` compatibility alias;
- `python -m carnopy.app.qml_launcher` remains an internal module-level smoke
  entry;
- the obsolete Qt Widgets presentation modules have been removed after tested
  QML parity and public-launcher migration;
- the QML frontend uses the authoritative QtCore controllers and private worker
  boundary;
- the QML application currently implements the responsive shell, Workspace,
  Dataset, Model Sweep, Visualization, YAML Preview, Run, Inspect, Activity,
  Settings, and Help surfaces, including one global worker-validated
  configuration lifecycle for Dataset, Model Sweep, and Preparation YAML;
- the structured Preparation page and scenario editor are packaged, tested,
  and enabled through the Stage 5 Unit 19B shell integration, including the
  explicit inspected-source prerequisite for new documents;
- typed blocking state, revision-bound standalone validation, operation
  feedback, exact Dataset row projections, and composition-owned document and
  shutdown decisions are shared with the authoritative controllers rather than
  reimplemented in QML;
- Dataset saved-config validation and generation state are owned by one
  `DatasetExecutionController`; the public QML Run workflow is its view;
- revision-bound Sweep and Preparation planning, execution, cancellation,
  protected finalization, Activity persistence, and finalized-result identity
  are owned by focused workflow controllers rather than the configuration
  controller or QML pages;
- source discovery, worker inspection, typed source summaries, logical-array
  metadata, integrity-verified Preparation quality flags, table selection, and
  bounded preview state are owned by one `InspectionController`; the public QML
  Inspect workbench presents those projections together with typed finalized
  Preparation audit evidence;
- private Run-activity loading, typed projection, record-only removal,
  interrupted-state projection, and identity-checked staging recovery are owned
  by one `ActivityController`; the public QML Activity page is its view;
- configured plot-evidence projection is owned by one
  `ConfiguredPlotResultsController`, while inspected-data plot editing and
  rendering are owned by one `SessionPlotController`; the QML Visualization
  page binds both;
- the QML Visualization page exposes record-driven configured outcomes and
  explicit inspected-data session rendering, including verified preview,
  focus, PDF-open, and image-plus-sidecar export actions;
- the QML Activity page, guarded end-to-end cross-page/close parity, public
  launcher migration, and Widgets retirement are implemented.

The release version is `0.1.0a4`. Both public launchers select the
tested QML parity application; Carnopy does not ship two normal desktop
applications or a frontend selector. The resulting QML application is the
planned `0.1.0a4` alpha checkpoint. Later sweep, preparation, and native-3D
stages are not prerequisites for that release. Stage 3 implementation, remote
CI, the complete local gate, and native acceptance passed on 2026-07-30. Its
accepted screenshot and historical implementation index are tracked under
`docs/`, and this document records the accepted Stage 3 architecture.

## Authority map

Use the narrowest applicable authority:

| Source | Authority |
| --- | --- |
| `AGENTS.md` and its routed agent guides | Public scientific, data, architecture, packaging, and contribution contracts |
| `.agents/local.md` | Checkout-local execution, environment, credential, dependency, and Git restrictions |
| `PRODUCT_SCOPE.md` and `.agents/private/PRODUCT_STRATEGY.md`, when present | Maintainer-local product identity, future direction, and cross-roadmap priority |
| `GUI2_PLAN.md` | Temporary GUI-2 scope, sequencing, decisions, and acceptance status |
| `DESKTOP_ARCHITECTURE.md` | Durable implemented desktop structure and evolution |
| `README.md` | Public product summary plus user-facing installation and workflow guidance |

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
   authority. QML edits the shared drafts and deterministic document rather
   than owning a private configuration copy.
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
                     Public QML frontend
                QQmlApplicationEngine + QML views
                             |
                    DesktopController
                   composition and facade
                             |
          +------------------+------------------+
          |                  |                  |
 WorkspaceController   ConfigurationController   QmlSettingsController
          |                  |
          |       DatasetDraft + VisualizationDraft
          |          SweepDraft + PreparationDraft
          |                  |
          +------- DatasetExecutionController
          +------- SweepWorkflowController
          +------- PreparationWorkflowController
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
- `ConfigurationController`, including its `SweepDraft` and
  `PreparationDraft`;
- `DatasetExecutionController`;
- `InspectionController`;
- `SweepWorkflowController`;
- `PreparationWorkflowController`;
- `ActivityController`;
- `ConfiguredPlotResultsController`;
- `SessionPlotController`; and
- the shared verified-plot preview registry.

It binds workspace activation to configuration context exactly once. QML may
edit a child draft through explicit local-edit requests, but workspace changes,
document replacement, mode or coordinate replacement, Save, and shutdown must
pass through composition-level decisions and guards. This prevents a view from
bypassing dirty-state, active-edit, or worker-busy rules.

Cross-page workflow actions are also composition-owned. Run-result and Activity
actions reuse the same helpers for exact-output inspection and exact-generation
configured-result selection. Inspected-data exploration starts only after an
explicit inspection of the requested source succeeds; the view never infers a
source, performs hidden inspection, or starts rendering as a navigation side
effect.

QML enablement is never the lifecycle authority. Every global configuration
lifecycle and worker-start slot on `DesktopController` rechecks transient
editors and global request idleness before delegating. Direct Plan and Execute
requests therefore cannot bypass an open comparison or scenario editor.
Document editing uses one operation-aware Python policy across Dataset, Sweep,
Preparation, and configured Visualization: configuration load, validation,
Save, and workflow planning lock the owning document, while execution permits
ordinary in-memory edits beside its captured immutable snapshot. Owned nested
objects are rechecked at each slot boundary, and a session plot cannot be
mutated while its render worker owns the submitted request. Cancellation and
Force Stop retain their separate active-operation paths.

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

A matching request UUID is necessary but not sufficient for a controller to
adopt a terminal response. Each response-owning controller retains only its
operation-specific semantic context. Configuration requests retain workspace
and document-generation identity plus the applicable document kind, exact YAML
hash, and requested source. Inspection requests retain workspace, source,
inspection revision, table, worker-block offset, and local-page offset.
Workflow requests retain workspace and operation plus the requested source,
captured saved snapshot, and immutable execution plan/source context. A late
success or failure whose context no longer matches is discarded without
replacing newer state. Returned configuration sources and preview block
offsets are also checked against the request. This is deliberately local to the
three owners: the single coordinator remains authoritative, and navigation or
ordinary edits made beside an immutable active execution snapshot do not create
a second identity system or invalidate that execution response.

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

### Sweep and Preparation workflow controllers

`SweepWorkflowController` and `PreparationWorkflowController` consume exact
`SavedConfigSnapshot` values from `ConfigurationController`; they do not own a
second configuration document. Each owns its last accepted plan, active
execution attempt, progress and cancellation state, Activity writes, protected
finalization state, and last finalized result. Typed issue models distinguish
planning and execution blockers, while `planCurrent` and `resultRelation`
compare the exact saved configuration SHA-256 and workflow context. Finalized
results remain inspectable as `current`, `stale`, or `unrelated` when the
global document changes, and a later failed or cancelled attempt does not erase
the prior finalized result.

Planning accepts only a clean saved snapshot of the expected document type.
Execution retains that immutable snapshot and plan context even when ordinary
in-memory editing is allowed during the worker run. The worker recomputes and
verifies the plan before writing. Navigation and QML page lifetime never own or
erase scientific workflow state.

`PreparationWorkflowController` additionally owns one private immutable source
binding containing the resolved source path, inspection revision, accepted
descriptor, and typed preparation profile. Binding copies an explicitly
selected successful inspection; merely inspecting another artifact does not
replace it. Rebinding or clearing is explicit, changes execution context
without dirtying Preparation YAML, and stales a plan only when the semantic
binding differs. Workspace replacement clears the binding, while document
replacement and normal Inspect navigation do not. Planning and execution still
revalidate the bound descriptor and revision in the worker.

### `InspectionController`

`InspectionController` is the authoritative read-only source-inspection
workflow. It owns:

- direct-child workspace source discovery, bounded disclosure, and
  inspectability feedback;
- the active worker inspection request and exact source revision;
- source-kind-aware identity, backend, row, diagnostic, table, and integrity
  projections;
- a private preparation-eligibility descriptor and typed source profile for an
  explicitly inspected immutable dataset run or model-sweep bundle;
- dataset row totals together with the worker-reported column count, without
  opening the table again in the GUI process;
- three independent dataset failure aggregates for layer, code, and property;
- one typed row per logical array, including distinct shapes and dtypes within
  a shared artifact;
- an integrity-verified `quality_flags` table for current Preparation bundles,
  omitted from table control when its optional artifact is missing or corrupt
  while the worker-reported quality error keeps the main bundle inspectable;
- one focused Preparation audit-state object containing fixed typed models for
  quality overview, scenarios, partitions, leakage, duplicate-state and grid
  evidence, matrix diagnostics, correlations, singular values, and baseline
  metrics or failures;
- selected table identity, 500-row worker blocks, and 100-row local pages; and
- the copied inspected plot context consumed by `SessionPlotController`.

Workspace candidates are sorted by `st_mtime_ns` descending with resolved path
as the deterministic tiebreaker, revealed 20 at a time, and never discovered
through recursive traversal or symbolic links. Table row positions shown in
the frontend are one-based presentation positions; source order and worker
payload rows are unchanged. Known generated-directory locators receive a
human-readable mode, UTC timestamp, and short run identity in QML while the
exact path remains the selection authority and accessible description.
External file and folder actions are explicitly secondary and begin in the
active workspace's `outputs/` directory; they can still select an authorized
source outside the workspace.

`carnopy.app.source_inspection` and `carnopy.app.table_preview` are permanent
worker-only modules. They may import pandas, PyArrow, visualization inspection,
and data-reading implementations inside worker request handling.
`InspectionController`, `inspection_models`, `table_model`, and QML views
import none of those modules and never open table or array bytes. They consume
only JSON-compatible worker payloads. The first bounded
preview is queued after an explicit successful inspection because the request
coordinator releases its active session only after delivering the terminal
result.

For current Preparation bundles, private scenario audit evidence is read only
from the canonical contained `data/scenarios/<name>/scenario.json` path after
its recorded hash is verified. The exact bytes must agree with the finalized
scenario name, kind, and partition counts before leakage fields enter the
worker payload. Each resolved scenario audit file identity contributes to the
inspection revision. Missing legacy evidence remains unavailable rather than
being inferred. The controller validates the complete detached audit
projection before replacing any audit models, rejects audit payloads on other
source kinds, and clears those models when inspection becomes stale.

`PreparationAuditView` is the reusable typed presentation boundary for those
models. It does not own inspection state, read raw manifest dictionaries, or
request worker operations. Its quality/scenario, matrix, and baseline sections
use bounded reusable list delegates, preserve the diagnostic context carried by
each fixed role contract, and distinguish unavailable evidence from an empty
recorded result. Unit 21A packages and directly tests the component in
populated, unavailable, wide, and narrow states. Unit 21B integrates it as a
Preparation-only Inspect tab, retains explicit legacy-unavailable and
artifact-issue states, and returns to Summary whenever a selected audit tab no
longer matches the accepted source kind.

The preparation profile projects source kind and revision, available models,
eligible numeric, target, categorical, and auxiliary fields, observed category
values, curated derived-feature readiness, partial-sweep state, reference
contexts, and model-holdout availability. It is derived from verified metadata
and the established preparation field-resolution code in the worker. QML
consumes typed Qt models and never reconstructs preparation semantics from raw
manifest dictionaries. The profile remains an inspection result until the
user explicitly binds its exact snapshot for Preparation.

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
after execution record changes. The QML Activity page is a view over that
controller. Selection and refresh are local presentation operations; exact
Inspect/View navigation and both removal operations cross the queued root
bridge into composition-owned façade slots.
The controller exposes preformatted confirmation paths because Python sequence
wrappers are not treated as JavaScript arrays by QML.

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
revalidates bytes on each read. For QtSvg compatibility it removes empty
Matplotlib glyph definitions and their no-op references from the in-memory SVG
preview only; recorded artifact bytes, hashes, sidecars, and exports remain
unchanged. PDF is revalidated immediately before an explicit external open.

A completed generation remains selectable when it has no configured
visualization report. That state is explicit evidence absence, not an inferred
failure or a directory-scan fallback. The controller exposes the record's exact
output directory so the composition facade can offer **Explore this run**;
inspection must succeed before QML enters the inspected-data plot workflow.

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
shutdown, but do not block unrelated Dataset edits or Save. Native close and
SIGINT surface an explicit **Cancel edit and close** decision instead of
silently ignoring shutdown; accepting it cancels only temporary plot-edit
state and then re-enters the ordinary dirty and busy shutdown guards.
Creating a new session edit does not silently select a scientifically valid
plot request: the user must choose the plot kind and its required fields.
The controller does explicitly seed the edit with every fluid recorded by the
inspected source. Those selections are visible and removable, and a session
render requires at least one remaining fluid; an empty override is never used
as a hidden synonym for all fluids.
Plot-kind help identifies axis, property, series, and color roles, and verified
worker advisories such as a crowded curve family remain visible with the
committed result.
The configured and session workflows remain separate authorities. Configured
plots are YAML state rendered only by a later Generate; session plots are
ad-hoc state over the current inspected source. An explicit configured-row
**Preview with inspected data** action applies that row's inherited configured
defaults to a new session draft, but starts no worker and requires review
followed by Render. Scale advisories report the observed minimum, maximum, and
their ratio and explain the display tradeoff; they never change the selected
scale automatically.

Both controllers use `carnopy.visualization.requests` for lightweight canonical
request identity. They do not import visualization configuration/models,
renderers, source inspection, table readers, pandas, PyArrow, NumPy, CoolProp,
or Matplotlib. The QML Visualization page binds both controllers. Configured
result selection never scans figure directories, and session rendering starts
only from the explicit Render action. PNG and SVG are exposed through opaque,
cache-disabled verified-preview URLs and an in-app focus mode. PDF opens only
after immediate revalidation. Both configured and session exports use the same
no-overwrite image-plus-rewritten-sidecar operation below QML.

Worker-owned sampled-series rendering preserves emitted coordinates and splits
connected lines at observed phase-label changes rather than joining across an
unsampled phase interval. Sidecars report these deliberate transitions as
`phase_break_count` independently from invalid or missing `gap_count`. Dense
numeric curve families use one shared continuous colorbar across fluid facets;
smaller or categorical families retain discrete legends. This presentation is
shared by p–v, T–s, custom X–Y, and property-curve renderers and never adds a
saturation dome, thermodynamic cycle, process path, interpolation, or backend
call. The QML process still receives only the worker-produced artifact and
provenance sidecar.
Property heatmaps continue to render every sampled cell without interpolation.
Hollow valid-sample markers are presentation-only and are omitted above 10,000
samples per fluid facet so their outlines cannot obscure the color mesh;
invalid emitted states retain explicit cross markers and remain counted in the
sidecar.

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

Configuration selection remains explicit because one workspace may contain
multiple YAML documents. The QML open/import dialog starts in the active
workspace's authoritative `configs/` directory; the Workspace page identifies
`configs/` as configuration storage, `outputs/` as immutable generated-run
storage, and `figures/` as rendered-plot storage. External YAML remains
importable through the same worker-authoritative workflow.

Preflight is non-writing. Commit revalidates the plan; existing-directory
operations also recheck device and inode identity after confirmation. The
composition layer runs lifecycle guards before preflight and again before
commit. Recent workspaces are canonical paths stored under the stable Carnopy
application identity.

## Global configuration ownership

`ConfigurationController` owns one globally active Dataset, Model Sweep, or
Preparation document, not a Widget or QML page. It coordinates:

- workspace context and capability discovery;
- kind-specific New, generic Import, document replacement, and close;
- deterministic composition through `DatasetDraft` and `VisualizationDraft`,
  `SweepDraft`, or `PreparationDraft`;
- local validity, dirty state, and YAML preview;
- worker-authoritative import and exact-YAML Save validation;
- Save versus Save As, imported-reformat confirmation, and external-change
  protection;
- atomic workspace-owned replacement and exclusive no-overwrite new writes;
  and
- typed saved execution snapshots.

`ConfigurationDocument` retains the complete typed YAML payload independently
of the structured drafts. Its deterministic serializers preserve the complete
current public Dataset, Model Sweep, and Preparation shapes, including ordered
comparison plots, scenarios, and transformations. `SavedConfigSnapshot`
records the exact workspace-owned path, saved bytes, SHA-256, and document
type, and consumers must request the expected type.

Generic worker import reads one YAML mapping and dispatches directly from the
required, mutually exclusive `document_type` literal. It never determines
meaning by trying the three public schemas in sequence. Imported exact bytes
retain their source hash and do not silently become normalized saved bytes;
the read-only preview shows the deterministic in-memory serialization while
`reformatRequired` keeps the ownership distinction explicit until an accepted
Save.

Workspace initialization itself does not load a backend. After activation,
`ConfigurationController` prepares the configuration editor with a local
`describe_capabilities` worker request. For the current single-backend
milestone, that worker imports the installed CoolProp package, enumerates fluid
names and aliases, and builds the supported model, property, and visualization
choices. It performs no network request. Results are cached only for the life
of the application process. If Carnopy later approves another backend, the
capability request and cache identity must become explicitly backend/model-
aware; the current CoolProp-only path is not a general plugin architecture.

The document is updated only from the locally valid draft for its active kind.
A successful worker validation and file write refreshes the document and draft
baselines; failed validation or writing does not declare the draft saved.

The controller projects `documentKind`, `reformatRequired`, YAML availability,
and its first blocker as typed state: `yamlAvailable`, `blockingSection`,
`blockingField`, `blockingRow`, and `blockingIssue`. Invalid draft state always
exposes an empty YAML preview; the last valid serialization and a best-effort
replacement are never presented as current. Stable field and row identifiers
drive QML navigation without parsing issue prose.

Save and Save As submit the exact visible complete-document YAML to the worker
before any write. Imported-document reformat consent, external-change choices,
in-flight mutation checks, and baseline refresh retain the established Dataset
contract for every document kind. Save atomically replaces only the owned file
after both source-hash checks. Save As uses exclusive creation and refuses a
destination that already exists or appears before promotion. Typed
`operationFailed`, `saveSucceeded`, and `importSucceeded` signals provide QML
feedback.

Standalone worker validation is transient and revision-bound. The controller
captures the document type, exact visible YAML bytes, and SHA-256 and reports
`unavailable`, `blocked`, `not_run`, `running`, `valid`, `invalid`, `failed`, or
`stale`. Edits invalidate the relationship to any prior or in-flight result,
and late results for other bytes are ignored. A `config`/`invalid_config`
response is invalid even when its detailed issue list is empty. This state
never authorizes Save: every Save and Save As starts fresh worker validation
of the exact typed bytes immediately before writing.

### `DatasetDraft` and `SamplerDraft`

`DatasetDraft` owns model, mode, coordinate choice, ordered fluids, properties,
output formats, sampler drafts, compatibility, local validity, structured
first-invalid projection, and its dirty baseline. Its list models are the
single source used by QML.

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

The draft also projects inclusive interval count for valid linear and step-
spaced samplers plus the signed declared-unit `linspace` spacing. These values
are explanatory UI state only: `linspace` still serializes its point count,
`stepspace` still serializes its step field, and neither projection changes the
worker-materialized grid.

Dataset property rows add presentation-only label, symbol, and unit roles over
the existing canonical token. Trusted static symbols deliberately use styled
text for scientific subscripts; user input is never interpreted as markup.
These roles do not alter YAML property names, generated columns, metadata, or
worker behavior.

### `SweepDraft` and `ComparisonPlotDraft`

`SweepDraft` owns the complete current Model Sweep configuration shape:
ordered models and reference model, dataset mode, fluids, samplers, properties,
dataset formats, comparison format, ordered comparison snapshots,
compatibility, validity, and deterministic dirty baselines. It reuses the
lightweight sampler and capability projections; it does not call a backend or
materialize sample grids in the GUI process. Imported selections that are
currently incompatible remain visible and blocking rather than being silently
repaired.

Committed comparison plots are immutable payload snapshots. Exactly one
Python-owned `ComparisonPlotDraft` may be active for Add or Edit, and Commit or
Cancel is explicit. While it exists, Save, validation, planning, execution,
document or workspace replacement, and mutation of the committed comparison
list are guarded in Python. Navigation may hide the page without destroying
the draft. Stable field identifiers and committed row positions support typed
focus without parsing issue text.

### `PreparationDraft` and `ScenarioDraft`

`PreparationDraft` owns the complete current Preparation configuration shape:
numeric and curated derived features, observed or explicit categoricals,
targets, auxiliary fields, partial-sweep policy, outputs, array formats and
dtype, matrix diagnostics, optional baseline diagnostics, and ordered scenario
snapshots. Applying or clearing a bound source profile updates capability and
compatibility projections only; it never rewrites selected YAML state or marks
the document dirty. Imported requests for unavailable optional functionality
remain present with blocking guidance.

Committed scenarios are immutable snapshots covering all eight public kinds
and their partitions, holdouts, strata, numeric bins, and ordered
transformations. One Python-owned `ScenarioDraft` may be active. Kind changes
that would discard incompatible temporary values require an explicit decision,
and Commit or Cancel remains deliberate. The same composition-owned transient
edit guards used for configured plots and comparisons prevent visible but
uncommitted scenario state from entering Save, validation, Plan, Execute,
replacement, or shutdown. The visible Preparation page is a view of these
authoritative objects; correctness does not depend on QML component lifetime.

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
to navigate.

Stage 2 edits configured plot requests but intentionally does not render them.
Stage 3 Steps 7 and 8 extract configured-result evidence and session-only
manual plotting into authoritative controllers, then expose both workflows
through QML Visualization while preserving the worker-only rendering boundary.
Inspect remains the source-selection and table/diagnostic workbench.

The QML YAML Preview page is a read-only projection of the complete document.
It provides line numbers, search, selection/copy, file and dirty-state context,
and typed navigation to the first blocking Dataset, Visualization, Sweep, or
Preparation field. It does not edit YAML or retain stale text. Command-bar New,
generic Open/Import, Save, Save As, and Close actions cross the root runtime
bridge into `DesktopController`; QML owns only the consequential decision
dialogs and native file selection, not the underlying workflow.

## Public QML frontend

`carnopy.app.qml_launcher` is the lightweight public command module. The
canonical `carnopy-gui` entry point calls `main_gui`; the compatibility
`carnopy-app` entry point calls `main_app`. Both load the same packaged
`Carnopy` QML module. Their parser and version handling import no PySide6
module, so help, version, and missing-extra behavior remain available at the
optional-dependency boundary. The module's `main` remains an internal smoke
entry rather than another user-facing application.

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
Installed smoke mode exits immediately when startup is idle. When an initial
workspace starts capability discovery, smoke teardown waits for that request's
terminal coordinator state instead of destroying an active worker process.

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

Busy close is operation-specific. Generation offers cooperative cancellation
and closes only after the coordinator releases the request. Plot rendering may
offer explicit force-stop only through `SessionPlotController` and the
coordinator's parent-owned staging finalizer; a reported cleanup issue aborts
close. Configuration, inspection, and preview operations without a safe
cancellation path remain wait-only. These decisions are enforced in
`DesktopController`; QML presents the decision and cannot bypass it.

The QML Run page follows that same queued root-signal boundary for Validate,
Generate, Cancel, and Force Stop. It projects the authoritative execution
controller's exact saved snapshot, progress, terminal result, activity
persistence, and saved-baseline relation without parsing worker envelopes.
Successful generation stays on Run. **Inspect Run** submits its exact recorded
output directory through the inspection controller. **View Plots** selects its
exact generation request in configured results, including the explicit empty
state when no configured report exists. Neither action renders automatically.

The enabled QML Model Sweep page edits the complete current sweep schema
through `SweepDraft` and the one temporary `ComparisonPlotDraft`. A shared
workflow run panel projects typed blockers, plan evidence, progress,
cancellation, protected finalization, Activity persistence, and current,
stale, or unrelated result state from `SweepWorkflowController`. Opening the
page or editing the draft starts no worker. Plan and Execute consume only the
exact clean saved Model Sweep snapshot, and Inspect Result hands the finalized
output directory to the existing inspection workflow without changing the
active document.

The enabled QML Preparation page presents the bound-source card, all role and
output choices, quality and baseline settings, committed scenario summaries,
the one temporary `ScenarioDraft`, plan evidence, and execution/result state.
Unit 19B connects it to the normal navigation rail, lazy page loader, global
command status, structured workflow context inspector, stable focus routing,
and Workspace creation card. Creating a new document requires the existing
explicit bound source; without one, the Python composition reports the exact
prerequisite and routes to Inspect. Opening an existing Preparation YAML still
routes directly to the editor without inventing a source binding.

Preparation source, document-field, and scenario interactions follow the same
queued root-signal boundary as the established Dataset and Visualization
delegates. Native source binding presents visible text actions and may continue
to the Preparation page; an empty page offers explicit New or source-selection
actions without making navigation itself create or replace a document. Source,
role, category, output, quality-diagnostic, and Scenario controls never mutate
or destroy an active Loader, list model, or conditionally visible settings
section synchronously from the originating input handler. Matrix and baseline
numeric controls retain visible labels independently of their populated values,
and the adjacent Outputs and Quality diagnostics cards remain top-aligned as
either card expands. Native application reinspection confirmed explicit source
binding, Scenario creation, Matrix and Baseline expansion, persistent labels,
and stable card alignment without a presentation-path crash.

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

Dataset, Model Sweep, ML Preparation, Run, Inspect, Visualization, and Activity
navigation require only an active workspace and present their own prerequisite
states. YAML Preview alone requires an open document. This keeps historical
inspection, workflow-result review, and session plotting reachable without
inventing a current configuration. Dataset draft validation and Run
saved-snapshot validation are optional diagnostics. Neither authorizes Save or
generation; those operations retain their own fresh worker-authoritative
validation at the existing trust boundaries.

The QML Visualization page projects both plot controllers without importing or
running rendering code in the GUI process. Configured results start from a
selected persisted generation record and expose only verified report outcomes;
session plots start only after an explicit Render action. Opening the page,
switching its tabs, selecting an outcome, or opening focus mode starts no
worker. Dense numeric series use the shared continuous color scale while every
finite emitted coordinate and deliberate phase break remains unchanged.

The QML Activity page uses the rail label **Activity and Recovery**, the page
heading **Activity**, and separate **Run activity** and **Staging Recovery**
tabs. Record and recovery collections remain stable-role Qt models. The page
shows typed summaries and exposes the raw record only as expandable diagnostic
text. It never scans output or figure directories and never treats an activity
record as artifact ownership. Record selection, refresh, recovery selection,
and recovery refresh cross queued root signals before they touch Python state;
model-backed delegates are never reset or rebound synchronously inside their
own input callbacks. Recovery confirmation lists exact selected paths; the
controller still rescans and identity-checks them before removal.

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
  layout, recent-workspace, and unrelated settings.
- QML preserves the stable application identity and `recent_workspaces` used
  before frontend retirement. Obsolete Widgets `window_geometry` and current
  `qml/window/*` remain separate; no scientific draft or YAML state is stored
  in `QSettings`.
- A clean close records the actual screen and normal client geometry. Tests
  must cover hidden-before-show ordering, obsolete-state migration,
  single-instance rejection, settings isolation, and a clean replacement
  launch after the lock is released.
- A windowed close resolves the monitor from the largest intersection with the
  decorated frame rather than trusting a stale `QWindow.screen()` association.
  A maximized close resolves it from the persisted normal geometry because
  WSLg can report the maximized frame on a different logical screen. The stored
  maximized flag then reopens the hidden window maximized on that monitor.
- With no valid placement state, the normal 1440 by 900 window is centered on
  the operating system's primary logical screen.

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
monitor. The QML launcher also holds a per-user runtime lock so two
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
teardown.
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
| `tests/test_app_*.py` | Controller, draft, QML engine, and interaction contracts |
| `scripts/check_qml.py` | Non-writing QML format, import, and lint checks |
| dedicated Linux app CI job | App-extra typing and desktop tests under Qt offscreen execution |
| installed smoke tests | Both public QML command aliases plus packaged-QML responsive state, YAML-page creation, workflow-page instantiation as each surface is enabled, one controller interaction, teardown, and resource checks |
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
7. architecture boundary review and durable architecture documentation.

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
| 3 | Migrate remaining GUI-1 workflows, reach parity, switch both launchers to QML, remove Widgets, and qualify `0.1.0a4` | Complete |
| 4 | Add controlled sweep and preparation worker operations | Complete |
| 5 | Add structured sweep and preparation QML workflows | In progress through Unit 22B; semantic response and direct-action guards complete, shutdown hardening pending |
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

Stage 3 acceptance passed on 2026-07-30. The QML application now owns the
complete GUI-1 workflow surface through the authoritative QtCore controllers,
both public launchers select it, and the obsolete Widgets presentation is
removed. PR #20 passed its Python matrix, desktop, installed-QML Linux/Windows/
macOS, distribution, dependency, audit, and CodeQL checks; the complete local
Stage 3 gate also passed. Native review accepted Workspace, Dataset, YAML, Run,
Inspect, configured and session Visualization, Activity, Recovery, lifecycle,
theme, and window-state behavior. This is bounded alpha qualification, not the
full native-3D and platform qualification reserved for Stage 8.

Stage 4 acceptance passed on 2026-08-08. The private worker boundary now
supports revision-bound sweep and preparation planning and execution, exact
configuration identities, runtime fingerprints, stable preparation reads,
sticky protected finalization, guarded staging cleanup, and recovery of
force-stopped staging. `DesktopController` composes nonvisual workflow
controllers, while Activity persists executions only and can hand every
finalized inspectable result back to Inspect. Public APIs, YAML schemas,
scientific result models, output layouts, dependencies, and visible QML were
unchanged. The original required implementation gate passed with 820 tests,
preflight, lock, formatting, typing, and dependency checks. A post-acceptance
repair baseline passed with 825 tests. The independent audit remediation passed
the complete gate on 2026-08-09 with 836 tests, adding regressions for stable
metadata consumption, atomic no-replace finalization, cancellation, Activity,
controller state, runtime fingerprints, and all worker lifecycles. Stage 4 has
no native UI acceptance surface; structured editors and visible workflow pages
remain Stage 5. The separate WSLg maintenance acceptance then exercised a real
six-row generation, configured plot, verified inspection, clean workspace
reopen, and workspace-scoped installed smoke. Its lifecycle regression raised
the exhaustively verified suite to 837 tests.

Stage 5 is implemented through Unit 22B on `feat/gui2-stage5`. The former
Dataset-only document and controller now provide one global exact-file
lifecycle for all three public configuration types. The complete structured
Sweep workflow is enabled in QML. Preparation source profiling, explicit
source binding, complete drafts and scenario editing, planning, execution,
Activity, persistent result state, and the packaged editor page are
implemented and enabled through normal shell navigation and guarded Workspace
creation. Finalized quality flags are also available through verified bounded
table inspection. A Qt-independent Preparation audit projection now validates
and flattens finalized scenario, partition, duplicate-state, structured-grid,
matrix, correlation, singular-value, and baseline evidence into exact typed row
contracts. It represents absent values explicitly and never infers leakage from
successful finalization. The worker now supplies the versioned private scenario
details only after containment, recorded-hash, exact-byte, and scenario
identity checks; their file identities contribute to the inspection revision.
Legacy bundles without recorded details remain inspectable with leakage evidence
unavailable. A focused audit-state object owns the fixed list models, and the
inspection controller validates the complete projection before accepting it,
rejects cross-kind audit payloads, and clears the state when inspection becomes
stale. A reusable packaged audit component now presents every fixed model in
quality/scenario, matrix, and baseline sections with bounded lists, contextual
summaries, explicit unavailable states, and responsive card stacking. It is
directly QML-tested and integrated as a Preparation-only Inspect tab. Exact
artifact-level audit issues remain visible beside accepted evidence, legacy
bundles retain an unavailable audit state, and changing away from an accepted
Preparation inspection hides the tab and restores Summary selection.
Operation-specific response contexts now prevent terminal configuration,
inspection, preview, and workflow responses from crossing document, source,
workspace, saved-snapshot, or plan/source-context replacement. Returned load
sources and preview blocks must match their requests. Remaining shutdown and
transition lifecycle hardening, packaged qualification, complete gates, native
acceptance, and completion documentation remain unfinished. Direct desktop
slots now enforce global request idleness, transient-editor focus, document
kind, operation-aware edit locking, owned nested state, and session-render
locking without trusting QML enablement. Unit 22C retains shutdown and the
remaining transition matrix. This checkpoint changes private desktop ownership
and presentation infrastructure only; public scientific and distribution
contracts remain unchanged.

## Known current limitations

- Both public desktop commands launch the single QML presentation.
- The QML application can configure and save YAML and can validate or generate
  from the exact saved configuration through the authoritative execution
  controller. It can also explicitly inspect workspace or external dataset,
  sweep, and preparation sources and present their typed summaries, logical
  arrays, diagnostics, and bounded tables. It also presents configured plot
  evidence, explicit session rendering, private Run activity, and guarded
  staging recovery.
- The visible QML application now provides the complete structured Model Sweep
  and ML Preparation editors and workflows. New Preparation documents require
  an explicitly bound eligible inspection; existing YAML remains portable and
  opens without a source path. Inspect now presents typed finalized Preparation
  audit evidence and explicit unavailable legacy state. Exact emitted-value 3D
  presentation remains a later stage.
- Native folder dialogs and compositor behavior require human acceptance;
  headless tests do not automate them.
- The current WSLg development host can use CPU rendering through Mesa
  llvmpipe, which affects perceived QML scrolling and animation performance.
  A database would not correct that rendering limitation.
- The current WSLg software-rendering, stale-lock, window-activation, and
  workspace-smoke hardening is a separate desktop-maintenance follow-up, not a
  retroactive Stage 4 deliverable. Native XCB/WSLg acceptance passed on
  2026-08-09; it does not broaden Stage 8's cross-platform qualification.
- The packaged Carnopy mark is provisional and will be refined through an
  explicit branding decision rather than automatic tracing.

## Maintenance posture and navigation freshness

The temporary source growth during GUI-2 was deliberate but not permanent.
After equivalent QML behavior and the public launcher migration were verified,
Stage 3 Step 12 removed the obsolete Widgets presentation rather than keeping
two frontends for speculative future use. The deletion removed 14 presentation
modules (3,407 source lines), five implementation-specific test modules (2,487
test lines), and 83 obsolete Widget/duplicate-discovery lines from the retained
source-inspection test. This is historical evidence of the retired overlap,
not a quality metric.

Several desktop files are large because they currently concentrate real
composition, draft, or shell responsibilities. File size alone is not a reason
to add an interface, factory, event bus, generic draft base class, or another
dependency. Before adding code, reuse an existing repository helper, then the
standard library or Qt platform behavior, and otherwise make the smallest
change that preserves scientific, lifecycle, accessibility, and data-safety
contracts. Split a module only when a concrete stable responsibility can move
with focused tests and less coupling. Reassess the QML shell and controller
hotspots at explicit stage checkpoints. A database, web service, or external
project-management plugin does not solve the current local capability-loading
or rendering-performance constraints and is not justified by the implemented
workflow.

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
independent refactor required before Stage 3. Step 12 removed the obsolete
Widgets presentation without introducing another controller layer. A split is
justified only when it removes a named responsibility from one of these files
without creating a second state owner or weakening a worker boundary.

The Stage 5 Unit 19B checkpoint records the new concentration points separately
rather than rewriting that historical audit:

| File | Lines | Stage 5 responsibility to recheck |
| --- | ---: | --- |
| `qml/Carnopy/Main.qml` | 1,597 | Shell integration includes global documents, Sweep, and Preparation |
| `config_controller.py` | 1,218 | One exact file lifecycle with explicit three-kind draft dispatch |
| `desktop_controller.py` | 2,171 | Composition-owned guards and the QML command facade for four structured editors |
| `workflow_controller.py` | 1,312 | Shared plan/result lifecycle plus the Preparation-only source binding |
| `preparation_draft.py` | 1,457 | Complete public Preparation schema, capability projections, and scenario ownership |
| `qml/Carnopy/pages/PreparationPage.qml` | 1,069 | Dense but sectioned enabled editor awaiting native review |

These sizes deserve review during Unit 22 hardening, but they do not by
themselves justify a session manager, event bus, generic editor framework,
second source subsystem, or speculative multidocument support. At this
checkpoint `ConfigurationController` remains limited to document/file
lifecycle, workflow state remains outside it, and nested scenario/comparison
responsibilities already live in focused draft modules.

Use focused checks while a desktop step is being developed. Run the full source,
distribution, and preflight gates at stage or release boundaries, or earlier
when a cross-cutting change warrants them. This keeps verification complete
without repeatedly executing the same repository suite through both a direct
test command and the aggregate preflight wrapper.

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
| Global Dataset/Sweep/Preparation document, validation, Save, and dirty workflow | `carnopy.app.config_controller` and `config_document` |
| Dataset or sampler editable state | `dataset_draft` and `sampler_draft` |
| Model Sweep editable state or temporary comparison | `sweep_draft` and `comparison_plot_draft` |
| Preparation editable state or temporary scenario | `preparation_draft` and `scenario_draft` |
| Sweep/Preparation plans, execution, results, or Preparation binding | `workflow_controller` and `workflow_models` |
| Preparation source eligibility and typed profiles | `source_inspection` and `inspection_controller` |
| Configured visualization or temporary plot state | `visualization_draft`, `plot_draft`, and `mapping_draft` |
| Configured plot evidence, preview authorization, and safe pair export | `configured_plot_results_controller`, `plot_artifacts`, and `plot_preview_provider` |
| Inspected-data session plot edit and render lifecycle | `session_plot_controller` |
| QML presentation | `qml/Carnopy/` plus narrow runtime signal wiring |
| QML startup, resources, fonts, and warning policy | `qml_runtime`, `qml_resources`, and the resource manifest |
| Scientific behavior | Existing non-app domain/pipeline module, executed by the worker |

Before editing, inspect the applicable controller, its QML view and focused
tests, `AGENTS.md`, and the active GUI-2 stage plan. If a change appears
to require scientific code in QML, a second configuration copy, a direct CLI
call, multiple simultaneous workers, or weaker file-integrity checks, stop and
re-evaluate the ownership boundary.
