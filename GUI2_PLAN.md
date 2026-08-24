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

- `0.1.0a5` is the current published alpha release. It contains the accepted Stage 5
  structured Model Sweep and ML Preparation workflows, the custom desktop
  frame, and direct post-generation session plotting.
- `0.1.0a4` is the historical Stage 3 QML-parity release.
- `0.1.0a3` is the historical GUI-1 release and contains the retired Widgets
  presentation.
- `carnopy-gui` is canonical. `carnopy-app` launches the same QML application
  as the compatibility alias introduced for `0.1.0a4`.
- The obsolete Widgets presentation is deleted. Carnopy does not ship a
  frontend selector or two normal desktop applications.
- `0.1.0a5` remains bounded before native 3D; Stages 6–8 are not part of this
  release.
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
| 5 | Complete | Added accepted structured Sweep and Preparation workflows plus typed audit inspection |
| 6 | In progress (Units 1–3; 4A next) | Build exact emitted-value 3D scenes |
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
Stage 5 has added the corresponding structured QML workflows. Their numbers,
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
tests. Stage 5 is complete; its accepted record is indexed in
[`docs/archive/GUI2_STAGE5.md`](docs/archive/GUI2_STAGE5.md).

## Stage 5: sweep and preparation QML workflows

Stage 5 is complete. Its accepted implementation record, exact commit range,
PR reference, verification evidence, native acceptance, and limitations are
indexed in
[`docs/archive/GUI2_STAGE5.md`](docs/archive/GUI2_STAGE5.md). Durable ownership
is recorded in [`DESKTOP_ARCHITECTURE.md`](DESKTOP_ARCHITECTURE.md).

The accepted desktop surface provides:

- one global exact-file Dataset, Model Sweep, or Preparation document with
  deterministic preview, worker-validated Save, external-change protection,
  and typed saved snapshots;
- complete structured Model Sweep and Preparation drafts, including temporary
  comparison and scenario editors that cannot leak into saved or planned work;
- explicit immutable Preparation source binding copied from verified
  inspection, while portable Preparation YAML remains source-independent;
- revision-bound Plan and Execute workflows with cancellation, protected
  finalization, Activity persistence, durable result identity, and exact
  Inspect handoff;
- typed Preparation quality, scenario, matrix, correlation, singular-value,
  and baseline audit inspection; and
- responsive packaged QML surfaces qualified under both installed public
  launchers.

One composition-owned coordinator still admits one short-lived worker request
globally. Configuration, inspection, preview, plan, and execution responses are
adopted only when their request and operation-specific semantic contexts remain
current. QML remains presentation; Python controllers recheck every
consequential action, own temporary-edit and shutdown sequencing, and retain
scientific state independently of page lifetime.

No public YAML schema, CLI command, Python API, scientific algorithm, manifest,
result model, artifact layout, provenance contract, or optional-dependency
boundary changed. The complete local gate passed on 2026-08-16 with both
1,073-test suites, isolated distributions, installed launchers, and exact
inventories. PR #28's Python, desktop, distribution, dependency, audit, CodeQL,
and cross-platform installed-QML checks passed after synchronization with
`main`. The maintainer accepted native functional behavior on 2026-08-17 on
Ubuntu 24.04 under WSL2/WSLg.

The workflows remain scientifically dense. Broader onboarding, progressive
disclosure, action hierarchy, and discoverability are explicitly deferred to a
focused post-Stage-5 UX follow-up; this does not reopen the accepted scientific,
file-integrity, worker, or lifecycle boundaries.

## Stage 6: exact scientific 3D scenes

Stage 6 source profiling supports verified dataset runs, model-sweep child
datasets, and prepared main or scenario-partition tables.

Stage 6 remains incomplete. Units 1–3 now establish the lightweight contracts,
hostile-input boundary, and authoritative source profiles: immutable
source/profile/request models, canonical request identities and limits,
parent-created workspace-session leases, the canonical `scene.json` plus
little-endian `scene.bin` contract, strict adoption and abandoned-lease
verification, immutable scene bindings copied from Inspect, and the private
`profile_scene` worker operation. Geometry, production writing, scene
controllers, pick resolution, and integrated acceptance remain Units 4–8. No
visible QML or native renderer is enabled by this foundation.

