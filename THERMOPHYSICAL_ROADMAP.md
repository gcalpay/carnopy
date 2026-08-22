# Carnopy thermophysical and simulation roadmap

## Purpose and status

This document records the public research direction beyond Carnopy's current
alpha contract. It separates potential sources, model families, backend
adapters, mixture capabilities, cycle workflows, and visualizations from
implemented behavior.

Every item below is planned direction or a candidate for evaluation, not a
supported capability or a public API commitment. A candidate may enter Carnopy
only through a separately reviewed scientific contract and implementation
stage with licensing, platform, validation, provenance, and distribution
qualification. The current behavior remains defined by
[`docs/agent-guides/SCIENTIFIC_CONTRACTS.md`](docs/agent-guides/SCIENTIFIC_CONTRACTS.md).

## Product direction

Carnopy should not compete by reproducing every equation of state, activity
model, process solver, or training framework. Established scientific engines
already provide broad and specialized numerical implementations. Carnopy's
distinct role is to make work across those engines reproducible and auditable:

- canonical source, component, composition, unit, model, and parameter
  identities;
- explicit validity domains, reference states, uncertainty, and failure
  evidence;
- immutable generation, import, comparison, cycle, and preparation outputs;
- aligned model-to-model and model-to-reference comparisons;
- inspection and visualization without inventing unsampled values; and
- exact handoffs to external simulation and machine-learning consumers.

Backend count is not a success measure. A new adapter is useful only when its
results can be identified, validated, compared, reproduced, packaged, and
explained at least as rigorously as current CoolProp runs.

## Recommended sequence

1. Establish a validated source/import contract, beginning with ThermoML.
2. Add binary mixtures through a schema designed for later multicomponent use.
3. Add model-to-reference validation, uncertainty-aware residuals, and
   parameter provenance.
4. Introduce TESPy-backed thermodynamic-cycle studies and cycle visualization.
5. Select one advanced property backend from measured workflow and scientific
   needs instead of adding several shallow adapters.
6. Add a PyTorch consumption adapter and identity-bound imported prediction
   evaluation as separately reviewed ML stages.
7. Consider electrolytes and specialized distributed-training integration only
   after a concrete scientific use case requires them.

This order is a planning guide, not a release schedule. Evidence may justify a
different sequence, but identity and validation contracts should precede broad
backend or model expansion.

## Admission criteria for scientific expansions

Every source, model, or simulator integration must define and test:

- canonical names and versioned capability discovery;
- unit, basis, sign, composition, phase, and reference-state conventions;
- model parameters, interaction parameters, and their source or citation;
- supported properties, state variables, phases, and validity domains;
- behavior for unsupported, invalid, nonconverged, metastable, and ambiguous
  states;
- uncertainty and method metadata when the source provides them;
- deterministic normalized configuration and stable scientific identities;
- complete software, database, backend, model, and artifact provenance;
- immutable outputs, no-overwrite finalization, and auditable diagnostics;
- license, redistribution, optional-dependency, platform, and maintenance
  constraints; and
- independent checks against published or authoritative reference cases.

Carnopy must not silently translate incompatible conventions, fill missing
scientific information, select an interaction parameter without provenance,
or present agreement between two models as experimental validation.

## Validated reference and experimental data

### ThermoML as the first import target

ThermoML is the strongest first interchange target because it is an IUPAC
standard for representing thermodynamic property data and associated metadata.
A reviewed import stage should preserve, where supplied:

- publication DOI and full citation;
- authors, laboratory, sample, and measurement method;
- reported variables, properties, units, constraints, and phases;
- component identities and composition basis;
- numeric values, uncertainty definitions, and coverage;
- data-quality notes, corrections, and source-record identity; and
- the exact imported bytes and normalized Carnopy representation.

The importer must not treat every record as equally suitable for validation.
Method, uncertainty, phase, composition, and domain compatibility must remain
visible so users can decide what constitutes relevant evidence.

### Comparison and validation products

Model-to-reference comparison should align only scientifically compatible
states and should produce both row-level evidence and aggregate summaries:

- signed and absolute residuals;
- relative residuals only where the denominator is scientifically meaningful;
- bias, mean absolute error, root mean squared error, maximum deviation, and
  average absolute relative deviation where applicable;
- uncertainty-normalized residuals when uncertainty semantics are compatible;
- coverage maps over temperature, pressure, composition, property, and phase;
- model and parameter rankings scoped to an explicit domain; and
- traceable exclusions for unmatched or incompatible records.

Parameter regression may be considered only after this comparison contract
exists. Fitted binary interaction or activity-model parameters must retain the
source records, objective, weighting, bounds, optimizer, convergence evidence,
software versions, covariance or uncertainty information when available, and
an immutable result identity. Fitted parameters must never silently replace a
backend default.

## Mixtures and phase equilibria

### Composition contract

Binary mixtures are the practical first milestone, but the normalized schema
should not assume that exactly two components will always exist. It should
support:

- ordered canonical component identities;
- mole and mass fractions, with volume fractions only when their reference
  conditions and semantics are explicit;
