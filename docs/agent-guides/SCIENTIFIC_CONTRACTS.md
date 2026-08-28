# Public scientific and application contracts

This document is an authoritative routed part of the root
[contributor and coding-agent guide](../../AGENTS.md). Read it in full before
changing scientific behavior, configuration, sampling, CLI/API contracts, rows,
provenance, preparation, visualization, or core architecture. It must be
combined with the active stage plan and more specific architecture guidance
when those scopes apply.

The tracked README provides the public high-level direction. Maintainer-local
`PRODUCT_SCOPE.md` and `.agents/private/PRODUCT_STRATEGY.md`, when present,
may prioritize future work, but they do not override this document's current
scientific and public contracts or make an unimplemented direction available.

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

The `0.1.0a3` release established a Linux-first PySide6 Widgets frontend, and
`0.1.0a4` migrated the accepted workflows into one QML application while
removing the duplicate Widgets presentation. Current `0.1.0a5` source also
exposes structured Model Sweep and ML Preparation workflows plus direct
post-generation session plotting. The desktop remains a presentation frontend,
not a new scientific execution layer. Its permanent boundary includes the
private worker protocol, workspace lifecycle, worker-validated configuration,
saved-config execution, private activity and guarded staging recovery,
read-only source inspection, bounded table previews, configured and session
plot workflows, guarded no-overwrite image/sidecar promotion, Qt-only PNG/SVG
previews, and explicit PDF opening.

Development source after the published `0.1.0a5` payload additionally contains
GUI-2 Stage 6's private, nonvisual exact-scene preparation, verification,
lifecycle, and pick-resolution pipeline. It is not a public command, schema,
renderer, or released native-3D capability; its detailed scientific boundary
is recorded under Visualization below.

[GUI2_PLAN.md](../../GUI2_PLAN.md) is the temporary source of truth for unfinished
GUI-2 stages. Read it before changing desktop controllers, QML, native 3D, or
desktop packaging. Delete it only after GUI-2 is complete and permanent
documentation describes the final design.
[DESKTOP_ARCHITECTURE.md](../../DESKTOP_ARCHITECTURE.md) is the durable record of the
implemented desktop structure and evolution; update it when accepted work
changes a major ownership or process boundary.

Outside the current implemented contract:

- mixtures;
- ORC generation;
- additional property backends;
- random, Sobol, Latin-hypercube, adaptive, or active-learning sampling;
- ML training or inference;
- web/API services or databases;
- ThermoML, OCR, RAG, or literature mining.

[`THERMOPHYSICAL_ROADMAP.md`](../../THERMOPHYSICAL_ROADMAP.md) records public
source, mixture, model, backend, cycle, and visualization candidates.
[`ML_PREPARATION_ROADMAP.md`](../../ML_PREPARATION_ROADMAP.md) records current
Preparation behavior and future interoperability and evaluation directions.
Roadmap classifications are not implementation authority. Do not broaden this
contract without a separately approved stage and maintainer acceptance.

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

The desktop frontend follows the same boundary. Desktop presentation code must
communicate with one short-lived worker process through the private, versioned
JSON Lines protocol under `carnopy.app`; it must not invoke or parse the public
CLI.
Only the worker may import CoolProp, generation pipelines, pandas, PyArrow, or
Matplotlib. Progress and cooperative cancellation use private execution hooks;
do not add these hooks to the public Python API.

GUI-2 Stage 4 extends this private boundary with revision-bound, non-writing
planning and controlled execution for model sweeps and preparation. Planning
does not create output paths or fit baseline estimators. Execution recomputes
and verifies the current plan in its short-lived worker, persists Activity only
for execution, and protects the final immutable rename after all source,
serialization, and hashing checks succeed.