Inspect offers scene bindings only for complete run directories, sweep child
datasets, prepared main tables, and prepared scenario partitions. Standalone
CSV/Parquet files, sweep comparison values or deltas, support tables, and
insufficiently evidenced schemas are rejected as scene sources. Profiling
revalidates exact file identities and recorded hashes, classifies semantic
fields and units, computes source-valid finite/missing/range/domain evidence,
and chooses deterministic topology-first defaults. Dataset topology preserves
the recorded materialized SI level order. Prepared rows are joined one-to-one
with provenance and diagnostics by `prepared_row_id`; exclusions are validated
as the disjoint excluded source-row set, and scenario rows and metadata must
agree with the prepared main table. Prepared bundles preserve exact source
coordinates but not original ordered sampler levels, so their topology is
explicitly unavailable rather than inferred.

- Points represent finite emitted rows.
- Wireframe edges connect exact adjacent coordinate levels only within
  compatible fluid, model, phase, and partition contexts.
- Surfaces require exactly two verified source-sampling dimensions, explicit
  structured-grid evidence, and one unambiguous row per coordinate pair.
- A surface cell exists only when all corners exist and share a compatible
  context.
- Missing and invalid rows remain gaps.
- Ambiguous duplicates, incompatible contexts, and unsupported topology block
  affected connectivity explicitly. Non-positive retained scalar values make
  logarithmic presentation unavailable without invalidating exact raw points.
- Picking maps exactly to source-row identity and provenance.
- No backend call, interpolation, smoothing, extrapolation, resampling, or
  silent repair is permitted.

The bounded, hashed scene representation must be reconstructible by the GUI
and bridge without scientific imports in QML.

### Stage 6 delivery checkpoints

The accepted Stage 6 contract retains eight top-level units. Units 1–3 are
complete; Units 4–8 are divided into smaller dependency-ordered checkpoints so
that one review does not combine source projection, topology, serialization,
controller lifecycle, and picking. These checkpoints do not broaden Stage 6 or
change its final acceptance boundary.

A checkpoint should normally contain one scientific or lifecycle concept,
about 300–700 production lines, no more than about 1,200 changed lines in
total, and a focused regression for each distinct contract. These are soft
review ceilings, not correctness targets: split earlier when responsibilities
separate cleanly, and exceed them only when dividing the invariant would make
the implementation less auditable. The verification requirements in
`docs/agent-guides/DEVELOPMENT.md` remain authoritative.

Completed top-level units:

- **Unit 1 — contracts, limits, and canonical requests:** immutable source,
  field, filter, topology, request, identity, capability, limit, and error
  contracts with exact normalization and deterministic hashing.
- **Unit 2 — private lease, binary contract, and verifier:** parent-created
  workspace-session leases, canonical manifest and little-endian binary
  contracts, strict hostile-input verification, and liveness-safe abandoned
  lease cleanup.
- **Unit 3 — source adapters and scene profiling:** verified dataset-run,
  sweep-child, prepared-main, and prepared-partition adapters; exact prepared
  joins; authoritative field and topology profiles; deterministic defaults;
  immutable Inspect bindings; and the private `profile_scene` worker request.

Remaining checkpoints:

- **4A — retained-point projection and exact filters:** revalidate a profiled
  request, apply exact case-sensitive categorical and finite inclusive numeric
  filters, and retain only source-valid rows with finite selected X, Y, Z, and
  optional scalar values. Produce renderer-neutral point records and exact
  retained/excluded reason counts without connectivity.
- **4B — blocks and topology evidence:** partition retained points by every
  required artifact, run, fluid, model, phase, saturation-endpoint, scenario,
  and partition context. Preserve verified materialized topology-level order,
  identify dimensions, gaps, missing intermediate levels, and duplicate
  topology locations, and report explicit zero-dimensional or unsupported
  higher-dimensional outcomes without emitting primitives.
