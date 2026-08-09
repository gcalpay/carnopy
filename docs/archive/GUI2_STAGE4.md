# GUI-2 Stage 4 historical record

GUI-2 Stage 4 is accepted on the development branch. It added controlled,
nonvisual sweep and preparation operations around the existing scientific
contracts without changing public APIs, YAML schemas, result models, output
layouts, dependencies, or visible QML.

## Delivered workflows

- exact-byte configuration loading and structured validation for private sweep
  and preparation worker requests;
- non-writing, revision-bound sweep and preparation planning with canonical
  plan IDs and relevant runtime fingerprints;
- explicit preparation-source eligibility for generated dataset runs and
  model-sweep bundles, with stable descriptor-backed table reads;
- preparation feasibility covering semantic resolution, exclusions, scenarios,
  transformations, leakage checks, matrix diagnostics, array conversion, and
  baseline construction without fitting during planning;
- execution-time plan recomputation, baseline fitting, serialization, hashing,
  source revalidation, and protected atomic finalization;
- cooperative cancellation checkpoints, sticky protected-finalization
  semantics, sweep failure compatibility, guarded staging cleanup, and
  identity-checked recovery; and
- nonvisual sweep and preparation controllers, execution-only Activity records,
  stale-input invalidation, and inspection handoff for finalized outputs.

## Permanent boundaries confirmed

- Structured sweep and preparation editors and visible workflow pages remain
  GUI-2 Stage 5.
- New backends, advanced model families, PyTorch training/export expansion,
  and native 3D remain outside Stage 4.
- The desktop remains a presentation over the private worker protocol; QML
  does not parse worker envelopes or own scientific execution state.

## Verification

The original complete implementation gate passed on 2026-08-08: locked
resolution, Ruff check and format, strict mypy, dependency compatibility,
preflight, and **820 tests**. A post-acceptance repair baseline passed with 825
tests. After an independent audit, the remediation gate passed on 2026-08-09
with **836 tests**, adding explicit coverage for stable metadata consumption,
atomic no-replace finalization, cancellation between artifact writes, Activity
terminal truth, failed-load state, runtime fingerprint invalidation, and the
preparation worker lifecycle. No screenshot or native UI acceptance was
required for Stage 4 because it has no visible QML changes. The separate WSLg
launch-hardening follow-up retains its own manual native-acceptance boundary.

Stage 5 structured sweep and preparation QML workflows are the approved next
stage.
