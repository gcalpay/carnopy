# Carnopy contributor and coding-agent guide

## Authority and local instructions

This file applies to the repository root and all subdirectories unless a more
specific nested `AGENTS.md` exists.

Before inspecting, testing, or changing the repository, check this exact
repository-relative path:

```text
<repository-root>/.agents/local.md
```

If that file exists, read it in full before taking any other action. It is the
highest-priority repository instruction for local paths, environment selection,
allowed commands, Git authority, dependency operations, credentials, and
publication boundaries. Do not infer permission from this public file when the
local file is more restrictive.

The tracked `AGENTS.md` remains authoritative for public scientific behavior,
schemas, compatibility contracts, architecture, and contribution standards.
Local instructions may narrow operational authority but must not silently alter
those public contracts.

Canonical names:

```text
Project: Carnopy
Repository: carnopy
Distribution: carnopy
Import package: carnopy
CLI: carnopy
```

CoolProp is the first backend dependency, not the project identity.

Before starting an implementation stage, inspect the worktree and follow the
stage-boundary rules in `.agents/local.md` when unrelated or uncommitted work is
present. Preserve unrelated changes. Git mutation remains human-owned unless a
local instruction explicitly grants narrower authority. Follow the local file
for dependency, credential, external-configuration, and publication authority.

## Codex delegation policy

Delegate only bounded, independent work where parallelism materially improves
quality or speed. The only project agents that may be delegated to are the
explicit definitions under `.codex/agents/`: `explorer`, `worker`, `reviewer`,
and `architect`. The project `explorer` and `worker` intentionally override the
built-in roles with the same names.

Every active project agent must pin its model, reasoning effort, and sandbox.
GPT-5.4, GPT-5.4-mini, Terra, automatic model selection, and automatic review
are forbidden. Do not add or use another project role without maintainer
review. Parent-model preferences, exact-selection failures, and observable
fallback handling belong in `.agents/local.md`.

The reviewed project-agent assignments are:

| Role | Purpose | Sandbox | Model | Effort | Typical tier |
| --- | --- | --- | --- | --- | --- |
| `explorer` | Focused codebase lookup and evidence collection | `read-only` | GPT-5.6 Luna | High | Easiest read-only |
| `worker` | Bounded, already-designed implementation | `workspace-write` | GPT-5.6 Luna | Max | Easy write |
| `reviewer` | Correctness, regression, security, and scientific review | `read-only` | GPT-5.6 Sol | XHigh | Hard read-only |
| `architect` | Difficult architecture, native, scientific, numerical, and release decisions | `read-only` | GPT-5.6 Sol | Max | Most difficult |

These are exact pins, not minimums. Approved parent-only intermediate tiers
remain in `.agents/local.md`; do not override a project role's pin to reach
them. A stuck agent reports the limitation to the parent; it does not alter its
own model or reasoning effort.

Dispatch project agents only through Codex's native custom-agent path. Before
spawning, verify that the callable spawn operation exposes an `agent_type`
argument, pass exactly one of `explorer`, `worker`, `reviewer`, or `architect`,
and require the spawned thread or native agent UI to report a display nickname
from that role's `nickname_candidates`. The stable `name` in each TOML is the
role selector; its nickname is presentation-only. A `task_name` is only a
canonical thread-path label and is never a role selector or display nickname.
A free-form task name, matching label, or prompt that says to act as one of
these roles is not evidence that its TOML profile was loaded.

Do not substitute a generic collaboration wrapper when `agent_type`, an
inspectable native subagent thread, the Subagents/background-agent UI, or the
native `close_agent` operation is unavailable. Continue in the parent thread
instead. Codex chooses unused nickname candidates without a guaranteed order;
do not predict the next nickname or treat a historical Done-row label as proof
that a custom profile was loaded.

Subagent use does not require Ultra, and Ultra is not approved for this project.
Delegation depth is one, so delegated agents must not spawn descendants. Close
every spawned agent through `close_agent` immediately after its result is
integrated or discarded, including agents already marked completed.
`interrupt_agent` stops a turn but leaves its thread open, so it is never a
substitute for `close_agent`. If the active surface does not provide the
required lifecycle operation, do not spawn project agents from that surface.

