# GUI-2 Stage 5 historical record

GUI-2 Stage 5 is accepted. It exposes Carnopy's complete existing Model Sweep
and ML Preparation contracts through the QML desktop while preserving the
Stage 4 worker, planning, execution, cancellation, Activity, recovery, and
source-integrity boundaries.

The durable current architecture is maintained in
[`DESKTOP_ARCHITECTURE.md`](../../DESKTOP_ARCHITECTURE.md). Unfinished GUI-2
work remains in [`GUI2_PLAN.md`](../../GUI2_PLAN.md). Source and tests remain
authoritative for exact behavior.

## Delivered workflows

- one global exact-file configuration lifecycle for Dataset, Model Sweep, and
  Preparation YAML, including deterministic preview, exact saved snapshots,
  explicit reformat state, external-change protection, atomic Save, and
  exclusive no-overwrite Save As;
- discriminator-based generic configuration loading and validation without
  schema-order guessing;
- complete structured Model Sweep editing, including models, reference model,
  every current dataset mode and sampler shape, outputs, ordered comparison
  plots, compatibility feedback, and temporary comparison editing;
- complete structured Preparation editing, including roles, observed and
  explicit categoricals, outputs, optional dependencies, quality and baseline
  settings, all eight scenario kinds, ordered transformations, and temporary
  scenario editing;
- explicit immutable Preparation source binding copied from a verified
  inspection, so browsing another artifact cannot silently change scientific
  execution context or rewrite portable Preparation YAML;
- revision-bound Plan and Execute workflows with typed blockers, cancellation,
  protected finalization, Activity persistence, persistent current/stale/
  unrelated result state, and exact Inspect handoff;
- integrity-verified Preparation quality-flag tables and typed audit
  projections for scenario, partition, leakage, duplicate-state, structured-
  grid, matrix, correlation, singular-value, and baseline evidence; and
- packaged responsive Sweep, Preparation, workflow, and audit QML surfaces
  under both installed public launchers, with exact source, wheel, and sdist
  inventories.

## Ownership and lifecycle boundaries

`ConfigurationController` owns only the active document and exact file
lifecycle. `SweepDraft`, `ComparisonPlotDraft`, `PreparationDraft`, and
`ScenarioDraft` own structured editing. Focused workflow controllers own plans,
executions, Activity, results, and the private Preparation binding. Inspect
remains the worker-authoritative browsing and verification surface.

One composition-owned request coordinator still admits one short-lived worker
request globally. Matching request IDs are supplemented by operation-specific
semantic contexts so obsolete configuration, inspection, preview, plan, and
execution responses cannot replace newer state. QML remains presentation: all
direct lifecycle and worker-start slots recheck request ownership, document
kind, temporary editors, and operation-aware edit policy in Python.

Temporary comparison and scenario edits are never committed implicitly. They
survive navigation, block Save, validation, Plan, Execute, document/workspace
replacement, and shutdown until explicitly committed or cancelled. Shutdown
decisions are bound to the exact worker, temporary edit, and document revision
presented to the user; protected finalization remains wait-only.

## Public-contract boundary

Stage 5 did not change public YAML schemas, CLI commands, Python APIs,
scientific algorithms, manifests, result models, artifact layouts, provenance
contracts, or optional-dependency boundaries. Preparation YAML remains
source-independent. Scientific validation, source access, planning, execution,
serialization, and finalization remain worker-authoritative.

## Implementation and review record

The Stage 5 implementation is the contiguous feature-branch sequence from
`cb71aaf99f048eb37650aa40be4cbf6d68d4cd85` through
`e25003ef523faf9f184ef32c630d272ce753b271`, synchronized with the then-current
`main` at `f1bf235943fc2ec8e072ab1ba81168b9c7bb2696`. The Stage 5 integration is
[PR #28](https://github.com/gcalpay/carnopy/pull/28). Git history preserves the
incremental configuration, Sweep, Preparation, audit, lifecycle-hardening, and
packaging units together with their focused tests.

## Verification and acceptance

Unit 23B passed the complete locked local gate on 2026-08-16. Both the direct
and preflight-owned suites passed **1,073 tests**. Lock consistency, Ruff,
formatting across 224 files, strict mypy across 139 source files, compatibility
across 70 installed packages, isolated wheel/sdist construction, Twine, exact
distribution inspection, and both installed public-launcher smokes also
passed.

After synchronization with `main`, PR #28 passed its Python 3.11–3.14 matrix,
quality, desktop, installed-QML Ubuntu/Windows/macOS smokes, distribution,
dependency-review, dependency-audit, and CodeQL checks in
[GitHub Actions run 31977406709](https://github.com/gcalpay/carnopy/actions/runs/31977406709)
and its companion security workflows.

The maintainer completed final native functional acceptance on 2026-08-17 on
Ubuntu 24.04 under WSL2/WSLg. The accepted review covered the global document
workflow, structured Sweep and Preparation editing, explicit source binding,
scenario and diagnostic controls, Plan and Execute, finalized result review,
Preparation audit inspection, and repaired queued-interaction paths. Earlier
native review found and fixed empty text-only actions, synchronous QML model/
Loader mutation crashes, unlabeled diagnostic fields, misaligned cards, and
direct workflow-panel re-entry before completion was accepted.

This remains bounded native Linux/WSLg acceptance plus cross-platform startup
smoke coverage, not the broad native-platform qualification reserved for GUI-2
Stage 8.

## Accepted limitation and follow-up

The complete workflows are functional but scientifically dense. The maintainer
accepted Stage 5 with broader onboarding, action hierarchy, progressive
disclosure, and workflow discoverability explicitly deferred to a focused UX
follow-up after merge. That follow-up may improve presentation and guidance but
must not create another document, source, planning, or scientific state owner.

Exact emitted-value 3D scene contracts remain Stage 6; native interactive 3D
remains Stage 7; broad native-3D packaging and platform qualification remain
Stage 8.
