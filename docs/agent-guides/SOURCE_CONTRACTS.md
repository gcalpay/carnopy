# SOURCE-1 evidence, comparison, and preparation contracts

## Status and authority

This is the accepted implementation contract for SOURCE-1. Development source
now implements SOURCE-1.1A's Python import preview, described below. Bundle
creation, comparison, collections, and source desktop pages remain planned.
SOURCE-1.0 establishes the full program's contracts; the checkpoint ledger and
qualification matrix live in
[SOURCE_IMPORT_PLAN.md](../../SOURCE_IMPORT_PLAN.md).

Read this guide with [the current scientific contracts](SCIENTIFIC_CONTRACTS.md),
the active SOURCE-1 checkpoint, and, for desktop work,
[DESKTOP_ARCHITECTURE.md](../../DESKTOP_ARCHITECTURE.md). Existing generation,
sweep, Preparation v1, and GUI-2 contracts remain authoritative for their
implemented behavior. SOURCE-1 introduces separate source kinds; it must not
make experimental observations impersonate generated dataset rows.

## Implemented SOURCE-1.1A preview

`preview_source_import(source, *, config)` reads a local file and exact import
YAML, returning a frozen `ImportPreview`. It creates no output, uses no network
or thermodynamic backend, and imports no scientific/data or Qt runtime.
`ImportConfig` and `ImportSelection` are frozen public configuration models;
`SourceImportError` is a `ConfigError` with stable `code` and `locator` fields.

```yaml
schema_version: 1
document_type: source_import
format: thermoml_xml  # or thermoml_json
selections: []        # all datasets/properties
```

Explicit selections use `dataset_index` (zero-based source dataset order,
including unsupported reaction datasets) and optional `property_numbers`
(reported integer property identifiers). For example,
`selections: [{dataset_index: 0, property_numbers: [1]}]`. An empty property
list selects all properties of that dataset. Duplicate or unknown selections,
extra configuration fields, YAML duplicate keys, and aliases fail explicitly.
Source paths are invocation inputs, never YAML fields.

The preview reports format/profile, source and configuration descriptors,
document/publication/request/context identities, per-dataset and overall
`eligible`/`unsupported`/`invalid`/`unselected` counts, reasons, and warnings.
It exposes at most 500 selected dataset summaries, 500 selected records, and
500 document diagnostics. Dataset property-number lists are also capped at
500; record display text at 1,024 characters. Omission/truncation fields are
explicit; complete evidence and exact bytes remain in the private plan.
`as_dict()` returns an independent JSON-compatible projection. The outcomes
are `ready_with_limitations` or `no_eligible_observations` in this first profile;
unclassified data origin always remains visible. Eligibility is prospective
density normalization eligibility, not a written or independently validated
observation.

The implemented subset qualifies direct mass/amount density with `RegNum` /
`nOrgNum` component references, pure substances or two identified components,
and single liquid/gas/broad-fluid phases. Mole and mass fractions may be
variables or constraints. Exact rational arithmetic checks state conflicts and
precision-supported fraction sums without rescaling reported evidence. Missing
T/P is disclosed separately from measurement eligibility. Alternative component
locators, ternary/reaction data, unsupported quantities/presentations/qualifiers,
and equilibrium contexts remain raw evidence with unsupported accounting.
Uncertainty and sample/method metadata are retained; uncertainty conversion and
data-origin qualification remain subsequent normalization work.

The readers enforce the resource profile in the active plan before completing
parse. Local integer identifiers accept at most 20 source characters; reported
precision accepts 1–1,024 significant digits. Unqualified precision and
nonfinite or nonrepresentable values cannot become eligible. NIST JSON must
have complete, unique `tml_elements` ordering and UTF-8 encoding; numeric
lexemes are preserved without a binary64 decoding step. Namespace/schema
locations do not trigger downloads. This remains subset validation, not XSD
conformance certification.

Reads reject symlinks, nonregular files, replacement, mutation, and oversize
input. The private cancellable plan revalidates both files after parsing and
can check a previously accepted preview's exact bindings. No preview can
publish a bundle; protected finalization belongs to SOURCE-1.1B.

## Evidence and eligibility — SOURCE-1.0A

### Source scope