## Purpose and scope

Carnopy generates reproducible, backend-derived synthetic thermophysical
datasets for machine-learning, surrogate-model, and engineering workflows.

Carnopy is not:

- a thermodynamic property model;
- experimental data or backend-independent ground truth;
- a process simulator;
- a machine-learning training framework.

The core workflow is:

```text
sampling specification
→ backend calls
→ validation and stable diagnostics
→ stable tabular schema
→ CSV/Parquet
→ metadata and report
→ optional visualization of emitted columns
```

Milestone 1 supports:

- CoolProp only;
- pure fluids only;
- YAML schema version 2;
- explicit CoolProp model selection: `heos`, `pr`, or `srk`;
- `property_table`;
- `saturation_table`;
- `vapor_mass_fraction_table`;
- deterministic sampling;
- selectable CSV and/or Parquet dataset output;
- metadata and report JSON;
- optional Matplotlib property curves, sampled heatmaps, x-y plots, and p-v/T-s
  diagrams;
- configured post-generation visualization;
- model-sweep bundles comparing emitted values from multiple CoolProp models.

The `0.1.0a3` release line adds a Linux-first PySide6 desktop frontend for
the existing dataset workflow. The desktop application is a presentation
frontend, not a new scientific execution layer. GUI-1 includes the worker
protocol, optional desktop shell, workspace lifecycle, worker-validated dataset
configuration editor, saved-config execution, workspace-local job diagnostics,
guarded staging recovery, read-only output/bundle inspection, bounded table
previews, inspection-driven session plot requests, private worker rendering,
guarded no-overwrite image/sidecar promotion, desktop Render controls,
immediate confirmed force-stop, Qt-only PNG/SVG previews, and explicit PDF
opening.

[GUI2_PLAN.md](GUI2_PLAN.md) is the temporary source of truth for the active
GUI-2 migration. Read it before changing desktop controllers, QML, native 3D,
desktop packaging, or Widgets retirement. Delete it only after GUI-2 is complete
and permanent documentation and Graphify outputs describe the final design.

Out of scope for now:

- mixtures;
- ORC generation;
- additional property backends;
- random, Sobol, Latin-hypercube, adaptive, or active-learning sampling;
- ML training or inference;
- web/API services or databases;
- ThermoML, OCR, RAG, or literature mining.

Do not broaden scope without maintainer approval.

## Development workflow

Use the project-local environment and locked uv workflow described by local
instructions. `pyproject.toml` and `uv.lock` are authoritative; do not recreate
requirements files.

Normal synchronization:

```bash
uv sync --locked --extra all --group dev
```

Release tooling:

```bash
uv sync --locked --extra all --group dev --group release
```

Required quality gate:

```bash
uv lock --check
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src/carnopy
uv run --locked pytest
uv run --locked python scripts/preflight.py
uv pip check --python .venv/bin/python
```

Maintainers can run the complete source, package, Twine, and distribution
inspection gate with:

```bash
bash scripts/local_gate.sh prerelease/local-gate
```

GitHub verification keeps core and desktop dependencies separate. General
quality and Python-matrix jobs do not install the `app` extra or Qt runtime
packages; the dedicated Linux app job owns desktop typing and tests. Pull
requests also receive dependency review and CodeQL analysis. Scheduled
workflows audit locked dependency profiles and exercise the core package on
Linux, Windows, and macOS.

If a required command or dependency is unavailable, preserve the exact failure
and ask before installing, upgrading, or substituting anything.

Use:

- `rg` for searches;
- `graphify query` for broad architecture, dependency, or codebase-navigation
  questions when `graphify-out/graph.json` exists;
- `apply_patch` for repository file edits;
- temporary directories for generated test artifacts;
- focused tests for every behavior change.

Graphify is optional local analysis tooling. When `graphify-out/graph.json`
exists, prefer scoped graph queries such as:

```bash
graphify query "how does preparation resolve semantic fields?" --graph graphify-out/graph.json
```