- normalization tolerances and the original declared composition;
- mixture, component, and phase composition bases;
- interaction parameters with model, source, units, version, and applicability;
- phase identities, phase fractions, and per-phase compositions; and
- stable identities that change when composition, basis, model, parameters, or
  reference context changes.

### Equilibrium and flash capabilities

Candidate mixture stages include:

- bubble-point and dew-point calculations;
- temperature-pressure, pressure-enthalpy, pressure-entropy, and quality flashes
  where the selected backend supports them;
- vapor-liquid and liquid-liquid equilibrium, followed later by
  vapor-liquid-liquid equilibrium where justified;
- phase envelopes, critical points and lines, and azeotrope evidence;
- stability, initialization, iteration, and convergence diagnostics; and
- explicit distinction between equilibrium, metastable, and failed states.

Backend capability discovery must decide which operations are available. QML,
CLI presentation, or generic list order must not guess scientific support.

## Property and equilibrium model families

The following families are evaluation candidates. Their names do not imply
that Carnopy will implement the mathematics itself.

| Family | Candidate models or standards | Primary scientific role and required caution |
| --- | --- | --- |
| Multiparameter and reference formulations | HEOS extensions, REFPROP formulations, IAPWS-IF97, GERG-2008 | High-accuracy fluid, water/steam, and natural-gas work; database version, mixture rules, validity domain, and reference state must be explicit. |
| Cubic and corresponding-states models | PR and SRK extensions, PRSV variants, Lee-Kesler-Plocker | Engineering calculations and comparison baselines; mixing rules, alpha functions, volume translation, and binary parameters are part of identity. |
| Molecular and associating equations of state | PC-SAFT, Cubic-Plus-Association (CPA), SAFT-VR Mie | Associating, polar, chain, and complex-fluid systems; parameter sets and association schemes require strong provenance. |
| Activity-coefficient and excess-Gibbs models | NRTL, UNIQUAC, Wilson, UNIFAC, Modified UNIFAC | Liquid-phase nonideality and phase-equilibrium calculations; component groups, temperature dependence, parameter directionality, and regression source must be retained. |
| Electrolyte models | Pitzer, electrolyte NRTL, Specific Ion Interaction Theory (SIT) | A separate electrolyte milestone requiring ion and species identities, concentration scales, reactions, charge balance, and solvent conventions. |
| Predictive mixture methods | UNIFAC variants and, after careful evaluation, COSMO-based approaches | Useful when fitted binary parameters are unavailable, but method version, group assignment, parameter database, and expected accuracy domain remain essential. |

NRTL, UNIQUAC, Wilson, and UNIFAC are not interchangeable equations of state.
They require an explicit phase-equilibrium framework and parameter contract.
CPA and PC-SAFT are especially relevant for associating and polar mixtures.
GERG-2008 is a natural-gas specialization, IAPWS-IF97 is a water and steam
industrial formulation, and Lee-Kesler is useful as an engineering benchmark.
Pitzer should not be folded into a generic fluid-mixture stage because aqueous
electrolytes add species, reaction, concentration, and electroneutrality
requirements.

## Backend adapter candidates

| Candidate | Potential value | Evaluation boundary |
| --- | --- | --- |
| CoolProp mixture and PC-SAFT capabilities | Lowest-friction extension of the current backend and worker boundary. | Qualify supported mixtures, models, flashes, parameters, and failure behavior per operation rather than assuming feature parity with pure-fluid HEOS. |
| NIST REFPROP | Authoritative high-accuracy pure-fluid and mixture formulations for many engineering uses. | Optional user-managed licensed installation only. Carnopy must not redistribute REFPROP and must record database version, fluid files, model, reference state, and capabilities. |
| ThermoPack | Broad multicomponent and multiphase engine with cubic, CPA, PC-SAFT, SAFT-VR Mie, Lee-Kesler, GERG, flash, envelope, and critical-point capabilities. Its Apache-2.0 license and current Windows, Linux, and macOS Python distribution make it a strong candidate. | Reverify license and platform artifacts at adoption, then evaluate ABI stability, thread/process behavior, numerical validation, and long-term adapter maintenance. |
| NIST teqp | Modern library for advanced Helmholtz-energy mixture models, CPA, PC-SAFT, SAFT-VR Mie, Lee-Kesler-Plocker, GERG, critical curves, phase equilibria, and fitting. | Define a narrow supported subset and stable parameter/model identities instead of exposing an unrestricted backend object model. |
| `thermo` | Python implementations of NRTL, UNIQUAC, UNIFAC and multiphase flash workflows. | Qualify model databases, parameter sources, flash algorithms, performance, dependency impact, and exact supported use cases. |

Selection must follow a concrete user workflow and comparison corpus. License,
platform reach, scientific coverage, deterministic configuration, failure
evidence, and maintenance cost matter more than the length of the feature list.

## Thermodynamic-cycle studies

Cycle support is an explicit future direction. Carnopy should wrap qualified
simulation engines and own reproducible configuration, execution records,
comparison, inspection, visualization, provenance, and ML handoff. It should
not become an unbounded general-purpose process solver.

### Candidate cycle families