GUI-2 Stage 5 is complete without changing those public contracts. Current
source uses one exact-byte desktop configuration lifecycle for the three public
document types, enables the complete structured Model Sweep and Preparation
QML workflows, and implements Preparation source profiling, explicit source
binding, structured drafts, planning, execution, and typed inspection of
finalized Preparation quality, scenario, matrix, and baseline evidence.
Creating a new Preparation document requires an explicitly bound eligible
inspection, while opening portable Preparation YAML never invents or serializes
a source. The source binding is private execution context and never adds a path
to Preparation YAML. QML remains a typed presentation of the
same worker-authoritative schemas and scientific operations; no Stage 5 draft,
profile, issue model, plan projection, or controller property is a public
Python or inspection interface.

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
Carnopy is not a training framework. The current implementation does not
optimize, depend on PyTorch, or export `.pt`/`.pth` files. The product scope
records a reviewed but unscheduled optional PyTorch dataset-export direction;
this current contract remains unchanged until a separate stage is approved,
implemented, verified, and accepted. The optional `analysis` extra may fit
disposable scikit-learn baseline estimators for train/evaluation diagnostics
only. It must not persist models or predictions, tune hyperparameters, alter
prepared rows, or leak validation/test statistics into fitting.

If preparation selects reference-dependent properties (`specific_enthalpy`,
`specific_entropy`, or `specific_internal_energy`) as features, targets, or
numeric auxiliary fields, it must record the source reference-state context and
require one compatible `reference_state_policy`/backend/model context across
the selected source rows. Mixed incompatible absolute `h`, `s`, or `u` values
must fail before writing a preparation bundle.

[ML_PREPARATION_ROADMAP.md](../../ML_PREPARATION_ROADMAP.md) records implemented
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
pressure: Pa, hPa, kPa, MPa, bar, atm
vapor_mass_fraction: "1"
```

Use `1 hPa = 100 Pa` and `1 atm = 101325 Pa`. These exact decimal scale factors
pass through the same sampler-canonicalization boundary as every other input
unit.

Normalization deterministically canonicalizes each valid sampler definition to
SI before materializing it. Declared-unit definitions with the same exact
canonical sampler key must produce the same materialized SI grid and `spec_id`.
All backend calls and generated numeric columns use SI. Preserve original units
and sampler declarations in metadata.

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

`metadata.json` records Carnopy as the software generator with its installed
version, repository, and MIT license while retaining the top-level
`carnopy_version` field. Parquet schema metadata records the same software
identity alongside the existing dataset-schema and unit metadata. A software
DOI is omitted unless a real DOI has been assigned; placeholders, empty
strings, and null DOI values are forbidden. These optional additive fields do
not make older metadata-schema-version-1 runs unreadable and do not alter CSV
contents or scientific identity.

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
- keep p-v and T-s as emitted-state diagrams, split connected series at
  observed phase-label changes, and never imply a saturation dome, cycle, or
  process path;
- derive only `specific_volume = 1 / mass_density`;
- use semantic scientific labels and units;
- keep visualization identity separate from dataset identity.

GUI-2 Stage 6 also implements a private, nonvisual exact-scene preparation
contract for verified dataset-run, model-sweep-child, prepared-main, and
prepared-partition tables. It retains only source-valid rows with finite
selected X, Y, Z, and optional scalar values; stores original row position and
stable source identity; and separates connectivity by artifact, run, fluid,
model, phase, saturation endpoint, scenario, and partition. Adjacency follows
only verified original materialized sampler-level order. Missing, invalid,
filtered, or omitted intermediate levels remain gaps, and duplicate topology
locations remain distinct points while blocking ambiguous connectivity.

One-dimensional exact topology may emit only immediately adjacent edges.
Exactly two-dimensional topology may additionally emit one ordered quad per
complete adjacent cell as `[i,j]`, `[i+1,j]`, `[i+1,j+1]`, `[i,j+1]`. Exact
zero-length edges and repeated-vertex or exactly collinear quads are omitted
and counted without tolerance. Unsupported or unavailable topology is reported
explicitly. Scene preparation never emits triangles or calls a backend, and it
never interpolates, smooths, extrapolates, resamples, merges, or silently
repairs source data.

These scenes are private, versioned, session-only desktop artifacts rather than
a public dataset schema or API. They are bounded to 250,000 points, 499,999
edges, 249,999 quads, and a 64 MiB complete manifest-plus-binary bundle. Stage 6
adds no visible renderer; interactive native presentation remains GUI-2 Stage 7
and is unavailable in the current published alpha.

Sampled-series sidecars distinguish invalid or missing `gap_count` from
deliberate `phase_break_count`. Dense numeric curve families may replace an
unreadable discrete legend with one shared continuous colorbar across facets,
but the rendered coordinates and series membership remain the emitted values.

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