Use the graph to narrow the search space before broad `rg` or repeated file
reads. For exact implementation changes, verify against the source files before
editing. Commit only the public graph artifacts when intentionally refreshing
the graph:

```text
graphify-out/GRAPH_REPORT.md
graphify-out/graph.html
graphify-out/graph.json
```

Do not commit Graphify cache, interpreter, manifest, cost, or `.graphify_*`
intermediate files.

Avoid:

- monolithic modules;
- speculative frameworks;
- heavy imports and side effects at module import time;
- brittle golden thermodynamic datasets;
- pixel-perfect figure tests.

Test count is not a target. Prefer a focused regression for each distinct
contract or failure mode, use parametrization where cases share behavior, and
remove redundant tests. The suite can still contain many tests because
configuration, scientific modes, provenance, visualization, CLI behavior,
packaging, and release tooling are separate public contracts.

Root and subcommand help must not import CoolProp, NumPy, pandas, PyArrow, or
Matplotlib.

## Public interfaces

The public CLI is:

```text
carnopy --version
carnopy init MODE OUTPUT [--create-parents] [--full]
carnopy properties
carnopy fluids [--model heos|pr|srk]
carnopy validate CONFIG.yaml
carnopy generate CONFIG.yaml [--out PATH] [--figures-out PATH]
carnopy sweep SWEEP.yaml [--out PATH]
carnopy prepare SOURCE --config PREPARATION.yaml [--out PATH]
carnopy inspect SOURCE
carnopy plot SOURCE ...
carnopy-app [--workspace PATH] [--version]
carnopy-gui [--workspace PATH] [--version]
```

The documented workflow is:

```text
init → edit → optional validate → generate/sweep → inspect → optional plot → optional prepare
```

Commands remain independently scriptable; do not add implicit chaining.

The supported Python API intentionally remains narrow:

- `load_config`;
- `validate_config`;
- `generate_dataset`;
- `generate_model_sweep`;
- `prepare_dataset`;
- public configuration and result models;
- explicit visualization functions.

Keep CLI handlers thin and scientific logic outside `cli.py`.

The desktop frontend follows the same boundary. Qt widgets must communicate
with one short-lived worker process through the private, versioned JSON Lines
protocol under `carnopy.app`; they must not invoke or parse the public CLI.
Only the worker may import CoolProp, generation pipelines, pandas, PyArrow, or
Matplotlib. Progress and cooperative cancellation use private execution hooks;
do not add these hooks to the public Python API.

Manual desktop plots must use the inspected dataset source and its integrity
revision. The GUI supplies a session-only public-shaped request; the worker
revalidates the source, renders through existing visualization code, and never
calls a thermodynamic backend. Plot images and sidecars belong under a
worker-derived direct child of the workspace figure root. Parent-side cleanup
must trust only verified staging leases, manifests, and inode identities.

## Configuration and sampling contracts

Every configuration contains:

```yaml
schema_version: 2
document_type: dataset
backend:
  name: coolprop
  model: heos
mode: property_table
fluids: [...]
grid: ...
properties: [...]
```

Schema version 1 inputs fail with migration guidance. Existing generated run
directories remain readable.

The selected model is part of normalized scientific identity and must appear in
rows, metadata, and reports. HEOS is not experimental truth. PR and SRK are
alternative cubic model assumptions and do not provide Carnopy transport
properties, surface tension, or a usable triple-point temperature. Reject
globally unsupported properties during configuration validation; preserve
state-dependent failures as row diagnostics.

Optional `outputs:` and `visualization:` sections are allowed. Dataset format
selection affects artifact-generation context but not scientific `spec_id`.
Visualization must not affect scientific or artifact-generation identity.

Model-sweep configurations use:

```yaml
schema_version: 2
document_type: model_sweep
backend:
  name: coolprop
  models: [heos, pr, srk]
  reference_model: heos
```

