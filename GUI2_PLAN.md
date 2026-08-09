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
| 5 | Approved next | Add structured sweep and preparation QML workflows |
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
tests. Stage 5 is now the approved next stage.

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
