# Carnopy GUI-2: active stages and release boundaries

This temporary document is the implementation source of truth for unfinished
GUI-2 work. Completed implementation detail belongs in Git history and the
short indexes under `docs/archive/`; durable implemented ownership belongs in
[`DESKTOP_ARCHITECTURE.md`](DESKTOP_ARCHITECTURE.md). Keeping completed ledgers
out of this mandatory reading path is an intentional context-budget safeguard.

Delete this plan only after every GUI-2 stage is complete, permanent
documentation describes the final architecture, and the maintainer accepts the
finished application.

## Release and frontend baseline

- `0.1.0a4` is the published baseline and contains the accepted Stage 3 QML
  parity application.
- `0.1.0a3` is the historical GUI-1 release and contains the retired Widgets
  presentation.
- `carnopy-gui` is canonical. `carnopy-app` launches the same QML application
  as a compatibility alias for `0.1.0a4`.
- The obsolete Widgets presentation is deleted. Carnopy does not ship a
  frontend selector or two normal desktop applications.
- `0.1.0a4` is a bounded post-Stage-3 release. It does not wait for sweep and
  preparation QML workflows or native 3D.
- The `app` extra is the cross-platform QML application. A future optional
  `3d` extra may add the native VTK bridge to that application; it is not a
  second GUI.

Stage 3 product implementation, remote CI, the complete local gate, and native
acceptance passed on 2026-07-30. Its accepted implementation record is indexed
in [`docs/archive/GUI2_STAGE3.md`](docs/archive/GUI2_STAGE3.md), and durable
ownership is recorded in [`DESKTOP_ARCHITECTURE.md`](DESKTOP_ARCHITECTURE.md).

## Authority and permanent boundaries

`AGENTS.md`, its routed guides, and `.agents/local.md` control scientific and
public contracts, local authority, dependencies, verification, and release
operations. The README records public direction; maintainer-local
`PRODUCT_SCOPE.md` and `.agents/private/PRODUCT_STRATEGY.md` control private
cross-roadmap priority when present. `DESKTOP_ARCHITECTURE.md` records
implemented desktop ownership. Repository source and tests establish exact
current behavior.

Locked GUI-2 boundaries:

- QML remains the only normal desktop presentation.
- Preserve public CLI and Python APIs, YAML schemas, immutable output layouts,
  provenance, identities, integrity checks, and no-overwrite behavior.
- Preserve one globally active request and one short-lived private worker per
  request.
- Keep CoolProp, NumPy, pandas, PyArrow, Matplotlib, scientific pipelines,
  table readers, and renderers outside the QML process.
- YAML remains portable configuration authority; QML must not create a second
  scientific state owner.
- Worker validation remains authoritative at Save, generation, inspection,
  rendering, and other established trust boundaries.
- Provide emitted-value 3D without interpolation, smoothing, extrapolation,
  resampling, invented states, or silent hole filling.
- Keep the native VTK bridge as a companion distribution in this repository.
- Support QML startup and focused interaction smokes on Linux, Windows, and
  macOS. Native 3D remains Linux-first until separately qualified.
- Deliver one branch and pull request per GUI-2 stage with coherent commits,
  stage-specific verification, documentation synchronization, and explicit
  maintainer acceptance.
- Git mutation, dependencies, credentials, tags, publication, and external
  service configuration remain human-controlled.

Changes to scientific behavior, public interfaces, renderer families,
companion-distribution strategy, or platform promises require explicit review.
Internal grouping may change when source and tests justify a smaller correct
implementation.

## Stage status

| Stage | Status | Durable outcome or active purpose |
| --- | --- | --- |
| 0 | Complete | Qualified the native Qt Quick and VTK bridge feasibility baseline |
| 1 | Complete | Established request ownership and QML-ready dataset controllers |
| 2 | Complete | Added the packaged QML shell and Dataset/YAML/Save workflows |
| 3 | Complete | Reached parity, migrated both launchers, retired Widgets, and qualified `0.1.0a4` |
| 4 | Complete | Added controlled sweep and preparation worker operations for the existing public contracts |
| 5 | In progress | Structured Sweep, Preparation, and typed audit inspection are enabled; lifecycle hardening and qualification remain |
| 6 | Pending | Build exact emitted-value 3D scenes |
| 7 | Pending | Add native interactive 3D to QML |
| 8 | Pending | Qualify native 3D packaging, platforms, and a later release |