Sweeps produce child dataset runs and comparison Parquet files. Comparison
alignment uses deterministic state keys from normalized sample indices, not
backend-computed floating-point coordinates. Comparison plots are explicit
sweep-level `property_comparison` or `property_delta` requests under
`comparison_plots:`. Do not reuse dataset `visualization:` inside sweep
configs. The concise packaged `model_sweep` starter must run in the base
install without Matplotlib; keep active `comparison_plots:` blocks in richer
examples only and document that they require `carnopy[viz]` or
`carnopy[all]`.

Preparation configurations use independent schema versioning:

```yaml
schema_version: 1
document_type: preparation
```

Preparation reads existing immutable dataset runs or model-sweep bundles and
writes Parquet derived-data outputs. It must resolve semantic fields through
source metadata/schema, preserve source row order, retain row-level source
identity, and never import or call thermodynamic backends. Preparation
separates user-facing `data/table.parquet` from `data/provenance.parquet` and
`data/diagnostics.parquet`, joined by `prepared_row_id`. Preparation may create
explicit leakage-aware scenarios, including user-binned `stratified_hash`, and
deterministic numeric transformations (`log10`, `standard`, `minmax`,
`robust`). Exact thermodynamic-state hashes must not cross automatic
partitions. Parquet remains canonical. Optional NumPy and
SafeTensors exports are derived ML-consumption files and must record feature
and target order, units, shapes, dtype, hashes, and conversion-error summaries.
Carnopy is not a training framework and does not optimize, depend on PyTorch,
or export `.pt`/`.pth` files. The optional `analysis` extra may fit disposable
scikit-learn baseline estimators for train/evaluation diagnostics only. It must
not persist models or predictions, tune hyperparameters, alter prepared rows,
or leak validation/test statistics into fitting.

If preparation selects reference-dependent properties (`specific_enthalpy`,
`specific_entropy`, or `specific_internal_energy`) as features, targets, or
numeric auxiliary fields, it must record the source reference-state context and
require one compatible `reference_state_policy`/backend/model context across
the selected source rows. Mixed incompatible absolute `h`, `s`, or `u` values
must fail before writing a preparation bundle.

[ML_PREPARATION_ROADMAP.md](ML_PREPARATION_ROADMAP.md) records implemented
preparation behavior separately from future research directions. Read it before
proposing preparation-quality, feature-engineering, statistical-diagnostic,
active-learning, or optimization work. Roadmap entries are not implementation
authority; public contracts still require a reviewed stage plan.

Dataset formats:

```yaml
outputs:
  dataset_formats: [csv, parquet]
```

Omission defaults to both formats. At least one of `csv` or `parquet` is
required. Canonical format order is CSV then Parquet.

Public samplers:

```text
explicit
linspace
stepspace
geomspace
logspace
```

`stepspace` is inclusive and requires a reachable endpoint. Public `arange` is
not supported.

Supported input units:

```text
temperature: K, degC
pressure: Pa, kPa, MPa, bar
vapor_mass_fraction: "1"
```

All backend calls and generated numeric columns use SI. Preserve original
units and sampler declarations in metadata.

The row limit is 1,000,000 after sampler materialization, fluid
canonicalization, Cartesian expansion, and saturation endpoint expansion.

Mode contracts:

- `property_table` requires temperature and pressure;
- `saturation_table` requires exactly one of temperature or pressure and emits
  separate liquid and vapor endpoint rows;
- `vapor_mass_fraction_table` requires vapor mass fraction plus exactly one of
  temperature or pressure.

Public `vapor_mass_fraction` maps to CoolProp `Q` only inside the adapter.
Use \(x_{\mathrm{vap}}\) as its scientific symbol in figures and equations;
do not rename the public schema or dataset field.

## Scientific behavior

Use the official CoolProp documentation as the backend authority:

- https://coolprop.org/coolprop/
- https://coolprop.org/coolprop/HighLevelAPI.html
- https://github.com/CoolProp/CoolProp

Reset every requested canonical fluid to CoolProp `DEF` once after validation
and before row evaluation. Do not change reference state during generation.

Specific enthalpy, entropy, and internal energy are reference-state dependent.
Absolute values are not directly comparable across different reference
conventions. Differences or ML datasets using these fields are meaningful only
within a recorded, compatible reference-state context.

