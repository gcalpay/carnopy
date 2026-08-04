# Carnopy product scope and direction

## Purpose and authority

This document is the durable public source of truth for Carnopy's product
identity, ecosystem position, long-term boundaries, and prioritization. It
explains what Carnopy is intended to become without presenting every direction
as an implemented feature or release promise.

Current scientific behavior, schemas, interfaces, and compatibility contracts
remain authoritative in
[`docs/agent-guides/SCIENTIFIC_CONTRACTS.md`](docs/agent-guides/SCIENTIFIC_CONTRACTS.md).
Implemented desktop ownership remains authoritative in
[`DESKTOP_ARCHITECTURE.md`](DESKTOP_ARCHITECTURE.md), and unfinished GUI-2 work
remains tracked in [`GUI2_PLAN.md`](GUI2_PLAN.md). The
[`ML_PREPARATION_ROADMAP.md`](ML_PREPARATION_ROADMAP.md) gives the more detailed
preparation roadmap.

Roadmap entries here require their own reviewed implementation plan before they
change a public API, schema, dependency, output, or scientific contract.

## Product position

Carnopy is an open and auditable thermophysical-data workbench. It helps people
define, generate or import, compare, inspect, visualize, prepare, and export
thermophysical data without hiding where values came from or silently repairing
invalid states.

Carnopy is broader than a dataset generator and narrower than a general
thermodynamic, process-simulation, or machine-learning platform. Its durable
value is the trustworthy workflow around scientific sources:

- explicit configuration and deterministic previews;
- source-aware execution, normalization, and comparison;
- immutable artifacts, provenance, diagnostics, and stable identities;
- bounded inspection and scientifically honest visualization;
- leakage-aware preparation and framework-consumption exports; and
- consistent behavior across the CLI, Python API, and desktop workbench.

Thermodynamic engines remain responsible for their property models. Training
frameworks remain responsible for model execution. Carnopy owns the auditable
data path between them.

## Ecosystem boundary

```text
CoolProp / FeOS / thermo / REFPROP / future data sources
                            ↓
Carnopy
configure · preview · generate/import · compare · inspect
visualize · prepare · export · audit
                            ↓
reproducible dataset bundles and framework adapters
                            ↓
Pinntropy or external training applications
problems · constraints · models · training · GPU execution
experiments · checkpoints · validation · deployment
                            ↓
PyTorch / DeepXDE / PhysicsNeMo
```

The names in the first and last rows describe ecosystem roles, not current
support promises. CoolProp is the only implemented thermophysical backend.
PyTorch, DeepXDE, and PhysicsNeMo are consumers or execution frameworks, not
Carnopy's scientific authority.

Pinntropy is reserved for a possible future thermodynamics-informed training
product. Carnopy does not depend on it, and no Pinntropy capability is promised
until it has a differentiated problem and reviewed boundary. A future
integration may present a connected user experience while retaining separate
packages, dependencies, contracts, and release decisions.

## Durable Carnopy responsibilities

### Configuration and workbench

Carnopy owns portable configuration, deterministic YAML preview, validation,
execution planning, workspace organization, progress and cancellation at
reviewed boundaries, immutable outputs, inspection, and recovery. A desktop
surface must remain a presentation of the same scientific core rather than a
second implementation.

### Sources, generation, and comparison

Carnopy may grow from CoolProp to additional thermophysical libraries,
licensed local engines, simulation outputs, and user-supplied, experimental,
or operational data. Every source requires an explicit capability,
provenance, uncertainty, licensing, identity, validity, and comparison
contract. An adapter does not turn backend output into experimental truth.

Thermodynamic-model sweeps belong in Carnopy because they compare source models
over aligned states. Machine-learning architecture or hyperparameter sweeps do
not; those belong to the training application consuming a Carnopy bundle.

### Inspection and visualization

Visualization is a first-class product capability, not decorative output. It
helps users find invalid regions, sparse or misleading sampling, phase changes,
scale problems, model disagreement, leakage risks, and preparation defects.

The durable visualization direction includes:

- scientifically meaningful grids, subgrids, facets, and state grouping;
- clear titles, axis labels, symbols, units, unit spacing, legends, and
  colorbars;
- explicit and validated linear or logarithmic scales and honest zoom/context;
- readable density, contrast, typography, and color choices;
- visible missing, invalid, ambiguous, and phase-discontinuous regions;
- deterministic 2D and exact emitted-value 3D views; and
- source identity, filters, transformations, scale choices, and artifact hashes
  in figure provenance.

Visualization must not silently interpolate, smooth, extrapolate, resample, or
invent thermodynamic states. The scientific contracts define the exact current
renderer behavior.