The first adapters accept local ThermoML XML and the corresponding NIST archive
JSON representation. Both feed one evidence model. JSON support is specific to
that representation, not arbitrary JSON tables. ThermoML's namespace and
recognized structural definitions determine support; a document's reported
Version must be preserved and must not be mistaken for a Carnopy schema version.
The adapters validate the supported subset rather than claiming full XSD
validation. Neither adapter downloads schemas or resolves external resources.

The [NIST archive description](https://www.nist.gov/publications/towards-improved-fairness-thermoml-archive)
documents the two serializations. [The ThermoML schema](https://trc.nist.gov/ThermoML.xsd)
is the authority for their scientific terms. Preserve original bytes even when
only part of the document can be normalized.

SOURCE-1.1 normalizes direct density observations for pure substances and binary
mixtures. SOURCE-1.2 adds the property families below. Reactions, more than two
components, unsupported property presentations, and other unqualified families
remain identifiable limitations. Equilibrium observations enter the supported
subset only in SOURCE-1.8.

| Quantity family | Canonical SI basis | First milestone |
| --- | --- | --- |
| Mass density | kg/m^3 | SOURCE-1.1 |
| Amount density | mol/m^3 | SOURCE-1.1 |
| Heat capacity at constant pressure or constant volume | J/(kg K) or J/(mol K), kept distinct | SOURCE-1.2 |
| Dynamic viscosity | Pa s | SOURCE-1.2 |
| Kinematic viscosity | m^2/s | SOURCE-1.2 |
| Thermal conductivity | W/(m K) | SOURCE-1.2 |
| Speed of sound | m/s | SOURCE-1.2 |

Temperature and pressure coordinates normalize to K and Pa. Composition is
dimensionless with an explicit basis. A mass-specific quantity must not become
a molar quantity through a unit-label change. Heat capacity at saturation,
excess/partial/apparent quantities, ideal-gas quantities, and logarithmic or
relative presentations are different semantics, not aliases for this table.
Absolute enthalpy, entropy, and internal-energy comparison and rebasing are
outside SOURCE-1's initial property set.

### Identity, citations, and source order

Keep these identities separate:

| Identity | Meaning |
| --- | --- |
| `source_document_id` | SHA-256 of the exact imported bytes |
| `dataset_id` | Versioned digest of document identity and the dataset's source locator |
| `point_id` | Versioned digest of dataset identity and the original `NumValues` position |
| `observation_id` | Versioned digest of point identity and the declared property number |
| `publication_id` | Normalized DOI when present; otherwise an explicitly recorded publication grouping identity |
| `request_id` | Digest of normalized options and ordered input scientific identities |
| `context_id` | Digest including request, adapter/schema versions, and relevant runtime/model evidence |
| `run_id` | UUID4 for one execution attempt |
| Artifact SHA-256 | Exact serialized file bytes, independent of logical row identity |

Use the existing canonical JSON and SHA-256 helpers with a versioned identity
domain for new digests. Local paths, filenames, timestamps, table sorting, and
the selected plotting presentation are not scientific identities.

Source locators retain zero-based dataset/point positions and the reported
dataset, component, variable, and property numbers where supplied. A missing
optional dataset number does not erase the ordinal locator. Duplicate declared
identifiers or broken references cannot be repaired by choosing the first
match. Preserve source dataset, point, and property order in normalized output.

Equivalent XML and JSON may have different byte and row identities. Compare
their normalized scientific content in qualification; never assert that the
files or their observation IDs are identical. Semantic duplicate candidates
are separate evidence, not permission to collapse rows.

Preserve DOI, full citation, authors, reported laboratory, sample and purity
information, methods, data-origin classification, notes, and corrections when
present. Missing information remains explicitly unavailable. Do not infer that
a property is experimental from the container format, its title, or an archive
URL. Report predicted, critically evaluated, and unknown origins distinctly;
the experimental comparison/ML workflow selects experimental evidence.

The [NIST ThermoML description](https://www.nist.gov/mml/acmd/trc/thermoml)
distinguishes accurate representation from critical evaluation. Carnopy's
structural validation, artifact integrity, model agreement, and scientific
quality assessment must likewise remain distinct. Retain supplied rights,
attribution, retrieval URL, and retrieval time; an unavailable license remains
unavailable rather than being replaced with Carnopy's software license.

### Observations, coordinates, and normalization

One canonical observation represents one reported property value at one source
point. Repeated measurements remain separate even when coordinates and values
are equal. Multiple reported properties may share a `point_id`; this is the
only automatic wide-row join authority. Equal coordinates, publication, or
rounded values do not establish that measurements were made together.

Resolve variables, property definitions, constraints, component references,
sample references, and phase references before normalization. Dataset-wide
constraints apply to their declared scope. A variable and constraint that give
incompatible definitions or values produce a diagnostic, not precedence by
parser order. Missing pressure must not default to atmospheric pressure.

For every normalized value retain its original numerical representation,
reported precision/digits, original quantity/unit/basis, source locator, and
conversion evidence. Normalize exact decimal scale/offset conversions before
the final binary64 projection; record the canonical value and any required
representation conversion. NaN and infinity cannot become eligible numeric
observations. Do not invent uncertainty from the number of reported digits.

Keep three eligibility decisions independent:

- **Normalization:** the reported quantity and its required scientific context
  are unambiguous and can be represented in the supported evidence model.
- **Comparison:** the selected model can evaluate a compatible property at the
  recorded state, composition, phase, and parameter context.
- **Preparation:** the explicitly requested features, targets, auxiliaries,
  transformations, and partition policy can be produced from finalized data.

A missing CoolProp mapping does not block import or inspection. Missing state
coordinates may block comparison without erasing a known measured property.
Unusable uncertainty does not erase an otherwise interpretable value, but it
blocks metrics that require that uncertainty. Do not reuse generated `valid`,
`backend_phase`, or failure fields to claim experimental validity.

### Components and composition

Retain source component order, local component/sample references, exact
reported names, and structural identifiers such as InChI/InChIKey and CAS when
supplied. Cross-document identity must be supported by unambiguous identifiers
or an explicit recorded mapping; a name match alone is not chemical identity.
Conflicting identifiers are blocking mapping diagnostics. Backend aliases and
canonical backend names belong to the comparison mapping, not the raw evidence.

Represent composition as an ordered list of component identities and values,
with a declared mole or mass basis and scope: overall, liquid, or vapour.
Storage supports a list rather than two hard-coded component columns, while
the SOURCE-1 capability gate admits at most two components. Unknown phase
composition is not interchangeable with overall composition.

Finite fractions must lie in [0, 1]. If a binary record explicitly supplies
one component fraction and identifies the complete two-component system in
that phase, derive the complement as `1 - fraction` and record the derivation.
For two supplied fractions, retain both exactly. Accept their sum as unity
only within the rounding intervals justified by their reported precision;
without such evidence require exact decimal unity. Never silently rescale a
reported pair. A backend conversion may explicitly rescale an accepted rounded
pair, retaining both the original and evaluation compositions and the rule.

Mole/mass conversion requires identified component molar masses with their
source and version. It preserves both bases and the conversion inputs. Import
never queries CoolProp to obtain missing masses; a comparison may use its
explicitly mapped backend's masses and record them in the comparison artifact.
Volume fractions, molality, and concentration measures are unsupported until
separately qualified; they must not be interpreted as mole fractions.

### Phases, uncertainty, and limitations

Keep reported property, variable, constraint, and composition phases at their
original scopes. Preserve specific liquid/vapour labels, broader fluid labels,
unknown labels, and equilibrium contexts separately. Model-reported phase is
additional evidence. Do not impose a phase solely to make a failing comparison
succeed, or infer a feed composition from liquid/vapour compositions.

Uncertainty records preserve their target quantity, assessment identity,
standard/expanded/combined classification, symmetric or asymmetric bounds,
absolute/relative basis, units, coverage factor, confidence level, evaluator,
and method where supplied. Coordinate and composition uncertainties remain
distinct from property uncertainty. Repeatability, device specifications,
limits, and uncertainty are not interchangeable.

Convert uncertainty magnitudes with the corresponding scale, without applying
a temperature offset. Expanded uncertainty may supply a standard uncertainty
only when the stated coverage factor and applicable definition justify the
conversion. Confidence level alone supplies no factor. Do not combine multiple
assessments, infer independence, or propagate input uncertainty automatically.
If multiple usable assessments exist, the comparison must select one explicitly.

Malformed syntax, unsafe documents, unsupported roots, ambiguous identifier
graphs, and resource-limit violations reject the document before output.
Recognized but unsupported scientific records and semantically invalid values
are retained in the raw source and inventory with locators and stable reasons;
they produce no eligible canonical observation. Every source property value is
accounted as normalized, unsupported, invalid, or unselected. Unknown scientific
qualifiers that could alter meaning block normalization of the affected record.
Unknown descriptive metadata remains raw evidence and an import limitation.

## Bundles and operations — SOURCE-1.0B

### Artifact contract

New bundle schema version 1 uses these distinct `bundle_kind` values:

- `imported_source`;
- `reference_comparison`;
- `source_collection`.

Readers dispatch by verified manifest kind/version rather than guessing from
a directory name or a failed attempt to read generated-run metadata. Initial
import artifacts are:

```text
manifest.json
request.original.yaml
request.normalized.json
source/original.xml OR source/original.json
catalog.json
data/observations.parquet
data/provenance.parquet
data/uncertainties.parquet
data/diagnostics.parquet
report.json
```

The catalog holds citation, component, sample, dataset, property, variable,
constraint, and phase definitions, plus the complete supported/unsupported
record inventory. Observations hold stable IDs, source order, quantity, SI
value/unit/basis, and available normalized state/composition. Provenance is
one-to-one with observations and contains locators, reported values, precision,
and conversion lineage. Uncertainties and diagnostics are long-form records
bound to their exact source target; diagnostics may target unsupported records
that have no canonical observation. Empty tables retain their declared schemas.

The manifest binds kind/version, identities, software/adapter versions,
capability profile, source evidence, artifact paths/hashes, table schemas/units,
counts, and completion status. It hashes every other artifact, not itself.
Downstream operations retain the exact manifest-byte hash separately.
The catalog and report must agree with table counts and identity joins.

Comparison bundles add a prediction/residual table and metrics report, with a
row for every selected observation/model request, including failures and
exclusions. Collection bundles materialize selected evidence and its lineage;
they are not mutable lists of external paths. Both copy the consumed canonical
evidence and required catalog/provenance/uncertainty records and retain original
source documents once per document hash. Recorded parent manifest identities
remain distinct from hashes of any selected materialized tables. Inspection of
the finalized scientific snapshot must not require the original host paths.

Use the existing stable descriptor-backed reading and guarded no-replace
finalization helpers. All file access enforces containment, regular-file and
symlink policy, hashes, and source identity. Revalidate consumed inputs before
protected finalization. Never overwrite inputs, staging directories, final
bundles, or figures. A cancelled or failed execution cannot publish success.
Figures remain separate image/sidecar outputs with their own request identity.

### Preview, configuration, and public interfaces

Preview is non-writing and backend-free for import. It inventories all records,
projects requested selections and eligibility, reports limitations/counts, and
binds exact source descriptors, configuration bytes, and adapter version.
Execution recomputes and verifies that context before writing. Selecting an
unknown source record is a configuration error. The default import selection
is all records, with every limitation disclosed. A recognized document with no
eligible observations may be archived with status `no_eligible_observations`;
it remains inspectable but offers no eligible plot/comparison/ML rows.

Introduce portable YAML schema version 1 documents with `document_type`:

| Type | Configuration responsibility |
| --- | --- |
| `source_import` | Explicit format (`thermoml_xml` or `thermoml_json`) and optional dataset/property selections; empty selections mean all |
| `source_comparison` | Observation selection, ordered models, component mappings, parameter contexts, and explicitly selected uncertainty assessment |
| `source_collection` | Selections and explicit exclusions by source identity, plus publication-group overrides with recorded reasons |

Source paths remain explicit invocation/binding inputs, not portable YAML
fields. Scientific mappings are declarative identifiers and values, never
executable expressions. Omitted comparison model selection defaults to HEOS;
unavailable models remain blocking selections rather than silently falling
back. These new schemas do not change Dataset/Model Sweep schema version 2.

The planned CLI additions are:

```text
carnopy init source_import|source_comparison|source_collection OUTPUT [--full]
carnopy import SOURCE --config IMPORT.yaml [--out PATH] [--preview] [--json]
carnopy compare SOURCE --config COMPARISON.yaml [--out PATH] [--preview] [--json]
carnopy collect SOURCE... --config COLLECTION.yaml [--out PATH] [--preview] [--json]
```

Output roots default to `outputs`. `--preview` creates no artifact or execution
Activity record; `--json` selects the structured result/preview representation.
The Python entry points are `import_source(source, *, config, output_root)`,
`compare_source(source, *, config, output_root)`, and
`collect_sources(sources, *, config, output_root)`, with the same default root.
Their matching `preview_source_import`, `preview_source_comparison`, and
`preview_source_collection` helpers return non-writing typed projections.
Results and projections are immutable, lightweight records containing identities,
counts, statuses, diagnostics, and artifact references rather than dataframes or
mutable engine objects. Private progress/cancellation hooks stay private.

Import completes as `completed`, `completed_with_limitations`, or
`no_eligible_observations`. Comparison distinguishes full success, completion
with exclusions/failures, and no comparable observations. All outcomes preserve
their accounting; document/configuration/integrity failures raise structured
errors without claiming a finalized result. Exact result models and their JSON
projections must implement these distinctions together in their owning stage.

`inspect`, `plot`, and `prepare` gain explicit source-kind dispatch. Existing
generated bundles and configurations retain their behavior. Preparation schema
version 2 introduces imported/collection/comparison roles and source-aware
grouping; version 1 remains readable and keeps its existing generated-source
semantics. Do not silently rewrite an opened legacy configuration or retrofit
fields into immutable old artifacts. Unknown future versions fail clearly.

### Comparison semantics

HEOS comparison starts with direct pure/binary temperature-pressure states.
Missing T/P, unresolved component identity, invalid composition, incompatible
phases, unsupported properties, unavailable parameters, and evaluation failures
produce distinct reasons. Never select a nearest state, interpolate, change an
input pair, or infer atmospheric pressure. Preserve available validity-domain
evidence and distinguish unavailable domain information from confirmed coverage.

A comparison records backend/model/version/revision, mappings, effective input
values and composition, reference policy, parameter values and sources, backend
phase, and raw failure diagnostics. Use native molar outputs for molar evidence
where qualified, or record any explicit basis conversion. HEOS uses qualified
built-in pair data; absent data does not trigger an estimated mixing rule.

PR/SRK accept explicit constant pair parameters with source/applicability, or
an explicitly selected zero-parameter baseline. Parameter fitting and
temperature-dependent parameter laws are outside this program. Instance-local
parameter changes must not alter another evaluation or the legacy generation
adapter. Capability discovery is property/operation/model/pair-specific; pure
fluid capability does not imply binary capability. See the official
[mixture](https://coolprop.org/fluid_properties/Mixtures.html) and
[cubic-model](https://coolprop.org/coolprop/Cubics.html) documentation.

For measurement `m` and prediction `p`, the residual is `r = m - p`; absolute
residual is `abs(r)`. Signed relative residual is `r / abs(m)` only when `m` is
finite, nonzero, and a ratio is meaningful for that quantity. A zero reference
still permits an absolute residual. Existing model-sweep differences retain
their own model-minus-reference convention; never relabel them as these
residuals. Uncertainty normalization is `r / u` for an explicitly selected,
compatible, positive standard property uncertainty. It is not automatically a
combined model/input uncertainty or a statistical z-score.

Report bias, MAE, RMSE, maximum absolute deviation, and applicable relative and
uncertainty-normalized summaries with their eligible counts and denominators.
Group by quantity/unit/basis, component system, phase, model/parameter context,
and selected domain; publish coverage and exclusions beside metrics. Do not
average incompatible units or rank models over different eligible populations
without identifying that difference. A missing uncertainty or unavailable
relative residual cannot suppress a valid absolute residual.

### Collections and Preparation

Collections accept finalized import and reference-comparison bundles, validate
every selected source, and preserve deterministic source/row order. Repeated
selection of the same observation/model evidence is a configuration error.
Different source documents with apparently duplicated measurements remain
separate rows with duplicate-candidate evidence. No automatic averaging,
deduplication, outlier removal, imputation, or cross-publication property joins.

Retain observation/point identity, publication and experiment-series identity,
component/composition/phase state, uncertainty, source hashes, and any prediction
and parameter context through Preparation. Measured and residual targets are
separate roles. Residual targets name the exact model/parameter context; multiple
model variants cannot be flattened into an unnamed target. Predictions may be
explicit features or auxiliaries, but measured target values and their derived
residuals must not be features that reveal the selected target.

Default automatic splits use connected groups joining publication membership,
all descendants of each measurement, and complete exact thermodynamic-state
identity across models and publications. A state key includes component
identities, composition basis/values, phase, and applicable state coordinates;
it excludes target values, model identity, and source filename. Missing DOI uses
an explicit publication grouping override or conservative document grouping,
with cross-document publication identity reported unavailable. Missing grouping
evidence must not be advertised as proven publication independence.

No connected group may cross partitions. Explicit holdouts that split a group,
insufficient groups, or empty requested partitions fail with diagnostics; do
not fall back to row shuffling. Split scenarios require enough state evidence
to perform their promised exact-state check. An explicit unsplit preparation
can retain otherwise eligible rows with unavailable split evidence and says so.
Fitted transformations and optional diagnostic baselines use training data
only. Parquet remains canonical; existing array exports remain derived and
manifest-backed. Preparation never calls CoolProp to fill missing values.

### Visualization, desktop, archive, and VLE

Imported observations start as scatter plots with explicitly qualified
uncertainty bars and source/phase/composition facets. Preserve repeated points
and missing values. Do not infer a grid, sequence topology, or continuous curve
from sorted measurements. Comparison plots read finalized predictions and
residuals; rendering never evaluates a backend. Figure provenance binds exact
sources, selections, quantities, conversions, uncertainty definitions, and
plot settings.

Sources and Reference Comparison are planned workflow surfaces under the
existing desktop composition. Collection editing belongs to Sources. New document
drafts use the global exact-byte Save lifecycle. Bind sources explicitly from
verified selections; browsing Inspect or changing pages cannot replace a bound
source. Workers own parsing, tables, capabilities, comparisons, and rendering;
QtCore controllers and QML consume bounded typed projections. Reuse one global
request coordinator, operation-bound response acceptance, cancellation,
protected finalization, execution Activity, and guarded recovery. Existing
500-row worker preview blocks and 100-row local pages remain the baseline.

Archive access follows the complete local workflow. Search the official NIST
metadata API with bounded pagination; explicitly download selected records and
retain source URL, retrieval evidence, raw bytes, and hashes. Download hands
off to the same import preview. Navigation never starts a download or import;
offline local workflows remain usable. Bulk mirroring and arbitrary crawling
are outside SOURCE-1.

VLE adds pure saturation pressure at reported T and saturation temperature at
reported P. Binary operations are bubble/dew pressure at reported T plus the
appropriate liquid/vapour composition, or bubble/dew temperature at reported P
plus that composition. Predicted pressure or temperature must not also be an
input to the same residual calculation. Preserve paired phase compositions,
input/output roles, convergence evidence, and exclusions. T-x-y, P-x-y, and x-y
plots use only recorded/imported or finalized evaluated points; no inferred
envelope, feed composition, or phase-fraction curve is authorized.

## Implementation and qualification boundary

Use `defusedxml` for XML with DTDs, entities, and external references forbidden;
use the standard JSON parser with duplicate keys and nonstandard nonfinite
constants rejected. Both paths require explicit byte, depth, record, and scalar
length bounds, cancellable processing, and verified source reads. Do not add a
generic parser/plugin framework. Dependency installation and lock changes still
follow local authority; SOURCE-1.0 changes neither dependencies nor runtime.

The [SOURCE-1 qualification matrix](../../SOURCE_IMPORT_PLAN.md#qualification-corpus-and-acceptance-matrix)
defines the minimum evidence for each behavior. Full public capability is
claimed only after its owning milestone passes scientific, compatibility,
desktop, documentation, and distribution acceptance. Pointwise feasibility is
not qualification of a fluid pair's complete domain or a model's accuracy.
