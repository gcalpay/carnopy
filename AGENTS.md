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

Before starting an implementation stage, establish whether unrelated or
uncommitted work is present. If the tree is dirty, pause before editing,
describe the intended stage boundary, and suggest a Conventional Commit message
so separate stages are not mixed accidentally. Preserve unrelated changes.

Read-only Git commands are allowed when needed to inspect repository state or
review changes. Examples include:

```text
git status --short
git diff
git diff --check
git log
git show
git ls-files
```

Do not run Git commands that change repository state. Staging, committing,
amending, branching, tagging, rebasing, resetting, restoring, merging, pushing,
and changing remotes remain human-owned unless a local instruction explicitly
grants narrower authority.

Do not publish packages, create credentials, configure repository security, or
change dependency declarations without explicit maintainer authorization.

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
- configured post-generation visualization.
- model-sweep bundles comparing emitted values from multiple CoolProp models.

The `0.1.0a3` development line adds a Linux-first PySide6 desktop frontend for
the existing dataset workflow. The desktop application is a presentation
frontend, not a new scientific execution layer.

Out of scope:

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
explicit leakage-aware scenarios and deterministic numeric transformations
(`log10`, `standard`, `minmax`). Parquet remains canonical. Optional NumPy and
SafeTensors exports are derived ML-consumption files and must record feature
and target order, units, shapes, dtype, hashes, and conversion-error summaries.
Carnopy does not train, optimize, use scikit-learn, depend on PyTorch, or
export `.pt`/`.pth` files in this release line.

If preparation selects reference-dependent properties (`specific_enthalpy`,
`specific_entropy`, or `specific_internal_energy`) as features, targets, or
numeric auxiliary fields, it must record the source reference-state context and
require one compatible `reference_state_policy`/backend/model context across
the selected source rows. Mixed incompatible absolute `h`, `s`, or `u` values
must fail before writing a preparation bundle.

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
- visualization requests, selection, rendering, and automation.
- desktop presentation, worker protocol, and process control.

## Packaging and release safeguards

Use the `src/` layout and Hatchling:

```toml
[build-system]
requires = ["hatchling>=1.27.0"]
build-backend = "hatchling.build"
```

Matplotlib remains optional through `viz`; SafeTensors remains optional through
`ml`; `all` must remain synchronized with all user-facing extras. PyArrow
remains core.

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

Common types:

```text
feat fix test docs refactor chore ci build perf style
```

Recommended scopes:

```text
dataset schema sampler coolprop cli validation metadata tests docs ci
packaging viz
```

Examples:

```text
feat(viz): add configured visualization outputs
fix(validation): reject duplicate canonical fluids
test(sampler): cover descending stepspace ranges
docs(project): consolidate public guidance
build(packaging): declare parquet runtime dependency
```