### Preparation and consumption

Carnopy owns deterministic splitting, leakage prevention, transformations,
curated features, interpretable diagnostics, canonical prepared tables, and
derived consumption formats. Parquet remains the canonical structured prepared
data; NumPy, SafeTensors, and future framework-specific artifacts are derived
views whose columns, units, dtypes, shapes, vocabularies, conversions, and
hashes remain manifest-backed.

Framework compatibility does not move training into Carnopy. A PyTorch-ready
dataset, loader adapter, or tensor artifact is a data interface. Models,
losses, optimizers, epochs, GPU orchestration, experiment tracking,
checkpoints, inference services, and deployment are training responsibilities.

### Automation integrations

A Carnopy skill or MCP server may be considered after the underlying public
workflows are mature enough to expose stable, permission-conscious operations.
Such an integration must call the same public contracts, preserve explicit
paths and no-overwrite behavior, distinguish reads from writes, and avoid
turning a conversational interface into a second scientific implementation.

## Roadmap classification

The status labels below are intentional:

- **Implemented** means present in current source and governed by current
  contracts.
- **Approved next** means selected for the next separate implementation stage,
  but not yet available.
- **Planned, unscheduled** means aligned with the product direction but neither
  sequenced nor promised for a release.
- **Research candidate** means evidence or design work is still required.
- **External** means intentionally owned by a consuming application or
  framework rather than Carnopy core.

| Status | Capabilities |
| --- | --- |
| Implemented | CoolProp pure-fluid generation with HEOS/PR/SRK; YAML init/preview/validation; immutable CSV/Parquet runs; thermodynamic-model sweeps; provenance and inspection; emitted-column 2D visualization; leakage-aware preparation; NumPy, NPZ, and SafeTensors exports; diagnostic baselines; CLI, Python, and QML workbench surfaces documented by the current contracts |
| Approved next | Optional PyTorch dataset export from preparation: one manifest-backed CPU tensor dictionary written as `.pt`, with no `.pth` duplicate and no training objects |
| Planned, unscheduled | Additional thermophysical backends; licensed local-engine adapters; validated user, experimental, operational, and simulation-source imports; richer reviewed sampling; desktop sweep and preparation workflows; exact emitted-value 3D scenes and native interaction |
| Research candidate | Active-learning generation, additional consumption formats with demonstrated consumers, multidimensional labelled-data models, advanced phase-safe diagnostics, and a mature skill/MCP boundary |
| External | Problem definitions, physical constraints, neural-network architectures, training and ML hyperparameter sweeps, GPU/distributed execution, experiments, model checkpoints, production validation, inference services, and deployment |

## Approved next stage: PyTorch dataset export

The next functional stage after this documentation reset is an optional
PyTorch consumption export. Its reviewed direction is:

- add `pytorch` as a preparation array-output format;
- write one `.pt` file containing only CPU tensors for features, targets, and
  explicitly requested auxiliary arrays;
- do not emit a duplicate `.pth` file, custom Python objects, models,
  optimizers, or checkpoints;
- retain semantic metadata in the existing JSON manifest and preserve Parquet
  as canonical;
- document loading on CPU with restricted `weights_only=True` behavior;
- isolate PyTorch in a dedicated optional dependency extra, leaving the base
  and existing `ml` installation independent; and
- qualify dependency availability against Carnopy's supported Python and
  platform matrix before changing packaging.

This direction is not an implemented interface until its separate stage is
accepted and the current contracts, templates, package metadata, and tests are
updated together.

## Sequencing

1. Establish and synchronize this product-scope authority.
2. Implement and qualify the optional PyTorch dataset export as a separate
   stage.
3. Reassess GUI-2 Stage 4 against the accepted product direction and current
   user workflow before resuming it.

GUI-2 Stage numbers remain stable. Deferral does not cancel their reviewed
technical content or imply that a later stage may bypass its dependencies.

## Licensing and sustainability gate

The Carnopy alpha line is distributed under the MIT License. Already published
versions retain the terms under which they were released. This document does
not promise that every future major release will use MIT and does not announce
a license change.

Before either the first stable release (`0.1.0` under the current versioning
plan) or acceptance of a substantial external contribution, whichever comes
first, the maintainer must review:

- Carnopy's sustainability and business model;
- the intended balance between adoption, reciprocity, and commercial use;
- copyright ownership and contribution governance;
- dependency and distribution-license compatibility; and
- synchronized treatment of repository, package, release, citation, and
  archival metadata.

Any license change is a separately reviewed legal and governance event. It is
not an ordinary documentation or packaging edit.