- **4C — exact one-dimensional edges:** connect only immediately adjacent
  verified levels inside one unambiguous block, preserve filtered or invalid
  intermediate levels as gaps, and omit and count exact zero-length edges.
  Prove that no edge crosses a block or ambiguous duplicate.
- **4D — exact two-dimensional cells:** emit adjacent grid edges and one
  ordered quad per complete cell as `[i,j]`, `[i+1,j]`, `[i+1,j+1]`,
  `[i,j+1]`. Omit and count missing-corner, repeated-vertex, exactly
  zero-length, and exactly collinear primitives without triangles,
  tessellation, tolerance, interpolation, or repair.
- **4E — capabilities and geometry limits:** compute representation
  capabilities only when every retained block has a valid primitive and no
  blocking ambiguity. Enforce the accepted point, edge, quad, and projected
  bundle-size limits before serialization, and integrate the complete exact
  geometry fixture matrix.
- **5A — deterministic binary layout and encoding:** plan the accepted float64,
  uint64, and uint32 buffers, absolute aligned offsets, deterministic zero
  padding, block ranges, and hashes without writing a completed lease.
- **5B — canonical manifest and production writer:** serialize binary buffers
  and the canonical manifest deterministically, record exact request, source,
  field, topology, block, gap, degeneracy, capability, and content identities,
  and prove writer/verifier round trips, byte stability, and tamper rejection.
- **5C — `build_scene` worker and adoption:** add projected or chunked reads,
  progress and cooperative-cancellation checkpoints, final source
  revalidation, exclusive creation, manifest-last completion, and parent
  adoption only after complete verification. Failure must retain the previous
  verified scene.
- **6A — `SceneDraft` and copied binding:** add the QtCore-only editable draft,
  explicit immutable binding copied from Inspect, topology-first defaults, and
  explicit Profile and Build/Update commands. Editing, navigation, and
  inspection changes must not start a scene build.
- **6B — `SceneController` state and replacement:** own submitted-draft
  locking, global request participation, progress and cancellation,
  settings-stale and source-stale transitions, verified replacement, and
  retention of the previous scene after failed or cancelled updates.
- **6C — desktop lifecycle integration:** compose the controller without a
  visible 3D page, enforce one global worker, clean leases during replacement,
  workspace changes, startup, and shutdown, and preserve safe force-stop and
  busy-shutdown behavior without Activity or Recovery records.
- **7A — direct and sweep exact picks:** revalidate the scene-level source
  descriptor and revision, then match original row position with stable
  `case_id` for dataset runs and sweep children. Return the exact source row or
  reject changed, missing, duplicated, reordered, or substituted identities.
- **7B — prepared picks and stale integration:** resolve `prepared_row_id`
  against prepared main or partition tables and return its exact row plus
  verified provenance, diagnostics, and scenario or partition context. Any
  failed source revalidation marks the controller source-stale and returns no
  misleading detail.
- **8A — integrated hostile and lifecycle acceptance:** exercise unsupported
  manifest and header versions, magic and endianness errors, every buffer
  alignment, overlap, order, range, type, shape, length, count, and connectivity
  violation, including globally valid cross-block edges and quads. Use real
  subprocesses to prove live-lock preservation and conservative cleanup of
  abandoned, malformed, replaced, symlinked, unrecognized, and apparently live
  leases.
- **8B — complete gate and documentation:** run the locked repository,
  preflight, distribution-inventory, and installed-launcher gates; archive the
  accepted Stage 6 contract; synchronize durable scientific and desktop
  architecture; and mark Stage 6 complete only after maintainer acceptance.

Stage 6 still excludes visible QML 3D, VTK reconstruction, cameras,
authoritative image export, dependency changes, public API, CLI, YAML, or
artifact-schema changes, version bumps, tags, and releases. Stage 7 owns the
interactive renderer and presentation; Stage 8 owns native packaging and
release qualification.

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
