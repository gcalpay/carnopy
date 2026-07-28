# Carnopy

[![PyPI](https://img.shields.io/pypi/v/carnopy.svg)](https://pypi.org/project/carnopy/)
[![Python](https://img.shields.io/pypi/pyversions/carnopy.svg)](https://pypi.org/project/carnopy/)
[![Verify](https://github.com/gcalpay/carnopy/actions/workflows/ci.yml/badge.svg)](https://github.com/gcalpay/carnopy/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Reproducible thermophysical dataset generation from thermodynamic backends with
inspection, visualization, and leakage-aware ML preparation through a CLI and
optional desktop GUI.

> Alpha software: public interfaces and generated schemas may still change
> before the stable `0.1.0` release.

Carnopy is not a thermodynamic property model. It orchestrates configured
property backends, validates deterministic sampling, preserves failed states as
diagnostics, and emits stable tabular data with provenance. Generated values are
synthetic backend output, not experimental data or backend-independent ground
truth.

Milestone 1 supports pure fluids through CoolProp and three modes:

- `property_table`: temperature-pressure state tables;
- `saturation_table`: saturated-liquid and saturated-vapor endpoint rows;
- `vapor_mass_fraction_table`: two-phase states over vapor mass fraction.

Carnopy has two user interfaces:

- **Command-line interface:** version `0.1.0a3` provides the complete dataset,
  sweep, inspection, plotting, and preparation workflow.
- **Desktop GUI:** version `0.1.0a3` provides an optional Linux-first PySide6
  application for dataset configuration, generation, inspection, and plotting.

## Installation

### Version `0.1.0a3`

Install the CLI-first base package:

```bash
python -m pip install "carnopy==0.1.0a3"
```

Add Matplotlib plotting support:

```bash
python -m pip install "carnopy[viz]==0.1.0a3"
```

Add SafeTensors preparation exports:

```bash
python -m pip install "carnopy[ml]==0.1.0a3"
```

Add optional scikit-learn preparation diagnostics:

```bash
python -m pip install "carnopy[analysis]==0.1.0a3"
```

Add the desktop application:

```bash
python -m pip install "carnopy[app]==0.1.0a3"
```

Install every optional capability:

```bash
python -m pip install "carnopy[all]==0.1.0a3"
```

For an isolated CLI installation:

```bash
uv tool install "carnopy==0.1.0a3"
```

To include every optional capability:

```bash
uv tool install "carnopy[all]==0.1.0a3"
```

The `0.1.0a3` base install remains CLI-first and does not install Matplotlib,
SafeTensors, scikit-learn, or PySide6. Its lightweight `carnopy-app --help`,
`carnopy-gui --help`, and version entry points remain available, while opening
the desktop requires the `app` extra. The `app` extra installs PySide6
Essentials and Matplotlib. The `all` extra is the dependency union of `viz`,
`ml`, `analysis`, and `app`. The desktop launchers remain separate from the CLI
as `carnopy-app` and `carnopy-gui`. PyArrow remains a core dependency because
Parquet is a first-class output format.

### Development checkout

Run the desktop directly from a source checkout:

```bash
git clone https://github.com/gcalpay/carnopy.git
cd carnopy
uv sync --locked --extra app --group dev
uv run --locked carnopy-gui
```

The source-tree `app` extra has the same optional dependency boundary. The
development `viz` and `app` extras declare a Pillow security floor for
Matplotlib's transitive image dependency; Pillow is not a separate Carnopy
feature. The active GUI-2 source line reports `0.1.0a4.dev0`, while the
published install commands above remain pinned to `0.1.0a3`. Stage 1
controller extraction is complete. The active GUI-2 `app` extra requires
PySide6 Essentials 6.11.1 or later within the 6.11 release line; the private
native bridge remains qualified against exactly Qt 6.11.1. On the active
`0.1.0a4.dev0` source line, `carnopy-gui` launches the modern QML application
and `carnopy-app` is a compatibility alias for that same application. The
Widgets implementation remains in the source tree only as a temporary parity
oracle until its dedicated retirement step.

## Quick start

```bash
carnopy init property_table my-dataset.yaml
# Edit the generated YAML, then:
carnopy generate my-dataset.yaml
carnopy inspect outputs/<run>
carnopy plot outputs/<run> \
  --kind property-curves \
  --property mass_density \
  --x temperature
```

The normal workflow is:

```text
init → edit → optional validate → generate/sweep → inspect → optional plot → optional prepare
```

For repository development:

```bash
uv sync --locked --extra all --group dev
uv run --locked carnopy --help
```

The current desktop development build can be opened from a source checkout:

```bash
uv run --locked carnopy-gui
```

To preselect a workspace without initializing it silently:

```bash
uv run --locked carnopy-gui --workspace /path/to/workspace
```

Qt normally selects its platform integration automatically. On WSLg, Carnopy's
`auto` mode prefers XCB when both WSLg display transports are available because
native Wayland dialogs can remain detached after selection. To select XCB
explicitly:

```bash
uv run --locked carnopy-gui --qt-platform xcb --workspace /path/to/workspace
```

The corresponding explicit Wayland selection is `--qt-platform wayland`;
omit the option or use `auto` for native platform detection outside WSLg and
the guarded XCB selection on WSLg. An existing `QT_QPA_PLATFORM` environment
override remains authoritative.

The current QML development application provides workspace lifecycle, a
worker-validated editor for all three dataset modes, deterministic YAML and
Save flows, exact-saved-configuration generation, bounded source and table
inspection, configured and session plot workflows, private Run activity, and
guarded staging recovery. Scientific generation, inspection, and Matplotlib
rendering remain in short-lived workers. PNG and SVG use verified in-app
previews; PDF opens only after explicit revalidation and user action.

## Guide

- [Workflow details](#workflow-details)
- [Configuration](#configuration)
- [Properties](#properties)
- [Visualization](#visualization)
- [Generated outputs and provenance](#generated-outputs-and-provenance)
- [Python API](#python-api)
- [Desktop GUI](#desktop-gui)
- [ML preparation roadmap](https://github.com/gcalpay/carnopy/blob/main/ML_PREPARATION_ROADMAP.md)
- [Architecture map](#architecture-map)
- [Scientific limitations](#scientific-limitations)
- [Development and contribution](#development-and-contribution)
- [Project status and roadmap](#project-status-and-roadmap)

## Workflow details

```text
init → edit → optional validate → generate/sweep → inspect → optional plot → optional prepare
```

Create a starter configuration:

```bash
carnopy init property_table my-dataset.yaml
```

`init` reads the selected template packaged inside the installed `carnopy`
module and writes a new file at the path you provide. For example, when the
current directory is `/home/cfd/carnopy/`:

```bash
carnopy init property_table property.yaml
```

creates:

```text
/home/cfd/carnopy/property.yaml
```

from the packaged `property_table.yaml` template. It does not modify or move
the packaged source.

Use `--full` to append the exhaustive commented reference for current
samplers, properties, units, output formats, visualization kinds, filters,
series selection, scales, and identity rules:

```bash
carnopy init property_table my-dataset.yaml --full
```

The active mode-specific configuration remains valid. Normal templates remain
concise. Both forms refuse to overwrite an existing `property.yaml`. A relative
output path is resolved from the current working directory; an absolute path
is written exactly where specified.

Available dataset modes:

```text
property_table
saturation_table
vapor_mass_fraction_table
```

Additional workflow/template types:

```text
model_sweep
```

`model_sweep` is not a dataset mode. It creates a sweep bundle containing one
immutable child dataset run per selected model plus comparison artifacts.

Discover backend fluids and semantic properties:

```bash
carnopy fluids                 # HEOS default
carnopy fluids --model pr      # model-specific availability
carnopy properties
```

Edit the YAML, optionally validate it, then generate an immutable run:

```bash
carnopy validate my-dataset.yaml
carnopy generate my-dataset.yaml
```

`generate` validates automatically. The separate `validate` command is useful
for scripts and early feedback, but does not evaluate thermodynamic rows.

After generation, inspect the run before choosing a plot:

```bash
carnopy inspect outputs/<run>
```

The inspection lists fluids, sampling levels, emitted properties, compatible
plot kinds, valid/invalid rows, phase and failure counts, property ranges,
available curve-series fields, supported display units, and copyable commands.

Use structured output in scripts or create a visualization-only starter file
for the immutable run:

```bash
carnopy inspect outputs/<run> --format json
carnopy inspect outputs/<run> --write-visualization plots.yaml
carnopy plot outputs/<run> --config plots.yaml
```

The writer uses exclusive creation and refuses to replace an existing YAML
file. It does not evaluate thermodynamic states or create a figure.

To choose a different output root:

```bash
carnopy generate \
  configs/cyclopentane_vapor_fraction_pressure.yaml \
  --out outputs/manual-test
```

The run is created directly under that root. Copy the exact path printed after
`Output directory:`; do not prepend the output root again:

```bash
# Example only; replace this with the exact path printed by your run.
RUN_DIR="outputs/manual-test/20260621T172006Z_vapor_fraction_c8e28e9f"
```

Run names use UTC creation time, a short mode label, and the first eight
hexadecimal characters of the unique `run_id`. Full identities and hashes
remain in `metadata.json`.

Use command-specific help for the complete current interface:

```bash
carnopy --help
carnopy generate --help
carnopy plot --help
```

## Configuration

Schema version 2 requires an explicit dataset document type and CoolProp
thermodynamic model:

```yaml
schema_version: 2
document_type: dataset
backend:
  name: coolprop
  model: heos
mode: property_table
fluids: [Propane, Isobutane]

grid:
  temperature:
    kind: linspace
    start: -50
    stop: 50
    num: 101
    unit: degC
  pressure:
    kind: linspace
    start: 101325
    stop: 506625
    num: 41
    unit: Pa

properties:
  - specific_enthalpy
  - mass_density

outputs:
  # Omit this section to keep the same default.
  dataset_formats: [csv, parquet]
```

Schema version 1 configuration files are intentionally rejected with a concise
migration message. Existing generated run directories remain readable.

### CoolProp models

Supported model names:

| Model | Meaning | Current capability notes |
|---|---|---|
| `heos` | CoolProp Helmholtz-energy equations and associated ancillary/transport models | Supports the full current Carnopy property registry, subject to fluid/state limitations. |
| `pr` | Peng-Robinson cubic equation of state | No viscosity, thermal conductivity, Prandtl number, surface tension, or usable triple-point temperature. |
| `srk` | Soave-Redlich-Kwong cubic equation of state | No viscosity, thermal conductivity, Prandtl number, surface tension, or usable triple-point temperature. |

Model selection is part of the executable scientific specification and changes
`spec_id`. The selected model is recorded in every generated row, metadata,
reports, and normalized configuration. HEOS is the starter default, not
experimental truth. PR and SRK are alternative model assumptions, not
accuracy rankings.

Reference-dependent enthalpy, entropy, and internal energy can differ between
models even after each model-qualified fluid is reset to CoolProp `DEF`.
Absolute values must not be compared across model/reference conventions without
an explicit scientific basis.

### Model sweeps

Model sweeps compare emitted values from several CoolProp models without
performing extra thermodynamic evaluations during comparison:

```bash
carnopy init model_sweep sweep.yaml
carnopy sweep sweep.yaml
```

The sweep document type is separate from dataset generation:

```yaml
schema_version: 2
document_type: model_sweep
backend:
  name: coolprop
  models: [heos, pr, srk]
  reference_model: heos
mode: property_table
fluids: [Propane]
grid:
  temperature: {kind: linspace, start: 280, stop: 340, num: 5, unit: K}
  pressure: {kind: linspace, start: 1, stop: 5, num: 5, unit: bar}
properties: [mass_density]
```

Each selected model creates a normal immutable child run under the sweep bundle.
Comparison artifacts are written as tidy Parquet tables:

```text
comparison/values.parquet
comparison/deltas.parquet
```

State alignment uses deterministic keys derived from normalized sample indices,
not backend-computed floating-point saturation coordinates. The selected
reference model is a comparison baseline, not experimental truth.
Reference-dependent properties such as enthalpy, entropy, and internal energy
are excluded from delta metrics.

Optional sweep-level comparison plots are explicit and separate from child-run
visualization. They require the optional visualization dependencies, installed
with `carnopy[viz]` or `carnopy[all]`. The concise `carnopy init model_sweep`
starter keeps this block commented so no-plot sweeps run in a base installation:

```yaml
comparison_plots:
  format: png
  plots:
    - name: propane_density_temperature_by_pressure
      kind: property_comparison
      fluid: Propane
      property: mass_density
      x: temperature
      group_by: pressure
      models: [heos, pr, srk]
    - name: propane_density_relative_delta
      kind: property_delta
      fluid: Propane
      property: mass_density
      x: temperature
      group_by: pressure
      models: [pr, srk]
      delta_metric: signed_relative_difference
```

Stage 4 comparison plots are one-fluid, one-property, one-x-axis side-by-side
model value comparisons or model-vs-reference delta plots. Multiple fluids
require multiple plot entries.

### ML preparation foundation

Preparation is the current ML-pipeline bridge. It reads an existing immutable
run or model-sweep bundle and writes deterministic Parquet outputs without
calling a thermodynamic backend. Omit `scenarios:` for a single unsplit
prepared table:

```bash
carnopy init preparation preparation.yaml
carnopy prepare outputs/<run> --config preparation.yaml --out prepared
```

Preparation configuration uses its own independent schema version:

```yaml
schema_version: 1
document_type: preparation
features:
  numeric: [temperature, pressure, mass_density]
  derived: [specific_volume]
categorical_features:
  - field: phase
    encoding: one_hot
    categories: observed
targets: [specific_enthalpy]
auxiliary: [fluid, backend_model, phase, run_id, case_id]
outputs:
  formats: [parquet]
```

Prepared bundles contain `manifest.json`, `diagnostics.json`,
`dataset_card.md`, `data/table.parquet`, `data/provenance.parquet`,
`data/diagnostics.parquet`, `data/exclusions.parquet`,
`quality_report.json`, and `data/quality_flags.parquet`.
`table.parquet` is the user-facing feature/target table. Provenance and source
diagnostics are separated and join back to the table through `prepared_row_id`.
Quality diagnostics are advisory: they summarize robust distributions,
finite-value coverage, target ranges, duplicate state candidates, scenario
partitions, and exact eligible property-table grid coverage where that shape can be
inferred safely. Quality flags
stay in a separate long-form table joined through `prepared_row_id`; they do not
exclude rows or change `table.parquet`.
If no source rows can produce the requested representation, Carnopy writes a
clearly marked `no_eligible_rows` bundle without `data/table.parquet`.

If selected features or targets include reference-dependent properties
(`specific_enthalpy`, `specific_entropy`, or `specific_internal_energy`),
preparation records the source reference-state context and requires one
compatible `reference_state_policy`/backend/model context across the selected
source rows. This allows ordinary same-context training data and rejects
misleading mixtures of absolute `h`, `s`, or `u` values from incompatible
contexts.

Optional leakage-aware scenarios add deterministic partition artifacts and
plain-JSON transformation parameters. Current numeric transformations are
`log10`, `standard`, `minmax`, and train-fitted median/IQR `robust` scaling:

```yaml
scenarios:
  - name: shuffle_baseline
    kind: shuffle
    seed: 42
    partitions:
      train: 0.8
      validation: 0.1
      test: 0.1
    transformations:
      - field: pressure
        methods: [log10, robust]

  - name: phase_temperature_strata
    kind: stratified_hash
    seed: 42
    partitions:
      train: 0.8
      validation: 0.1
      test: 0.1
    strata:
      categorical: [phase]
      numeric_bins:
        reduced_temperature: [0.8, 0.95, 1.05]

  - name: leave_fluid_out
    kind: leave_fluid_out
    holdouts:
      test: [Isopentane]
    remainder: train
```

Supported scenarios are `unsplit`, `shuffle`, `stratified_hash`, `coordinate_block`,
`range_holdout`, `leave_fluid_out`, `phase_holdout`, and `model_holdout`.
Shuffle and stratified scenarios keep an exact thermodynamic-state hash in one
partition. Numeric strata use only user-declared boundaries; empty or undersized
strata fail clearly rather than being silently rebalanced.

Optional matrix and baseline diagnostics are configured separately:

```yaml
quality:
  matrix_diagnostics:
    correlation_threshold: 0.995
    near_constant_relative_spread: 1.0e-12
  baseline_diagnostics:
    models: [dummy_mean, ridge, hist_gradient_boosting]
    random_seed: 42
    ridge_alpha: 1.0
    histogram_max_iterations: 100
```

Matrix diagnostics use configured features only and report constants,
near-constants, correlations, singular values, numerical rank, effective rank,
and conditioning. They fit on each scenario's `train` partition, or state
explicitly that an unsplit report uses `all`. Baseline diagnostics require
`carnopy[analysis]`; they fit disposable scikit-learn estimators on `train` and
report validation/test MAE, RMSE, and R² per target. Carnopy never persists the
estimators or predictions and does not tune, register, deploy, or use them to
change prepared rows.

Parquet remains the canonical prepared table. Optional NumPy and SafeTensors
exports are derived ML-consumption files:

```yaml
outputs:
  parquet: true
  arrays:
    formats: [npy, npz, safetensors]
    dtype: float32
    include_auxiliary: false
```

Array exports require `carnopy[ml]` or `carnopy[all]` when SafeTensors is
requested. Carnopy records feature/target order, units, shapes, dtype, file
hashes, and float32 conversion-error summaries in the manifest. It does not
depend on PyTorch or export `.pt`/`.pth` files in this release line. Implemented
behavior and reviewed future directions are separated in the
[ML preparation roadmap](https://github.com/gcalpay/carnopy/blob/main/ML_PREPARATION_ROADMAP.md).
Automatic PCA feature replacement, active learning, Manim animations, PyMC
workflows, SINDy, optimization, ORC/TFC work, mixtures, new backends, and a
professional 3D GUI remain separate reviewed milestones rather than implicit
parts of `prepare`.

### Modes

`property_table` requires temperature and pressure and generates their Cartesian
product for every selected fluid.

`saturation_table` requires exactly one of temperature or pressure. It computes
the missing saturation coordinate and emits separate saturated-liquid and
saturated-vapor rows.

`vapor_mass_fraction_table` requires vapor mass fraction plus exactly one of
temperature or pressure. Vapor mass fraction is vapor mass divided by total
vapor-plus-liquid mass. Carnopy denotes it by $x_{\mathrm{vap}}$ in figures
and scientific equations while keeping the explicit public field name
`vapor_mass_fraction`. CoolProp's `Q` name remains internal to the adapter.

For a pure fluid at fixed saturation temperature or pressure:

- $x_{\mathrm{vap}}=0$ is the saturated-liquid boundary;
- $x_{\mathrm{vap}}=1$ is the saturated-vapor boundary;
- $0<x_{\mathrm{vap}}<1$ is an equilibrium two-phase mixture state.

The endpoint states have definite backend properties. Near-endpoint values such
as `0.01` and `0.99` are interior mixture states; they supplement rather than
replace the boundaries. For specific enthalpy and specific volume:

```math
h(x_{\mathrm{vap}})
=(1-x_{\mathrm{vap}})h_f+x_{\mathrm{vap}}h_g
```

```math
\frac{1}{\rho(x_{\mathrm{vap}})}
=\frac{1-x_{\mathrm{vap}}}{\rho_f}
+\frac{x_{\mathrm{vap}}}{\rho_g}
```

See the
[CoolProp high-level saturation documentation](https://coolprop.org/coolprop/HighLevelAPI.html#vapor-liquid-and-saturation-states)
for the backend definition of the endpoint states.

### Samplers

| Sampler | Parameters | Behavior |
|---|---|---|
| `explicit` | `values` | Preserves declared order; values must be finite and unique after SI conversion. |
| `linspace` | `start`, `stop`, `num` | Includes both endpoints; supports ascending and descending ranges. |
| `stepspace` | `start`, `stop`, `step` | Includes both endpoints; the endpoint must be reachable. |
| `geomspace` | `start`, `stop`, `num` | Positive physical endpoints; supports either direction. |
| `logspace` | `start_exp`, `stop_exp`, `num`, optional `base` | Samples exponent space; `base` must exceed one. |

Equal sampler bounds are rejected; use `explicit` for one value. Geometric and
logarithmic sampling is not supported for offset Celsius values or vapor mass
fraction. Use Kelvin for geometric temperature grids.

`linspace` uses uniform increments. For example, `start: 1`, `stop: 5`, and
`num: 5` produce `1, 2, 3, 4, 5`. `geomspace` uses uniform ratios and produces
approximately `1, 1.495, 2.236, 3.344, 5` for the same bounds.

### Dataset formats

Select generated table formats independently of the scientific specification:

```yaml
outputs:
  dataset_formats: [csv]
```

Supported values are `csv` and `parquet`. At least one is required. Omitting
`outputs` preserves the default `[csv, parquet]`. Format selection changes the
artifact-generation context and `output_request_id`, but not `spec_id` or
`config.normalized.json`.

### Units

Supported input units:

```text
temperature: K, degC
pressure: Pa, hPa, kPa, MPa, bar, atm
vapor_mass_fraction: "1"
```

YAML uses `degC` as the stable token for degrees Celsius. One hectopascal is
exactly `100 Pa`, and one standard atmosphere is exactly `101325 Pa`. All valid
declared units are canonicalized to SI before sampling.

Carnopy deterministically canonicalizes each sampler definition to SI before it
materializes the grid. Engineering-unit declarations with the same exact
canonical sampler key therefore produce the same materialized SI grid and
scientific `spec_id`. All backend calls and generated numeric columns use SI,
while original units and sampler definitions remain recorded in metadata.

Validation rejects non-finite values, non-positive pressure, temperatures at or
below absolute zero, vapor mass fractions outside `[0, 1]`, incompatible units,
duplicate canonical fluids, and projected runs above 1,000,000 rows.

Validation proves that a configuration is structurally executable. It does not
promise that every fluid, state, phase, and requested property will be valid.

## Properties

Use `carnopy properties` for the authoritative installed registry and its
HEOS/PR/SRK support columns. Properties globally unsupported by a selected
model fail configuration validation before row generation.

| Semantic name | Dataset column | Classification |
|---|---|---|
| `specific_enthalpy` | `specific_enthalpy_J_kg` | backend-provided, reference-dependent |
| `specific_entropy` | `specific_entropy_J_kgK` | backend-provided, reference-dependent |
| `specific_internal_energy` | `specific_internal_energy_J_kg` | backend-provided, reference-dependent |
| `mass_density` | `mass_density_kg_m3` | backend-provided |
| `isobaric_specific_heat_capacity` | `isobaric_specific_heat_capacity_J_kgK` | backend-provided |
| `isochoric_specific_heat_capacity` | `isochoric_specific_heat_capacity_J_kgK` | backend-provided |
| `dynamic_viscosity` | `dynamic_viscosity_Pa_s` | backend-provided |
| `kinematic_viscosity` | `kinematic_viscosity_m2_s` | derived from viscosity and density |
| `thermal_conductivity` | `thermal_conductivity_W_mK` | backend-provided |
| `prandtl_number` | `prandtl_number` | backend-provided |
| `speed_of_sound` | `speed_of_sound_m_s` | backend-provided |
| `molar_mass` | `molar_mass_kg_mol` | fluid constant |
| `critical_temperature` | `critical_temperature_K` | fluid constant |
| `critical_pressure` | `critical_pressure_Pa` | fluid constant |
| `triple_point_temperature` | `triple_point_temperature_K` | fluid constant |
| `surface_tension` | `surface_tension_N_m` | mode/region limited |

Derived dependencies may be evaluated internally without being emitted unless
explicitly requested. Fluid constants may be repeated in rows and are also
summarized in metadata.

Milestone 1 uses strict row validity: failure of any required coordinate, phase,
or requested property makes the row invalid. Successfully evaluated values may
remain populated while failed values remain null. Requesting a mode-limited
property such as `surface_tension` over a broad state grid can therefore
invalidate otherwise usable rows.

## Visualization

Visualization is a reproducible view of emitted dataset columns:

- it never calls CoolProp or another thermodynamic backend;
- it never smooths, interpolates, extrapolates, or invents states;
- it preserves invalid and missing gaps;
- it retains markers at emitted samples;
- its identity is separate from scientific dataset identity.

Install `carnopy[all]` or `carnopy[viz]` before plotting.

### Manual plotting

Supported plot kinds:

```text
property-curves
property-heatmap
xy
pv
ts
```

Property curves use discrete, colorblind-safe series colors and markers.
For `property_table`, choose the x-axis explicitly:

```bash
carnopy plot outputs/<property-run> \
  --kind property-curves \
  --property mass_density \
  --x temperature
```

Carnopy connects adjacent valid emitted samples with straight line segments as
visual guides. It does not smooth or evaluate intermediate states. A sparse
series advisory is emitted for connected series with five or fewer samples.
Generate a denser source grid for finer thermodynamic resolution. Use SVG or
PDF for zoom-independent rendering:

```bash
carnopy plot outputs/<run> ... --output figures/plot.svg
carnopy plot outputs/<run> ... --output figures/plot.pdf
```

For `vapor_mass_fraction_table`, vapor mass fraction is the x-axis and the
sampled saturation pressure or temperature defines the series:

```bash
carnopy plot "$RUN_DIR" \
  --kind property-curves \
  --property mass_density \
  --value-scale linear \
  --show
```

Sampled heatmaps use flat, non-interpolated cells and require at least two
unique values on each axis:

```bash
carnopy plot "$RUN_DIR" \
  --kind property-heatmap \
  --property specific_enthalpy \
  --color-scale linear
```

`saturation_table` does not support property heatmaps because it contains only
the two endpoint branches.

Generic x-y plots use numeric semantic fields from emitted columns:

```bash
carnopy plot outputs/<property-run> \
  --kind xy \
  --x specific_enthalpy \
  --y specific_entropy \
  --group-by pressure
```

If more than one independent sampling coordinate remains, `--group-by` must
resolve the ambiguity. Carnopy does not apply hidden grouping precedence.

Conventional thermodynamic diagrams are derived only from emitted columns:

```bash
carnopy plot outputs/<run-with-density> --kind pv
carnopy plot outputs/<run-with-entropy> --kind ts
```

The p-v diagram uses:

```text
specific_volume = 1 / mass_density
```

The T-s diagram uses emitted entropy and temperature and requires recorded
reference-state metadata. Neither command fabricates a saturation dome,
critical point, or missing branch.

Exact filters use canonical SI values and never select a nearest neighbor:

```bash
carnopy plot "$RUN_DIR" \
  --kind property-curves \
  --property mass_density \
  --filter pressure=200000
```

Repeat `--filter` to combine filters with logical AND. Current filter fields are
temperature, pressure, vapor mass fraction, phase, and saturation endpoint.
Repeat `--fluid` to select multiple fluids; each fluid receives its own facet.

Select specific members of a curve family with repeatable unit-aware
`--series` options. Values for the same field are combined with logical OR:

```bash
carnopy plot outputs/<property-run> \
  --kind property-curves \
  --property specific_enthalpy \
  --x temperature \
  --series pressure=1bar \
  --series pressure=3bar \
  --series pressure=5bar \
  --display-unit temperature=degC \
  --display-unit pressure=bar \
  --display-unit specific_enthalpy=kJ/kg
```

Series selection is exact after conversion to canonical SI; Carnopy never
chooses the nearest emitted level. Supported engineering display conversions
cover temperature, pressure, enthalpy, internal energy, entropy, and specific
heat capacities. Display conversion changes only figure values and labels, not
the immutable SI dataset.

`SOURCE` may be a run directory, CSV, or Parquet file. Run directories prefer
Parquet and verify it against `metadata.json`. Standalone saturation and
vapor-quality files may require `--saturation-coordinate pressure` or
`--saturation-coordinate temperature`.

Every export writes an image plus `.plot.json` provenance sidecar under
`figures/` by default. Existing image or sidecar paths are refused.
Finalization uses exclusive same-filesystem hard links: it is no-overwrite-safe,
but the two-file pair is not fully crash-atomic.

### Configured visualization

An optional top-level `visualization` section generates figures after the
immutable dataset run is finalized:

```yaml
visualization:
  format: png
  fluids: [Propane]
  display_units:
    pressure: bar

  plots:
    - name: density-vs-temperature
      kind: property_curves
      property: mass_density
      x: temperature
      series:
        pressure: [1bar, 3bar, 5bar]
      display_units:
        temperature: degC
      value_scale: linear

    - name: density-map
      kind: property_heatmap
      property: mass_density
      color_scale: log

    - name: enthalpy-entropy
      kind: xy
      x: specific_enthalpy
      y: specific_entropy
      group_by: pressure

    - name: pressure-specific-volume
      kind: pv

    - name: temperature-entropy
      kind: ts
```

Supported formats are `png`, `pdf`, and `svg`. Per-plot `format` and `fluids`
replace their shared values; scales are selected per plot. Per-plot filters are
AND-merged with shared filters, and conflicting values for the same field are
rejected. Plot names must be unique safe filename slugs. Output paths and
interactive display are intentionally not stored in YAML.

Shared or per-plot exact filters use YAML mappings:

```yaml
visualization:
  filters:
    phase: gas
  plots:
    - name: gas-density
      kind: property_curves
      property: mass_density
      x: temperature
      filters:
        pressure: 100000
```

Generate with the default figure root:

```bash
carnopy generate my-dataset.yaml
```

Or select another figure root:

```bash
carnopy generate my-dataset.yaml \
  --out outputs/manual-test \
  --figures-out figures/manual-test
```

Configured figures are written to:

```text
<figures-root>/<run-directory-name>/
├── <plot-name>.<format>
├── <plot-name>.plot.json
└── visualization-report.json
```

The same YAML requests can be applied later to an existing immutable run. The
file may be a full Carnopy configuration or a small file containing only a
top-level `visualization:` section:

```bash
carnopy plot outputs/<run> \
  --config plots.yaml \
  --figures-out figures
```

Batch plotting accepts run directories, not standalone CSV/Parquet files.
Scientific generation fields in a full config are ignored; requests are
validated against the actual emitted run columns. Manual plot options cannot be
combined with `--config`.

Plots execute independently after dataset finalization. A failed plot preserves
the immutable run and any successful figures, records outcomes in the report,
and makes the CLI exit with code `1`. A zero-valid-row dataset retains exit code
`3` and records configured plots as skipped.

Visualization settings do not change `config.normalized.json`, `spec_id`, or
`generation_context_id`. They receive their own
`visualization_request_id = viz-<sha256>`. Exact YAML bytes still affect the raw
configuration hash.

## Generated outputs and provenance

`outputs/` is a local generated-data directory and is intentionally ignored by
Git. Carnopy creates output roots when requested; the repository does not track
an empty placeholder or generated example runs.

Each immutable run contains the selected dataset files plus mandatory
provenance outputs:

```text
outputs/<run>/
├── dataset.csv          # when requested
├── dataset.parquet      # when requested
├── config.original.yaml
├── config.normalized.json
├── config.reference.yaml # full mode-specific commented configuration helper
├── metadata.json
└── report.json
```

Runs are staged and then finalized atomically as one directory. Existing final
or staging paths are never overwritten.

`config.reference.yaml` comes from the same packaged source as `carnopy init
MODE OUTPUT --full`. It is created only while staging a new run, included in
the artifact inventory and hashes, and never added to or overwritten in an
existing run.

Identity layers:

- `spec_id`: canonical executable scientific specification;
- `generation_context_id`: specification plus software and artifact context;
- `output_request_id`: canonical dataset serialization request;
- `run_id`: one UUID4 execution attempt;
- artifact hashes: exact emitted bytes;
- `visualization_request_id`: normalized visualization request, independent
  from dataset identity.

Configuration provenance includes SHA-256 hashes of exact source YAML and
canonical materialized SI configuration bytes. Metadata records software
versions, backend model, model-qualified reference-state targets, canonical
fluids and properties, model capabilities, sampling, failure counts, units,
fluid constants, and artifact hashes. Carnopy does not store the host
source-config path.

Parquet schema metadata includes the dataset schema version and unit mapping.
Figures are derived artifacts outside the run and are not added to immutable
dataset artifact hashes.

## Python API

```python
from carnopy import generate_dataset, load_config, validate_config

loaded = load_config("my-dataset.yaml")
validation = validate_config("my-dataset.yaml")
result = generate_dataset(
    "my-dataset.yaml",
    output_root="outputs",
    figures_root="figures",
)
```

When configured visualization exists, `result.visualization` contains its
request ID, status, figure directory, report path, and outcome counts.
`result.dataset_formats` and `result.output_request_id` describe the selected
table serialization independently of the scientific `spec_id`.

Manual plotting:

```python
from carnopy.visualization import (
    plot_property_heatmap,
    plot_thermodynamic_diagram,
    plot_xy,
)

heatmap = plot_property_heatmap(
    "outputs/<run>",
    property_name="mass_density",
)

xy = plot_xy(
    "outputs/<run>",
    x="specific_enthalpy",
    y="specific_entropy",
    group_by="pressure",
)

pv = plot_thermodynamic_diagram("outputs/<run>", kind="pv")
```

The returned Matplotlib figure represents an image that has already been
exported. Modifying it does not update the image or provenance sidecar.

## Desktop GUI

The desktop frontend is optional through `carnopy[app]`. The published
`0.1.0a3` release uses Qt Widgets. The active `0.1.0a4.dev0` source line routes
both `carnopy-gui` and the compatibility alias `carnopy-app` to the modern QML
application. Neither frontend parses or invokes CLI output; scientific
validation and execution run in short-lived workers through a private,
versioned JSON Lines protocol.

See [Desktop architecture and evolution](DESKTOP_ARCHITECTURE.md) for the
implemented controller ownership, process boundary, frontend migration status,
verification layers, and GUI-1/GUI-2 evolution record.

The prepared `0.1.0a3` source implementation includes:

- explicit workspace creation, initialization, and reopening;
- workspace-local `configs/`, `outputs/`, and `figures/` directories;
- structured editing for HEOS, PR, and SRK dataset configurations;
- all three dataset modes, current samplers, units, properties, and output
  formats;
- guided configured-visualization requests for every current plot kind;
- deterministic read-only YAML preview;
- worker validation before Import or Save;
- exclusive Save As, atomic normal Save, dirty-state prompts, and external-file
  modification detection;
- optional explicit validation and independent generation of the exact saved
  configuration, with phases, row progress, cooperative cancellation, and an
  informational equivalent CLI command;
- direct-child workspace source discovery plus read-only external browsing;
- structured inspection of dataset runs, standalone CSV/Parquet files,
  model-sweep bundles, and preparation bundles;
- order-preserving table previews fetched in bounded 500-row worker blocks and
  presented as local 100-row pages;
- workspace-local Validate/Generate job diagnostics and confirmed, guarded
  cleanup of recognized stale staging directories;
- inspection-driven, session-only plot-request editing for dataset sources;
- a private worker plot-rendering contract that uses existing visualization
  logic without thermodynamic backend calls;
- guarded no-overwrite promotion of one image and provenance sidecar into a
  worker-derived directory under the workspace `figures/` root;
- Plot-page format selection, manual Render controls, row/advisory reporting,
  and an informational equivalent CLI command;
- immediate confirmed force-stop with parent-owned staging cleanup and guarded
  close behavior;
- validated Qt-only PNG/SVG previews with fit, zoom, 100%, and panning
  controls; and
- explicit PDF opening through the system viewer.

Imported invalid YAML files remain untouched and must be repaired in a text
editor before import. Imported valid files also remain untouched until saved
under the selected workspace. Exact numeric visualization filters and series
levels remain explicit inputs; finite choices such as fields, fluids,
categorical values, units, formats, scales, and valid series dimensions are
provided by the editor.

Sweep and preparation creation remain reserved for GUI-2; GUI-1 inspects their
completed bundles read-only. NumPy and SafeTensors outputs are listed from the
preparation manifest but are not rendered as matrices. The Plot page can build
a compatible request from inspection results and render PNG, SVG, or PDF through
the worker. PNG and SVG exports preview automatically after containment,
symlink, regular-file, suffix, and SHA-256 checks. PDF exports remain closed
until the user selects **Open PDF** and the file passes the same checks again.
Preview failures do not remove successful image or sidecar exports.

Qt/PySide6 is an optional third-party dependency with its own
LGPL/GPL/commercial licensing terms. Carnopy remains MIT licensed, does not
vendor Qt, and does not distribute standalone desktop installers in GUI-1.
Downstream redistributors should review the official
[Qt for Python package details](https://doc.qt.io/qtforpython-6/package_details.html)
and [Qt licensing terms](https://doc.qt.io/qt-6/licensing.html). This is not
legal advice.

## Architecture map

The repository includes a generated Graphify codebase map:

```text
graphify-out/GRAPH_REPORT.md
graphify-out/graph.html
graphify-out/graph.json
```

Open `graphify-out/graph.html` locally after cloning for an interactive view.
The graph is an aid for navigation and review, not a source of scientific
truth. Verify exact behavior against the source files and tests before making
changes.

The currently committed graph predates active Stage 3 parity work and is
hard-stale for current desktop work. Do not use it to navigate the remaining
frontend migration. The computed freshness policy and current source revision
are recorded in
[`DESKTOP_ARCHITECTURE.md`](DESKTOP_ARCHITECTURE.md#maintenance-posture-and-navigation-freshness).

## Scientific limitations

- CoolProp is the only backend in Milestone 1.
- CoolProp model selection supports HEOS, Peng-Robinson, and
  Soave-Redlich-Kwong.
- Pure fluids only; mixtures are deferred.
- Generated data is backend output, not experimental evidence.
- All backend calls and generated numeric columns use SI.
- Specific enthalpy, entropy, and internal energy depend on reference state.
- Carnopy resets every requested fluid to CoolProp `DEF` before generation and
  records that policy.
- Preparation warns and records reference-state context when selected features
  or targets include absolute reference-dependent values.
- CoolProp reference-state mutation is process-global; concurrent embedded use
  with unrelated CoolProp calculations is unsupported in Milestone 1.
- Release regression tests compare finalized Parquet values with direct
  CoolProp calls for representative states in all three modes.
- Separate sanity checks require the generated normal boiling points of Propane
  and Cyclopentane at `101325 Pa` to remain within the uncertainty intervals
  published by the NIST Chemistry WebBook. These checks do not establish
  universal experimental accuracy.
- Absolute reference-dependent values are not directly comparable across
  different reference conventions or model/reference combinations.
- PR/SRK transport properties, surface tension, and triple-point temperature
  are rejected during validation because the cubic backends do not provide the
  required model capability.
- Visualization reads emitted columns only and is not a second property
  evaluation layer.
- ORC generation, additional backends, ML training, web services, databases,
  and mixture models are deferred.

Post-alpha work may add an optional cycle-feasibility subsystem that produces
traceable screening datasets without turning the property generator into a
hidden process simulator. An ORC/TFC contract must explicitly include source
and sink profiles, pinch/approach temperatures, pressure losses, component
efficiencies, subcooling and superheat margins, cavitation/NPSH constraints,
minimum turbine-exhaust quality, and critical/maximum operating limits.
Saturated liquid alone is not a pump cavitation margin, and turbine discharge
need not universally have vapor mass fraction one.

Official backend references:

- https://coolprop.org/coolprop/
- https://coolprop.org/coolprop/HighLevelAPI.html
- https://github.com/CoolProp/CoolProp

## Development and contribution

Carnopy uses a `src/` layout, Hatchling, standalone uv, Ruff, strict mypy, and
pytest. `pyproject.toml` and `uv.lock` are authoritative.

Normal development:

```bash
uv sync --locked --extra all --group dev
```

Release-readiness tooling:

```bash
uv sync --locked --extra all --group dev --group release
```

Quality gate:

```bash
uv lock --check
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src/carnopy
uv run --locked pytest
uv run --locked python scripts/preflight.py
uv pip check --python .venv/bin/python
```

Full local release gate, including a non-destructive build and distribution
inspection:

```bash
bash scripts/local_gate.sh prerelease/local-gate
```

Keep changes small and explicit. Public configuration names, semantic property
names, SI dataset columns, failure codes, metadata fields, and identity rules
are compatibility contracts. Tests use temporary output directories and do not
commit generated datasets or figures.

The test count is not a quality target. The suite separates configuration,
sampling, three thermodynamic modes, diagnostics, provenance, visualization,
CLI behavior, packaging, and release automation. New tests should protect a
distinct contract or regression and use parametrization instead of duplicating
equivalent cases.

Contributor and coding-agent rules, architecture constraints, commit
conventions, and release-maintainer safeguards are in
[AGENTS.md](https://github.com/gcalpay/carnopy/blob/main/AGENTS.md).
Contributor setup, testing, and pull-request guidance are in
[CONTRIBUTING.md](https://github.com/gcalpay/carnopy/blob/main/.github/CONTRIBUTING.md).
Report security vulnerabilities privately according to the
[security policy](https://github.com/gcalpay/carnopy/security/policy).

## Project status and roadmap

Carnopy remains alpha software while its public schemas and backend boundaries
are validated through real use. Version `0.1.0a3` includes GUI-1, a Linux-first
desktop frontend for the existing dataset workflow.

GUI-1 includes the worker protocol, workspace shell, dataset configuration
editor, dataset execution, read-only bundle inspection, bounded table previews,
job diagnostics, guarded staging recovery, inspection-driven plot requests,
worker-side backend-free rendering, safe no-overwrite artifact promotion,
desktop Render controls, confirmed force-stop/close ownership, Qt-only PNG/SVG
previews, explicit PDF opening, packaging inventory checks, installed-wheel
smoke coverage, release hardening, and final architecture-map review.

The prepared source now includes robust distribution reports, exact-state
split leakage protection, explicit-bin stratification, train-fitted robust
scaling, opt-in matrix diagnostics, and optional diagnostic-only scikit-learn
baselines. The
[ML preparation roadmap](https://github.com/gcalpay/carnopy/blob/main/ML_PREPARATION_ROADMAP.md)
separates current behavior from research directions. Carnopy remains a dataset
and preparation tool rather than a model-training framework.

A later pure-fluid ORC feasibility-envelope subsystem may produce traceable
accepted and rejected operating windows rather than silently acting as a
complete process simulator or optimizer.

That design must explicitly cover source and sink profiles, pinch and approach
temperatures, pressure losses, subcooling and superheat margins, equipment
efficiencies, critical-point and operating limits, and minimum turbine-exhaust
quality. Saturated liquid alone is not a pump cavitation margin; NPSH may be
reported only when sufficient hydraulic-system and pump data are supplied.

The active `0.1.0a4.dev0` application development line targets a cross-platform
modern QML presentation layer with tested GUI-1 capability parity. Both source
checkout desktop commands now launch that one QML frontend; the obsolete
Widgets presentation remains only until its next, separately verified removal
step. Optional native VTK exact-grid 3D visualization belongs to a later GUI-2
alpha milestone and is not required for `0.1.0a4`. GUI-2 uses the same worker
and core Python boundaries rather than duplicating scientific logic. TFC
screening, mixtures, additional backends, and standalone desktop installers
remain deferred.

Use [GitHub issues](https://github.com/gcalpay/carnopy/issues) for bug reports,
scientific discrepancies, and focused feature requests. See
[CONTRIBUTING.md](https://github.com/gcalpay/carnopy/blob/main/.github/CONTRIBUTING.md)
before proposing a public or scientific contract change.

## License

Carnopy is distributed under the MIT License. See `LICENSE`.
