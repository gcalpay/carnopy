# GUI-2 Stage 2 historical record

GUI-2 Stage 2 is complete. It introduced the packaged private QML runtime,
responsive scientific workbench shell, Workspace, Dataset, configured-
Visualization editing, deterministic YAML preview, worker-validated Save and
Save As, exact sampler unit changes, revision-bound validation, Dataset row
projections, searchable selectors, installed-resource verification, and the
accepted Stage 2 visual system.

The implemented architecture and permanent boundaries are maintained in
[`DESKTOP_ARCHITECTURE.md`](../../DESKTOP_ARCHITECTURE.md). Current and future
GUI-2 work remains in [`GUI2_PLAN.md`](../../GUI2_PLAN.md). Source and tests are
authoritative for exact behavior.

The complete accepted Stage 2 plan, its 19-step implementation ledger,
verification record, and transition into Stage 3 remain immutable in Git at
merged Stage 2 revision:

```text
e3550b244d2ac05d0a33cb37875c98c0cb49c7c5
```

Read the historical section only when investigating a Stage 2 decision or
regression:

```bash
git show e3550b244d2ac05d0a33cb37875c98c0cb49c7c5:GUI2_PLAN.md
```

The approved visual reference remains tracked at
[`docs/assets/gui2-stage2-dataset-dark.png`](../assets/gui2-stage2-dataset-dark.png)
with SHA-256
`d6b0ed719218be659ad5d2b940f1f11eab61802d641b4896dee9b96084ad8d48`.

This archive is deliberately not part of the mandatory startup-reading route.
Completed-stage implementation detail must not consume every active Stage 3
working context. Do not copy historical contracts back into the active plan;
promote a still-permanent rule into `DESKTOP_ARCHITECTURE.md` instead.