- Rankine, organic Rankine, and trilateral flash cycles;
- vapor-compression refrigeration cycles;
- heat-pump cycles;
- Brayton and recuperated Brayton cycles;
- combined and cascade cycles after the component and topology contracts are
  proven; and
- reacting or propulsion cycles only through later specialized adapters.

### Minimum cycle result contract

A cycle run must retain:

- ordered topology, streams, ports, component types, and connectivity;
- boundary conditions and design or off-design mode;
- working fluid, composition, property backend, model, parameters, and
  reference state;
- compressor, turbine, pump, and other component efficiencies;
- heat-exchanger approaches, pressure losses, ambient assumptions, and other
  declared component parameters;
- solver settings, initialization, convergence, residual, warning, and failure
  evidence;
- state points with stable stream and component identities;
- mass, energy, entropy, and, where supported, exergy balances;
- heat duties, shaft powers, net power, efficiency, and coefficient of
  performance with explicit sign and unit conventions; and
- exact engine, adapter, configuration, artifact, and software provenance.

Current p-v and T-s plots connect emitted sampled states only within their
existing visualization contract. They cannot be relabeled as cycle diagrams.
Cycle visualization requires an ordered process topology and states accepted
through a new typed result contract.

### Simulation-engine candidates

- **TESPy** is the strongest first Python adapter candidate. Its MIT license and
  Python workflow fit Carnopy's optional-adapter boundary, and it covers power
  plants, heat pumps, refrigeration systems, Rankine and gas-turbine cycles,
  exergy analysis, and property-diagram integration.
- **pyCycle** is a later candidate for jet-engine and propulsion cycle studies
  through the OpenMDAO ecosystem.
- **Cantera** is a later candidate for reacting thermodynamics and reactor
  networks rather than ordinary nonreacting property tables.
- **IDAES** is a later candidate for full process flowsheets and optimization
  when a use case needs that broader process-modeling scope.

Each adapter must remain optional and worker-owned. Carnopy configuration and
results should not expose mutable engine objects as public scientific state.

## Visualization direction

Future views should remain projections of verified imported or generated
artifacts. Candidate views include:

- temperature-composition (T-x-y), pressure-composition (P-x-y), and
  liquid-vapor composition (x-y) diagrams;
- binary and ternary composition views;
- bubble, dew, critical, and phase envelopes;
- model-to-reference parity, residual, and uncertainty plots;
- residual surfaces over temperature, pressure, composition, and phase;
- validity-domain and source-coverage maps;
- T-s, p-h, h-s, and p-v cycle diagrams based on ordered cycle results;
- component energy, entropy, and exergy views;
- sensitivity and working-fluid comparisons;
- Preparation partition, coverage, and leakage-diagnostic views; and
- imported ML prediction parity, residual, error-domain, learning-curve, and
  uncertainty-calibration views.

Visualization must preserve missing data, phase boundaries, uncertainty,
source identity, and failures. Interpolation, smoothing, derived envelopes, or
topological paths require an explicit scientific contract and must never be
introduced as presentation-only conveniences.

## Relationship to ML Preparation

Future source, mixture, and cycle outputs should expose machine-readable
coordinates, properties, units, compositions, phases, domain masks,
derivatives or constraints when genuinely available, and complete provenance.
Preparation can then consume those verified fields without calling the
originating scientific backend. Framework adapters, prediction-result imports,
metrics, and result visualization are detailed in
[`ML_PREPARATION_ROADMAP.md`](ML_PREPARATION_ROADMAP.md).

## Primary references for candidate evaluation

- IUPAC, [ThermoML](https://iupac.org/what-we-do/digital-standards/thermoml/).
- NIST Thermodynamics Research Center,
  [ThermoML](https://www.nist.gov/mml/acmd/trc/thermoml) and the
  [ThermoML Archive](https://www.nist.gov/mml/acmd/trc/thermoml/thermoml-archive).
- CoolProp, [Mixtures](https://coolprop.org/fluid_properties/Mixtures.html) and
  [Backends](https://coolprop.org/develop/backends.html).
- NIST, [REFPROP](https://www.nist.gov/programs-projects/reference-fluid-thermodynamic-and-transport-properties-database-refprop).
- ThermoPack, [documentation](https://thermotools.github.io/thermopack/vcurrent/method_docs.html)
  and [source repository](https://github.com/thermotools/thermopack).
- NIST, [teqp documentation](https://pages.nist.gov/teqp-docs/en/stable/index.html).
- `thermo`, [activity-coefficient models](https://thermo.readthedocs.io/activity_coefficients.html)
  and [phase and flash workflows](https://thermo.readthedocs.io/tutorial_phases_and_flash.html).
- USGS PHREEQC, [Pitzer model documentation](https://water.usgs.gov/water-resources/software/PHREEQC/documentation/phreeqc3-html/phreeqc3-37.htm).
- TESPy, [documentation](https://tespy.readthedocs.io/en/main/documentation.html)
  and [source repository](https://github.com/oemof/tespy).
- OpenMDAO, [pyCycle](https://github.com/openmdao/pycycle).
- Cantera, [reactor networks](https://cantera.org/stable/reference/reactors/index.html).
- IDAES, [process systems engineering framework](https://idaes.org/software/).