## Completed-stage records

### Stage 0: native feasibility

Stage 0 qualified a same-repository `carnopy-vtk-bridge` wheel containing a
`QQuickVTKItem` subtype at commit
`094378ca3fef53de7338f593188d5e14f1461a84`. The Linux Ubuntu 24.04,
CPython 3.12, Qt 6.11.1, VTK 9.6.2, software-OpenGL qualification proved clean
installation, rendering, interaction, resize, reconstruction, teardown, and
process exit. It did not qualify other platforms or future bridge changes.

### Stage 1: request ownership and dataset core

Stage 1 introduced the composition-owned request coordinator, workspace and
configuration controllers, Dataset and Visualization drafts, deterministic
document workflow, and the worker-validated Save boundary. Execution,
inspection, plotting, Activity, and Recovery were deliberately extracted only
immediately before their Stage 3 QML migrations.

### Stage 2: modern QML dataset application

Stage 2 added the packaged Qt 6.11.1 QML runtime, responsive Precision Grid
shell, themes and resources, Workspace, Dataset, configured-Visualization
editing, deterministic YAML preview, worker-validated Save, exact sampler
canonicalization and unit changes, typed projections, and cross-platform
installed-QML smokes. Its historical index is
[`docs/archive/GUI2_STAGE2.md`](docs/archive/GUI2_STAGE2.md).

### Stage 3: QML parity and Widgets retirement

Stage 3 added authoritative Run, Inspect, configured-result, inspected-data
plotting, Activity, Recovery, guarded cross-page workflows, and native QML
acceptance. Both public commands launch QML and the duplicate Widgets frontend
is removed. The durable ownership graph is in `DESKTOP_ARCHITECTURE.md`; the
full implementation ledger is indexed in
[`docs/archive/GUI2_STAGE3.md`](docs/archive/GUI2_STAGE3.md).

The accepted public Dataset capture is:

![Carnopy QML Dataset workbench](https://raw.githubusercontent.com/gcalpay/carnopy/main/docs/assets/carnopy-dataset-workbench-dark.png)

## `0.1.0a4` release checkpoint

The checkpoint completed on 2026-07-30 through:

```text
branch: release/0.1.0a4
PR:     chore(release): publish Carnopy 0.1.0a4
commit: chore(release): prepare 0.1.0a4
```

The release commit aligned `0.1.0a4` across Carnopy source, companion-bridge
metadata and qualification constants, `uv.lock`, tracked citation metadata,
release assertions, and version-specific documentation. The complete source,
package, Twine, installed-distribution, and local release gates passed before
the protected `main` merge. The annotated `v0.1.0a4` tag then passed the
protected publication workflow and produced the byte-identical
[PyPI distributions](https://pypi.org/project/carnopy/0.1.0a4/). The matching
[GitHub prerelease](https://github.com/gcalpay/carnopy/releases/tag/v0.1.0a4)
was archived under the version-specific Zenodo DOI
[`10.5281/zenodo.21709965`](https://doi.org/10.5281/zenodo.21709965).

Do not replace the published distributions or move the release tag.

No Stage 4–8 functionality or native VTK is part of the `0.1.0a4` gate.

At the `0.1.0a4` checkpoint, Stage 4 was the approved next implementation
stage. It began the accepted workflow-depth milestone by exposing the existing
sweep and preparation contracts through controlled worker operations without
changing their public schemas or output layouts. Stage 4 has since completed;
Stage 5 now adds the corresponding structured QML workflows. Their numbers,
dependencies, and reviewed technical content remain unchanged by this
reprioritization.

## Stage 4: sweep and preparation worker operations

Stage 4 is complete. The accepted implementation record is indexed in
[`docs/archive/GUI2_STAGE4.md`](docs/archive/GUI2_STAGE4.md). It adds private
worker operations for sweep and preparation loading, exact-text validation,
non-writing planning, execution, progress, cancellation, protected
finalization, and guarded recovery.

Preparation planning is revision-bound and non-writing. It classifies eligible
sources explicitly, performs stable descriptor-backed reads, computes semantic
resolution, exclusions, scenarios, transformations, leakage checks, matrix
diagnostics, array feasibility, and baseline feasibility without fitting.
Execution recomputes and verifies the plan in its short-lived worker, fits
requested baselines only during execution, and writes only after the plan and
source checks succeed.

The desktop now composes nonvisual sweep and preparation workflow controllers
with execution-only Activity records, stale-input invalidation, and inspection
handoff. Protected finalization is sticky and distinct from ordinary
non-cooperative phases, so the existing force-only plot behavior remains
unchanged. Public APIs, YAML schemas, result models, output layouts,
dependencies, and visible QML are unchanged.

The original complete implementation gate and preflight passed on 2026-08-08
with 820 tests. A post-acceptance repair baseline passed with 825 tests. The
independent Stage 4 audit remediation then passed the complete gate on
2026-08-09 with 836 tests, including stable metadata consumption, atomic
no-replace finalization, cancellation, Activity, controller-state, runtime
fingerprint, and complete worker-lifecycle regressions. No screenshot or native
UI acceptance was required for Stage 4 because it made no visible QML changes.
The separate WSLg launch-hardening follow-up remains desktop maintenance. Its
native XCB/WSLg acceptance passed on 2026-08-09 with a real six-row generation,
configured plot, verified inspection, clean workspace reopen, and a fixed
workspace-scoped smoke lifecycle; exhaustive verification now collects 837
tests. Stage 5 is now in progress on its dedicated feature branch.

## Stage 5: sweep and preparation QML workflows

The sweep workflow covers models, reference-model settings, comparison
options, comparison plots, validation, execution, cancellation, and inspection
handoff.

The preparation workflow covers immutable dataset or sweep sources, numeric
and categorical features, targets, auxiliary and derived fields, current
scenarios and partitions, transformations, canonical Parquet, optional NPY,
NPZ, and SafeTensors outputs, matrix diagnostics, and optional baseline
diagnostics.

Inspection presents manifests, quality flags, exclusions, provenance, leakage
audits, partition summaries, correlations, singular values, rank, conditioning,
and baseline metrics. Missing optional dependencies disable only the affected
feature and provide exact installation guidance.

### Implementation checkpoint: Units 1–21B

Stage 5 is in progress on `feat/gui2-stage5`. The implemented checkpoint keeps
one globally active configuration document while extending its exact-byte,
dirty-state, reformat, external-change, atomic-Save, exclusive-Save-As, and
saved-snapshot contracts across Dataset, Model Sweep, and Preparation YAML.
`ConfigurationController` owns only that shared document lifecycle and the
three focused drafts; workflow planning, execution, Activity, results,
inspection, and Preparation source context remain in their existing focused
controllers. Generic worker loading dispatches directly from the required
`document_type` discriminator rather than parser order.

The structured Model Sweep workflow is enabled in the normal QML shell. It
supports the complete current sweep schema, comparison-plot snapshots and
temporary editing, typed plan and result projections, revision-bound planning,
controlled execution, cancellation, protected finalization, persistent
finalized-result identity, and exact Inspect handoff.

Preparation is implemented through the Unit 19B visible-shell checkpoint:

- inspection derives a private typed preparation profile from verified source
  metadata and established preparation field-resolution logic;
- `PreparationWorkflowController` owns an explicit immutable copy of the
  selected inspection snapshot, so later browsing in Inspect cannot silently
  change the effective preparation source;
- the complete current role, categorical, output, quality, baseline, and
  eight-scenario schema is represented by Python-owned drafts;
- temporary scenario edits survive navigation and cannot leak into Save,
  validation, planning, execution, document replacement, workspace
  replacement, or shutdown;
- preparation planning, execution, cancellation, protected finalization,
  Activity, result relation, and exact Inspect handoff consume the global
  saved document plus the explicit source binding; and
- the packaged `PreparationPage` and scenario editor are available through
  normal navigation, the Workspace source prerequisite, the global command
  lifecycle, and the workflow context inspector.

Unit 19A adds the Python-owned New Preparation lifecycle. The configuration
controller composes the packaged Preparation template through the global
document lifecycle, while the desktop composition requires an explicit bound
source before creation. A missing binding produces an exact prerequisite and
routes to Inspect; direct internal configuration calls cannot bypass that
composition guard. No new QML surface is enabled by 19A.

Unit 19B enables the normal Preparation surface without adding another state
owner. Workspace creation routes an unbound user to Inspect, dirty replacement
uses the global discard decision, Preparation documents open directly in the
structured page, and navigation, command status, focus routing, context state,
and source-change actions bind the existing authoritative controllers. Focused
QML coverage also holds optional ML and analysis controls unavailable under an
app-only capability projection while keeping the page usable.

Unit 20A begins finalized audit exposure without adding presentation state.
Current Preparation `quality_flags` are now an integrity-verified table in the
worker inspection catalog and therefore contribute to the exact inspection
revision and reuse the established 500-row worker blocks and 100-row local
pages. An invalid optional flags artifact remains omitted from table control and
is reported through the existing Preparation quality error instead of making
the main bundle uninspectable.

Unit 20B adds the Qt-independent `PreparationAuditProjection` and its exact
role contracts. It validates and deterministically flattens finalized quality,
scenario and partition, duplicate-state, structured-grid, matrix, correlation,
singular-value, and baseline evidence into detached typed rows. Missing numeric
evidence has explicit availability state, mismatched worker evidence is
rejected, and absent scenario-detail evidence never produces inferred leakage
claims. A versioned private scenario-detail input is defined for the verified
`scenario.json` evidence that Unit 20C will supply; no controller or QML wiring
is part of Unit 20B.

Unit 20C completes the private worker/controller integration. Current scenario
audit artifacts are resolved within the finalized bundle, checked against their
recorded hashes, read as exact bytes, and required to match the manifest's
scenario name, kind, and partition counts before their leakage evidence enters
the private worker payload. Their file identities contribute to the inspection
revision. Legacy bundles without recorded scenario audit artifacts remain
inspectable but expose no leakage evidence. A focused `PreparationAuditModel`
owns the exact section list models, while `InspectionController` validates the
complete projection before accepting the response, rejects audit data attached
to another source kind, and clears audit state when inspection becomes stale.

Unit 21A adds the reusable packaged `PreparationAuditView` without yet changing
normal Inspect navigation. The component consumes only the focused typed audit
object, groups quality/scenario, matrix, and baseline evidence into explicit
sections, uses bounded reusable list delegates for potentially large evidence,
and distinguishes unavailable evidence from an available section with no
findings. It retains scenario, partition, fit, target, model, and source-group
context in visible summaries, stacks its cards at narrow widths, and is directly
instantiated with populated and unavailable projections under the QML warning
capture. This deliberately leaves placement in the Inspect workflow to the
separate Unit 21B integration boundary.

Unit 21B integrates that component as a fifth Inspect tab only while a
Preparation bundle has been successfully accepted. Dataset and Model Sweep
inspections retain their existing four tabs. Current bundles present the typed
quality/scenario, matrix, and baseline evidence plus exact artifact-level audit
issues; legacy bundles retain an explicit unavailable state rather than losing
the audit surface or fabricating evidence. Starting another inspection, a
failed or stale inspection, or accepting a non-Preparation source hides the tab
and returns a selected audit tab to Summary. The page remains responsive at
narrow widths, and QML continues to consume only the controller's typed models.

No public YAML schema, CLI command, Python API, scientific algorithm, manifest,
result model, artifact layout, provenance contract, or dependency boundary has
changed. Focused tests accompany each completed implementation unit; the
complete Stage 5 gate and native acceptance remain pending.

The remaining implementation order after Unit 21B is:

1. Unit 22 hardens cross-workflow lifecycle and semantic response guards.
2. Unit 23 qualifies packaged Stage 5 QML and runs the complete gate.
3. Unit 24 records completion only after automated and manual acceptance.

The Unit 21B commit is the audit-presentation checkpoint for another
normal-application inspection before lifecycle work continues. Lifecycle paths
are inspected after Unit 22, and the final installed application after Unit 23;
acceptance must not be deferred until the documentation-only completion unit.

## Stage 6: exact scientific 3D scenes

Worker-prepared scenes support dataset runs and prepared main or scenario
tables.

- Points represent finite emitted rows.
- Wireframe edges connect exact adjacent coordinate levels only within
  compatible fluid, model, phase, and partition contexts.
- Surfaces require two independent coordinates, explicit structured-grid
  evidence, and one unambiguous row per coordinate pair.
- A surface cell exists only when all corners exist and share a compatible
  context.
- Missing and invalid rows remain gaps.
- Ambiguous duplicates, incompatible contexts, non-positive logarithmic
  domains, and unsupported shapes fail clearly.
- Picking maps exactly to source-row identity and provenance.
- No backend call, interpolation, smoothing, extrapolation, resampling, or
  silent repair is permitted.

The bounded, hashed scene representation must be reconstructible by the GUI
and bridge without scientific imports in QML.

## Stage 7: native interactive 3D

Expand the qualified bridge with render-thread-owned VTK state, scene
reconstruction, rotate, pan, zoom, camera reset, standard views, axes and
units, scalar legends, validated linear and logarithmic presentation, points,
wireframe, surfaces, exact picking, and deterministic teardown.

The QML page selects inspection-backed sources, coordinates, scalar values,
scales, representations, and filters. Unsupported surfaces receive an explicit
explanation rather than an approximation.

Authoritative image export uses a short-lived worker with explicit scene,
camera, dimensions, scalar mapping, and rendering settings. It writes a
guarded no-overwrite PNG and sidecar; live framebuffer capture is not
authoritative.

## Stage 8: native 3D packaging and later-release qualification

The package has one QML GUI with optional capabilities:

- `app` installs the cross-platform QML application without native VTK;
- `3d` adds the native bridge to that application;
- base, `viz`, `ml`, and `analysis` remain isolated.

Two packaging decisions remain open for Stage 8 review:

1. whether `all` remains cross-platform without `3d` or includes `3d` and
   becomes Linux-only;
2. whether native 3D initially supports only CPython 3.12 or requires bridge
   wheels for every Carnopy-supported Python version.

Qualification covers installed QML resources, Linux/Windows/macOS startup,
Linux native build and wheel inspection, rendering, picking, resize, hide/show
reconstruction, teardown, process exit, dependency isolation, optional-feature
errors, security auditing, and non-destructive distribution rehearsal.

The bridge and Carnopy remain separate artifacts. Human configuration is
required before any companion PyPI project, Trusted Publisher, tag, or
publication. Publication order is bridge first and Carnopy second.

## Completion gates

Before each remaining stage PR merges:

- run focused and complete gates appropriate to that stage;
- complete its recorded native/manual acceptance;
- resolve concrete high- and medium-severity findings;
- synchronize active and durable documentation; and
- mark the stage complete only after explicit maintainer acceptance.

Before final GUI-2 completion, run complete source, distribution, installed-
profile, cross-platform QML, Linux-native, and manual workflow qualification;
obtain an independent explicitly configured review; refresh permanent
documentation from the final architecture; and delete this plan.

Manim, PyMC, SINDy, optimization, ORC/TFC workflows, mixtures, training
infrastructure, deployment, additional backends, and standalone installers
remain outside the current GUI-2 milestone unless separately approved.