If actual CoolProp behavior contradicts an approved contract:

1. Stop before implementing a workaround.
2. Preserve fluid, normalized inputs, property, mode, CoolProp version,
   exception type/message, and observed result.
3. Explain the contradiction.
4. Ask the maintainer to decide.

Do not silently change input pairs, phase rules, numerical methods, schemas, or
backend behavior.

## Rows, validity, and failures

Every row includes:

```text
run_id
case_id
mode
fluid
backend
backend_model
backend_version
phase
backend_phase
valid
failure_layer
failure_code
failure_message
failure_property
backend_error_type
backend_error_message
```

`case_id` is zero-based and assigned after deterministic final ordering.

Milestone 1 uses strict row validity. Any required coordinate, phase, or
requested-property failure invalidates the row. Successfully evaluated values
may remain populated; failed values remain null.

Do not infer stable failure categories by brittle parsing of backend messages.
Preserve raw backend diagnostics separately.

## Provenance and immutable artifacts

Identity meanings:

- `spec_id`: canonical executable scientific specification;
- `generation_context_id`: artifact-generation context;
- `output_request_id`: canonical CSV/Parquet serialization request;
- `run_id`: one UUID4 generation attempt;
- artifact hashes: exact emitted bytes;
- `visualization_request_id`: normalized visualization request.

Generation writes immutable run directories containing:

```text
dataset.csv
dataset.parquet
config.original.yaml
config.normalized.json
config.reference.yaml
metadata.json
report.json
```

`config.reference.yaml` is the mode-specific full commented template produced
from the same authoritative packaged source as `carnopy init MODE OUTPUT
--full`. Write it only into the fresh staging directory, include it in artifact
hashes and metadata, and never retrofit or overwrite it in an existing run.

Human-facing names use:

```text
<UTC-second>_<mode-slug>_<eight-character-run-prefix>
```

The directory name is a locator, not dataset identity.

Runs are staged and atomically renamed. Never overwrite an existing final or
staging directory. Do not add host source-config paths to metadata.

Tests use temporary directories. Do not commit generated datasets or figures.

## Visualization contracts

Visualization is a reproducible view of emitted columns:

- never call a thermodynamic backend;
- never smooth, interpolate, extrapolate, or invent states;
- preserve invalid and missing gaps;
- derive only `specific_volume = 1 / mass_density`;
- use semantic scientific labels and units;
- keep visualization identity separate from dataset identity.

Supported kinds:

```text
property_curves
property_heatmap
xy
pv
ts
```

CLI spelling uses `property-curves` and `property-heatmap`.

Manual exports:

- prefer Parquet in run directories;
- fall back to CSV for CSV-only runs;
- verify recorded source hashes;
- write outside immutable source runs;
- write an image plus `.plot.json`;
- refuse existing image or sidecar paths;
- finalize using exclusive same-filesystem hard links;
- remain no-overwrite-safe but not fully two-file crash-atomic.

Configured visualization:

- validates before thermodynamic generation;
- executes after dataset finalization;
- writes under a separate figure root;
- records one `visualization-report.json`;
- preserves successful figures after another plot fails;
- never changes `config.normalized.json`, `spec_id`,
  `generation_context_id`, or dataset artifact hashes.

`carnopy inspect SOURCE` reports emitted plotting capabilities without backend
calls. Text and JSON inspection must include source identity, integrity,
coordinates, levels, properties, ranges, phases, failures, plot capabilities,
series fields, and supported display units. Inspection may exclusively create
a visualization-only starter with `--write-visualization`.

Repeatable `--series FIELD=VALUE` selections choose exact emitted curve-family
levels after unit conversion and combine values for one field with logical OR.
Repeatable `--display-unit FIELD=UNIT` options affect figure values and labels
only; immutable datasets remain SI.

`carnopy plot RUN --config FILE.yaml` batch-renders a top-level
`visualization:` section against an existing immutable run. Batch rendering
must ignore scientific fields in a full generation config and validate only
against emitted run columns.

Dataset `run_status` remains solely about row validity.

