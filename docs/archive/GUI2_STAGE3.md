# GUI-2 Stage 3 historical record

GUI-2 Stage 3 is accepted. It completed desktop workflow parity, made QML the
single public presentation, and removed the temporary Qt Widgets frontend.
This record summarizes the implementation for contributors without keeping the
complete 1,879-line implementation plan in the normal repository reading path.

The durable current architecture is maintained in
[`DESKTOP_ARCHITECTURE.md`](../../DESKTOP_ARCHITECTURE.md). Unfinished GUI-2
work remains in [`GUI2_PLAN.md`](../../GUI2_PLAN.md). Source and tests are
authoritative for exact behavior.

## Delivered workflows

Stage 3 added the QML equivalents of the remaining GUI-1 workflows:

- exact saved-configuration validation and dataset generation;
- progress, cooperative cancellation, explicit force-stop, and typed results;
- bounded source discovery and worker-owned source inspection;
- typed summaries, diagnostics, logical arrays, and paged table previews;
- configured-plot evidence and inspected-data session plotting;
- hash-bound PNG/SVG previews, explicit PDF opening, and safe image/sidecar
  export;
- private Run activity and guarded staging recovery;
- guarded navigation, replacement, busy-close, and transient-edit decisions;
- both public desktop commands launching the same QML application; and
- deletion of the duplicate Widgets presentation after parity passed.

The accepted navigation order is:

```text
Workspace
Dataset
YAML Preview
Run
Inspect
Visualization
Activity and Recovery
```

## Ownership established

`DesktopController` remains the composition and lifecycle authority. Stage 3
added or completed these authoritative controller boundaries:

| Owner | Responsibility |
| --- | --- |
| `DatasetExecutionController` | Exact saved snapshots, validation, generation, progress, cancellation, results, and write-side Run activity |
| `InspectionController` | Source catalog, worker inspection, typed summaries, array metadata, table selection, and bounded preview |
| `ActivityController` | Read-side activity projection/removal and identity-checked staging recovery |
| `ConfiguredPlotResultsController` | Persisted generation selection, report/sidecar verification, ordered outcomes, and configured previews |
| `SessionPlotController` | One inspected-source plot draft, explicit worker render, result, preview, and export |
| verified preview provider | Opaque-token PNG/SVG reads and revalidated PDF opening |

QML remains a view over those owners. It does not parse worker envelopes or
job files, open scientific data, choose arbitrary artifact paths, or infer
lifecycle state from English messages.

## Permanent boundaries confirmed

- A short-lived private worker owns CoolProp, NumPy, pandas, PyArrow,
  Matplotlib, source readers, generation, inspection, and rendering.
- One composition-owned coordinator admits one active request globally.
- Generation validates the exact clean saved bytes immediately before running;
  earlier standalone validation never authorizes it.
- Inspection and plotting bind to exact source revisions and recorded
  identities.
- Configured results are discovered from persisted generation records and
  reports, never by scanning figure directories.
- QML receives opaque verified preview tokens rather than arbitrary file URLs.
- Image-plus-sidecar export revalidates the source pair, refuses overwrite, and
  rewrites only the copied destination paths.
- Configured plot edits are durable YAML state; inspected-data plot edits are
  session-only transient state.
- Public YAML, schemas, emitted rows, scientific identity, provenance, and
  no-overwrite behavior did not change during parity.

## Important implementation lessons

Native acceptance found several defects that are useful regression context:

- QML pages must be instantiated lazily and retained after first use. Replacing
  a `Loader` while delegates were incubating caused destroyed-context warnings.
- Controller/model mutations triggered by delegates cross queued root signals;
  synchronous rebinding inside a click handler caused crashes and missed
  activations.
- Window restoration belongs in the Python runtime before first show. QML and
  Python must not compete to place or maximize the native window.
- Maximized monitor restoration uses persisted normal geometry because WSLg
  can report the decorated maximized frame on another logical screen.
- Native dialogs need a transient parent and completion outside their native
  callback. Carnopy does not replace platform dialogs to control compositor
  placement.
- Dense emitted-state curve families use a continuous color scale instead of
  an unreadable legend, while retaining exact emitted points and phase breaks.
- Dense heatmaps omit redundant hollow valid-sample markers but retain every
  color cell and every invalid-state cross.
- p-v and T-s remain emitted-state diagrams. They do not construct cycles,
  saturation domes, phase envelopes, or missing branches.
- An exact saturation-boundary state may remain an invalid row with its raw
  backend diagnostic; the GUI must not invent a phase.
- New session plots require explicit kind and field choices. An empty fluid
  selection is invalid rather than an implicit hidden request for every fluid.

These are regression explanations, not invitations to restore presentation
logic inside controllers or scientific logic inside QML.

## Frontend retirement

After QML parity and both public launchers passed, Stage 3 removed 14 obsolete
Widgets source modules, five presentation-specific test modules, and the
remaining duplicate source-discovery presentation code. The line reduction is
historical evidence of retired overlap, not a quality metric.

`QApplication`, native `QFileDialog`, and fallback `QMessageBox` use may remain
inside the QML runtime. Widgets retirement means one presentation frontend,
not a prohibition on all QtWidgets runtime classes.

`carnopy-gui` is canonical. `carnopy-app` launches the same QML application as
the documented `0.1.0a4` compatibility alias.

## Verification and accepted capture

Stage 3 passed focused controller/QML/scientific checks, the complete local
gate, PR #20's Python matrix, desktop and distribution checks, installed-QML
smokes on Linux, Windows, and macOS, dependency/security checks, and native
Linux acceptance. This is bounded alpha qualification; full native-3D and
platform qualification remains Stage 8.

The accepted 1920-pixel-wide Dark-mode Dataset capture is tracked at
[`docs/assets/carnopy-dataset-workbench-dark.png`](../assets/carnopy-dataset-workbench-dark.png)
with SHA-256
`51495f3ad520e1479b97581da480eb782d0421961d8faffb88792d18557a2549`.
The visible local workspace path is intentional and contains no secret.

## Full historical recovery

The exact accepted Stage 3 plan, its 13-step implementation ledger, corrective
native-review record, and release boundary remain immutable in Git at the final
implementation revision:

```text
e08067935e8ef3c1c990fb9a7c26ee2d2adafb5e
```

Read it only when investigating a specific Stage 3 decision or regression:

```bash
git show e08067935e8ef3c1c990fb9a7c26ee2d2adafb5e:GUI2_PLAN.md
```

This archive is deliberately outside the mandatory startup-reading route. If a
historical rule still constrains active work, promote it into
`DESKTOP_ARCHITECTURE.md` instead of copying the full completed plan back into
the active context.
