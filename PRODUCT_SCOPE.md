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

### Relationship to backend-owned graphical tools

CoolProp 8 includes a native desktop GUI centered on point-property lookup,
saturation tables, and humid-air calculation and plotting. That tool remains a
frontend for CoolProp itself; its existence is not a reason for Carnopy to
duplicate calculator tabs or compete on direct property-query breadth. See the
[CoolProp GUI implementation](https://github.com/CoolProp/CoolProp/pull/2715)
and [CoolProp changelog](https://coolprop.org/coolprop/changelog.html).

Carnopy must differentiate through the workflow around scientific sources:
reproducible batch specifications, immutable dataset bundles, model-aligned
comparison, provenance, diagnostics, emitted-value visualization,
leakage-aware preparation, and explicit consumption exports. A desktop feature
that merely reproduces a backend calculator is not product progress unless it
serves that auditable workflow.

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
- **Planned, sequenced** means its relative order is accepted, but its public
  contract, implementation stage, and release are not yet approved.
- **Planned, unscheduled** means aligned with the product direction but neither
  sequenced nor promised for a release.
- **Research candidate** means evidence or design work is still required.
- **External** means intentionally owned by a consuming application or
  framework rather than Carnopy core.

| Status | Capabilities |
| --- | --- |
| Implemented | CoolProp pure-fluid generation with HEOS/PR/SRK; YAML init/preview/validation; immutable CSV/Parquet runs; thermodynamic-model sweeps; provenance and inspection; emitted-column 2D visualization; leakage-aware preparation; NumPy, NPZ, and SafeTensors exports; diagnostic baselines; CLI, Python, and QML workbench surfaces documented by the current contracts |
| Approved next | GUI-2 Stage 4: controlled desktop worker operations for existing model-sweep and preparation capabilities, without changing their public scientific schemas or output layouts |
| Planned, sequenced | GUI-2 Stage 5 structured sweep and preparation QML workflows; then a validated source/import capability contract and one concrete source-breadth expansion selected from demonstrated user needs |
| Planned, unscheduled | Optional manifest-backed PyTorch `.pt` export; richer reviewed sampling; exact emitted-value 3D scenes and native interaction; later automation integrations |
| Research candidate | CoolProp mixtures; `thermo` activity-coefficient workflows; licensed REFPROP integration; CPA/PC-SAFT support; active-learning generation; additional consumption formats with demonstrated consumers; multidimensional labelled-data models; advanced phase-safe diagnostics; and a mature skill/MCP boundary |
| External | Problem definitions, physical constraints, neural-network architectures, training and ML hyperparameter sweeps, GPU/distributed execution, experiments, model checkpoints, production validation, inference services, and deployment |

## Source and advanced-model horizons

The accepted product order is **workflow depth now, source breadth next,
advanced model breadth later**.

Workflow depth means exposing the already implemented sweep and preparation
contracts through the desktop without creating a second scientific
implementation. Source breadth then begins with a reviewed capability and
import contract covering semantics, units, identity, uncertainty, licensing,
validity, provenance, and comparison. A validated tabular import path for
user-supplied, experimental, operational, or simulation data is the preferred
first proof that Carnopy is a source-aware workbench rather than a CoolProp
frontend. One additional computational source may follow when a concrete user
workflow justifies it.

Advanced thermodynamic families require separate scientific milestones. The
following candidates are preserved for future planning; their order is not a
support promise or an implementation ranking.

| Candidate | Product reason | Required scientific gate |
| --- | --- | --- |
| CoolProp mixtures | Moderate scientific expansion while retaining the current engine and provenance family | Composition and mixture identity, interaction parameters, phase behavior, validity domains, aligned-state comparison, and reference-state contracts |
| `thermo` with NRTL or UNIQUAC | Mixture VLE/LLE workflows using parameterized activity-coefficient models | Phase-equilibrium schemas, parameter source and regression provenance, composition bases, applicability ranges, convergence diagnostics, and validation cases |
| REFPROP integration | Professional reference-property workflows using a licensed local engine | User-managed installation and license boundaries, non-redistribution, version and fluid identity, reference-state compatibility, capability discovery, and platform qualification |
| CPA or PC-SAFT | Advanced associating-fluid and molecular equation-of-state work | A dedicated model-family milestone with selected source ownership, parameter provenance, domain-specific validation datasets, numerical-failure contracts, and comparison policy |

No candidate should be introduced merely to increase a backend or model count.
The implementation plan must identify the user workflow, authoritative source,
validation evidence, schema impact, optional dependencies, and maintenance
boundary first.

## Reviewed future stage: Optional PyTorch dataset export

An optional PyTorch consumption export remains a reviewed, bounded future
direction, but it no longer defines the next product stage. Its artifact remains
one manifest-backed CPU tensor dictionary written as `.pt`, with no `.pth`
duplicate and no training objects, governed by these constraints:

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

This direction is not an implemented interface until a concrete consumer
justifies its separate stage and the current contracts, templates, package
metadata, and tests are updated together.

## Sequencing

1. Establish and synchronize this product-scope authority.
2. Implement GUI-2 Stage 4 worker operations for the existing sweep and
   preparation contracts.
3. Complete the visible workflow-depth milestone through GUI-2 Stage 5 QML
   sweep and preparation workflows after Stage 4 acceptance.
4. Plan source breadth through a validated import/source capability contract,
   then select one concrete source expansion from demonstrated user needs.
5. Consider advanced mixture and model families only through dedicated
   scientific stages with suitable validation evidence.

The optional PyTorch export may be accepted as a bounded independent stage when
a concrete consumer makes it worthwhile, but it does not preempt workflow or
source depth by default. Exact 3D and native interaction remain valid later
directions rather than the current differentiator.

GUI-2 Stage numbers remain stable. Reprioritization does not cancel their
reviewed technical content or imply that a later stage may bypass its
dependencies.

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