## Architecture

The high-level pipeline is:

```text
YAML
  → validated configuration
  → canonical SI scientific specification
  → thin backend adapter
  → mode-specific rows
  → stable DataFrame schema
  → immutable CSV/Parquet + metadata/report
  → optional emitted-column visualization
```

The backend boundary contains only capabilities needed by current modes. It is
not a plugin framework. Add abstractions only when concrete additional backend
requirements exist.

Keep focused module boundaries:

- configuration parsing and normalization;
- semantic domain registries;
- backend adapter;
- mode generators;
- output/provenance writers;
- visualization requests, selection, rendering, and automation;
- desktop presentation, worker protocol, process control, workspace-local job
  records, safe source descriptors, and bounded table preview.

## Packaging and release safeguards

Use the `src/` layout and Hatchling:

```toml
[build-system]
requires = ["hatchling>=1.27.0"]
build-backend = "hatchling.build"
```

Matplotlib remains optional through `viz`; SafeTensors remains optional through
`ml`; scikit-learn remains optional through `analysis`; PySide6 Essentials and
Matplotlib remain optional through `app`; `all`
must remain synchronized with all user-facing extras. PyArrow remains core.
Qt/PySide6 remains an externally licensed optional dependency. Carnopy does not
vendor Qt or ship standalone desktop installers; downstream redistribution
requires review of the applicable Qt terms rather than assumptions based on
Carnopy's MIT license.

Carnopy uses alpha releases before stable `0.1.0`. The release workflow builds
one wheel and sdist, verifies them, requires human approval, and publishes them
to production PyPI through GitHub OIDC Trusted Publishing.

Only a human maintainer may:

- make the repository public;
- configure GitHub environments or Trusted Publishers;
- create or push release tags;
- approve production deployment;
- publish to PyPI.

Never rebuild changed payloads under an uploaded version. Any changed payload
requires a new version. Never use `skip-existing` to repair a partial release.

For each release:

1. update the source version and user-facing installation examples;
2. run the complete source and distribution gates;
3. commit and push, then require green CI on `main`;
4. create one annotated `v<version>` tag;
5. push only that tag and approve the protected `pypi` environment;
6. verify the published release and create a matching GitHub pre-release while
   Carnopy remains alpha.

Do not move or reuse a published version tag. After stable `0.1.0`, use ordinary
release versions unless a deliberate prerelease is needed.

Distribution checks:

```bash
uv run --locked --group release python -m build
uv run --locked --group release python -m twine check dist/*
uv run --locked python scripts/check_distribution.py dist/*
```

`python -m build` normally uses its default isolated build environment. That
environment installs the `[build-system]` requirements declared in
`pyproject.toml`. Do not modify the development environment solely to satisfy
the build backend. Use the ignored, repository-local `prerelease/` directory
for non-destructive rehearsal builds when an existing `dist/` must be
preserved. Final release artifacts belong in `dist/`. Do not write Carnopy
build artifacts outside the repository.

## Commit messages

Use:

```text
<type>(<scope>): <imperative summary>
```

Rules:

- lowercase type and scope;
- imperative mood: `add`, `fix`, `validate`, `reject`, `document`;
- concise summary, ideally no more than 72 characters;
- no trailing period;
- body only when the reason or tradeoff matters.

After completing and verifying an implementation, include a recommended commit
message in the final handoff. Also list the exact repository-relative files to
stage. If more than one commit is recommended, give the file group for each
commit and state whether hunk-level staging is required. Prefer one coherent
commit unless the proposed intermediate commits are independently reviewable
and verifiable. This is guidance for the human operator and does not grant Git
mutation authority.

Common types:

```text
feat fix test docs refactor chore ci build perf style
```

Recommended scopes:

```text
dataset schema sampler coolprop cli validation metadata tests docs ci
packaging viz app
```

Examples:

```text
feat(viz): add configured visualization outputs
fix(validation): reject duplicate canonical fluids
test(sampler): cover descending stepspace ranges
docs(project): consolidate public guidance
build(packaging): declare parquet runtime dependency
```
