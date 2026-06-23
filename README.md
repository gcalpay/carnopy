# Carnopy

[![PyPI](https://img.shields.io/pypi/v/carnopy.svg)](https://pypi.org/project/carnopy/)
[![Python](https://img.shields.io/pypi/pyversions/carnopy.svg)](https://pypi.org/project/carnopy/)
[![Verify](https://github.com/gcalpay/carnopy/actions/workflows/ci.yml/badge.svg)](https://github.com/gcalpay/carnopy/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Synthetic thermophysical property dataset generation from thermodynamic
databases and simulation backends for physics-informed ML surrogate models.

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

## Installation

Install the current alpha:

```bash
python -m pip install "carnopy==0.1.0a2"
```

Install optional plotting support:

```bash
python -m pip install "carnopy[all]==0.1.0a2"
```

For an isolated CLI:

```bash
uv tool install "carnopy==0.1.0a2"
uv tool install "carnopy[all]==0.1.0a2"
```

The base package supports generation and validation. The `viz` and `all` extras
install Matplotlib for manual or configured figure generation. PyArrow remains
a core dependency because Parquet is a supported first-class output format.

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
init → edit → optional validate → generate → inspect → optional plot
```

For repository development:

```bash
uv sync --locked --extra all --group dev
uv run --locked carnopy --help
```

## Guide

- [Workflow details](#workflow-details)
- [Configuration](#configuration)
- [Properties](#properties)
- [Visualization](#visualization)
- [Generated artifacts and provenance](#generated-artifacts-and-provenance)
- [Python API](#python-api)
- [Scientific limitations](#scientific-limitations)
- [Development and contribution](#development-and-contribution)
- [Project status and roadmap](#project-status-and-roadmap)

## Workflow details

```text
init → edit → optional validate → generate → inspect → optional plot
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

Available modes:

```text
property_table
saturation_table
vapor_mass_fraction_table
model_sweep
```

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
fluids: [Propane]

grid:
  temperature:
    kind: linspace
    start: 20
    stop: 100
    num: 5
    unit: degC
  pressure:
    kind: linspace
    start: 1
    stop: 20
    num: 5
    unit: bar

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
visualization:

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
```

Stage 4 comparison plots are one-fluid, one-property, one-x-axis side-by-side
model comparisons. Multiple fluids require multiple plot entries.

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
pressure: Pa, kPa, MPa, bar
vapor_mass_fraction: "1"
```

All backend calls and generated numeric columns use SI. Original units and
sampler definitions remain recorded in metadata.

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

## Generated artifacts and provenance

Each immutable run contains the selected dataset files plus mandatory
provenance artifacts:

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
  are rejected during validation because CoolProp 7.2.0 does not provide the
  required model capability.
- Visualization reads emitted columns only and is not a second property
  evaluation layer.
- ORC generation, additional backends, ML training, GUI, web services,
  databases, and mixture models are deferred.

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
are validated through real use. The next substantive milestone is a separately
designed pure-fluid ORC feasibility-envelope subsystem. It will produce
traceable accepted and rejected operating windows rather than silently acting
as a complete process simulator or optimizer.

That design must explicitly cover source and sink profiles, pinch and approach
temperatures, pressure losses, subcooling and superheat margins, equipment
efficiencies, critical-point and operating limits, and minimum turbine-exhaust
quality. Saturated liquid alone is not a pump cavitation margin; NPSH may be
reported only when sufficient hydraulic-system and pump data are supplied.

Deferred work includes TFC screening, mixtures, 3D visualization, and a PySide6
desktop interface. These capabilities will use the same core Python API rather
than duplicate scientific logic.

Use [GitHub issues](https://github.com/gcalpay/carnopy/issues) for bug reports,
scientific discrepancies, and focused feature requests. See
[CONTRIBUTING.md](https://github.com/gcalpay/carnopy/blob/main/.github/CONTRIBUTING.md)
before proposing a public or scientific contract change.

## License

Carnopy is distributed under the MIT License. See `LICENSE`.
