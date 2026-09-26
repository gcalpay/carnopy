# SOURCE-1 — ThermoML import, comparison, and ML preparation

## Authority and current checkpoint

The maintainer accepted this program on 2026-09-26. It delivers the workflow
across Python, the CLI, and the QML desktop:

```text
local ThermoML XML/JSON
  -> import -> inspect -> plot -> CoolProp comparison
  -> multi-publication collection -> measured-value/residual ML preparation
  -> later NIST archive access -> later vapour-liquid equilibrium
```

**Completed milestone: SOURCE-1.0, contracts (0A–0C).**
**Completed checkpoint: SOURCE-1.1A**, bounded parsing and non-writing import
preview; verification is recorded below. SOURCE-1.1 remains in progress.
**Next checkpoint: SOURCE-1.1B**, density normalization and immutable import
bundles, after the local commit boundary. The Python preview is available in
development source; bundle writing, the import CLI, and desktop import are
not implemented yet.

The normative source contract is
[docs/agent-guides/SOURCE_CONTRACTS.md](docs/agent-guides/SOURCE_CONTRACTS.md).
The [current scientific contracts](docs/agent-guides/SCIENTIFIC_CONTRACTS.md)
remain authoritative for implemented generation, sweeps, and Preparation v1.
The [desktop architecture](DESKTOP_ARCHITECTURE.md) remains the ownership
authority. GUI-2 Stage 6 is complete; pending Stages 7/8 retain their numbers,
dependencies, and acceptance requirements in [GUI2_PLAN.md](GUI2_PLAN.md).

This plan records the explicitly accepted program, not private product
strategy. Its checkpoint status must be updated with each implementation
handoff. An accepted design is not evidence of implemented or released support.
Repository-local Git, dependency, stage-boundary, and publication rules apply.
Milestones are acceptance boundaries, not automatic releases.

## Accepted scope and delivery order

- Pure fluids and binary mixtures; refrigerants and common engineering fluids
  anchor qualification. Import is independent of CoolProp coverage.
- Local files first. Complete the single-phase desktop import-to-ML workflow
  before archive discovery/download and then VLE.
- Density first, then constant-pressure/constant-volume heat capacity,
  viscosity, thermal conductivity, and speed of sound, with mass/molar basis
  preserved.
- HEOS comparison first; PR/SRK follow with explicitly selected and recorded
  binary parameters. Binary evaluation supports comparisons in this program.
- Multiple publications may form one immutable collection. Preparation supports
  measured-property and separately identified measurement-minus-model targets.
- Use the existing scientific core and desktop worker infrastructure. A
  milestone with user-facing behavior includes Python/CLI and desktop delivery;
  backend-only work does not complete that milestone.

General binary generation/sweeps, parameter fitting, new property engines,
ternary systems, LLE, automatic reference-state rebasing, native 3D, training,
and new tensor formats are separate work. SOURCE-1 does not add a database,
web service, generic adapter framework, full-archive mirror, or installer.

## Milestones and submilestones

### SOURCE-1.0 — Contracts

| Checkpoint | Deliverable | Status |
| --- | --- | --- |
| 0A | Evidence, identity, normalization, composition, phase, uncertainty, and eligibility contract | Complete; documented in SOURCE_CONTRACTS.md |
| 0B | Bundle kinds, artifact responsibilities, configuration/API boundaries, compatibility, and desktop ownership | Complete; documented in SOURCE_CONTRACTS.md |
| 0C | Qualification corpus specification, acceptance matrix, stage ledger, and synchronized guidance/distribution inventory | Complete; verification recorded below |

Completion means the implementation contract and acceptance matrix are
reviewable and discoverable from the contributor guide and public roadmaps.
It does not mean parser fixtures have run or source/model capabilities are
qualified. This checkpoint changes prose and its distribution inventory only;
it adds no runtime source, template, schema implementation, or dependency.

### SOURCE-1.1 — Local import and inspection

| Checkpoint | Deliverable and acceptance |
| --- | --- |
| 1A | Complete. Bounded XML/JSON readers, shared evidence inventory, stable source reads, selections, and non-writing Python preview. Both encodings preserve interpreted evidence while retaining different raw identities. Verification is recorded below. |
| 1B | Normalize supported pure/binary density observations; write immutable source bundles with complete accounting, raw bytes, provenance, uncertainty, and diagnostic joins. Expose the planned import CLI/API. |
| 1C | Add the Sources import document/draft, worker planning/execution, explicit source binding, Activity/recovery, source discovery, and bounded Inspect tables. Complete installed and native desktop acceptance. |

The 1A implementation uses canonical identity, stable reads, cancellation, and
the existing failure hierarchy. XML parsing uses `defusedxml`; JSON uses the
standard library with explicit validation. The XML dependency is in the base
distribution and loads only in the import path. Local qualification uses the
locked Python 3.12.3 environment; broader Python support remains subject to the
existing matrix gates. Dependency edits, locking, and installation must follow
local authorization; do not substitute an unqualified parser if unavailable.

The initial resource profile is 64 MiB per uncompressed source, nesting depth
64, 1 MiB per scalar text value, and 1,000,000 property-value records per
document, including unsupported/unselected records. SOURCE-1.1A additionally
bounds representation size to 1,000,000 XML elements or JSON containers/scalars
(including keys); this bounds documents with many empty or descriptive nodes.
Reject inputs over a limit and accept values at the limit; never truncate or
finalize a partial parse. Check depth/text/counts during
parsing, not only after materializing the document. Compressed archives and
embedded file retrieval are not accepted import inputs. These are versioned
capability limits, not silently adjustable scientific options.

An import preview records format, adapter/schema profile, source hash, ordered
dataset/property selection, accounting, limitations, and plan identity. Save
validates the exact YAML. Execution validates and recomputes the plan against
the bound source before staging and again checks source identity before final
publication. The parser adds no backend call or network request.

### SOURCE-1.2 — Properties and observation plots

| Checkpoint | Deliverable and acceptance |
| --- | --- |
| 2A | Add qualified heat-capacity, viscosity, conductivity, and sound-speed quantity mappings; preserve mass/molar and special-property distinctions. |
| 2B | Expose source, sample, method, phase, composition, and uncertainty selections and diagnostics through core inspection and typed desktop profiles. |
| 2C | Add scatter/uncertainty plots, source-aware facets, verified image/sidecar export, and the existing session-plot handoff; qualify desktop interaction. |

No gridded topology or connected curve is inferred from observation sorting.
Plotting and inspection remain backend-free. Missing or inapplicable uncertainty
is visible rather than supplied as zero.

### SOURCE-1.3 — HEOS reference comparison

| Checkpoint | Deliverable and acceptance |
| --- | --- |
| 3A | Add explicit component mappings and pure-fluid T/P evaluation with exact observation/property/input identity and source/model phase checks. |
| 3B | Qualify binary compositions, built-in pair parameters, property/operation capabilities, conversions, validity evidence, and structured failures. |
| 3C | Publish comparison bundles, metrics, parity/residual plots, CLI/API, and the Reference Comparison desktop workflow with immutable source binding. |

Evaluate only compatible observed states; preserve a requested row even when
prediction is unavailable. Record model parameters and effective numerical
inputs. Absolute, relative, and uncertainty-normalized metric eligibility are
independent. Comparison plotting consumes finalized results.

### SOURCE-1.4 — PR/SRK reference comparison

| Checkpoint | Deliverable and acceptance |
| --- | --- |
| 4A | Add sourced constant pair parameters and a deliberately selected zero-parameter baseline, with instance-local application and complete provenance. |
| 4B | Qualify supported properties/operations and failure cases independently for PR and SRK; keep legacy pure-fluid generation behavior intact. |
| 4C | Expose model/parameter selection, common-domain metrics, plots, and desktop diagnostics through the established comparison workflow. |

No fitted-parameter service, undocumented parameter fallback, or assumption of
transport-property parity is admitted.

### SOURCE-1.5 — Multi-publication source collections

| Checkpoint | Deliverable and acceptance |
| --- | --- |
| 5A | Validate explicit selections from finalized import/comparison bundles with pinned manifests, artifact identities, and reproducible row ordering. |
| 5B | Materialize an immutable canonical evidence snapshot; preserve raw document identity and lineage, expose duplicate candidates and publication/series groups. |
| 5C | Add collection configuration, CLI/API, Sources-page collection editing, coverage review, and exact Inspect/Preparation handoff. |

No implicit averaging, duplicate removal, or coordinate-only joins. Different
publications remain traceable even when their reported measurements coincide.

### SOURCE-1.6 — Experimental ML preparation

| Checkpoint | Deliverable and acceptance |
| --- | --- |
| 6A | Add Preparation v2 measured-property targets, eligible composition/source fields, and explicit co-reported-property joins while preserving v1 readers. |
| 6B | Add named residual targets bound to exact comparison/model/parameter identities; reject feature choices that reveal their target. |
| 6C | Add publication/state/measurement grouping, explicit holdouts, leakage/coverage audit, typed desktop controls, and current manifest-backed array exports. |

Default partitions keep connected publication and exact-state groups intact
across model variants. Reject contradictory or impossible split requests.
Preparation never repairs missing information with a backend call. Completion
of 6C is the first complete local single-phase SOURCE-1 workflow acceptance.

### SOURCE-1.7 — NIST archive access

| Checkpoint | Deliverable and acceptance |
| --- | --- |
| 7A | Add bounded, paginated official metadata search by compound, property, and publication; expose unsupported service responses and network failures. |
| 7B | Download explicitly selected XML/JSON records with source/retrieval evidence, byte limits, hashes, cancellation, and no-overwrite destinations. |
| 7C | Add desktop search/download and CLI/API access, handing acquired local files to the existing import preview; verify offline reuse. |

NIST documents a Cordra-backed metadata API in its
[archive publication](https://www.nist.gov/publications/towards-improved-fairness-thermoml-archive).
Use that service boundary rather than scraping article presentation. Navigation
does not acquire data. No background mirror or credentials are required by the
accepted design; a changed upstream requirement must be surfaced explicitly.

### SOURCE-1.8 — Vapour-liquid equilibrium

| Checkpoint | Deliverable and acceptance |
| --- | --- |
| 8A | Normalize qualified pure-fluid vapour-pressure and binary liquid/vapour composition observations, preserving phase-specific roles and uncertainty. |
| 8B | Qualify pure saturation P(T)/T(P) and binary bubble/dew P(T, composition)/T(P, composition), with exact input/output roles and convergence evidence. |
| 8C | Add emitted-point T-x-y, P-x-y, and x-y views plus comparison, collection, and Preparation integration across all three interfaces. |

Overall composition, liquid composition, vapour composition, and phase
fraction remain distinct. A predicted target cannot also be supplied as an
input to the same comparison. This stage does not add general mixture
generation, arbitrary flashes, LLE, or inferred continuous phase envelopes.

## Qualification corpus and acceptance matrix

Routine tests use small, hand-authored XML/JSON fixtures and temporary output
directories. Do not commit generated datasets or figures. The fixture cases
below are the corpus specification; their executable fixtures and checks are
delivered with the owning behavior. Real-source acquisition is explicit and
separate from offline CI. Do not vendor article/archive payloads without
establishing their redistribution terms.

### Real-record anchor

The primary density case is Jia et al., *Journal of Chemical Thermodynamics*
101 (2016), 54–63, DOI `10.1016/j.jct.2016.05.013`:
[archive record](https://trc.nist.gov/ThermoML/10.1016/j.jct.2016.05.013.html),
[XML](https://trc.nist.gov/ThermoML/10.1016/j.jct.2016.05.013.xml), and
[JSON](https://trc.nist.gov/ThermoML/10.1016/j.jct.2016.05.013.json).

The XML inspected during planning on 2026-09-26 was 547,786 bytes, SHA-256:

```text
43b9f77584299cb5dd9435e170a29274265a32d7803e2510b3d68aea6fdc79b8
```

Use the hash as a revision pin, not a guarantee that the upstream URL will
always return those bytes. A mismatch requires reviewing the changed record;
never silently regenerate expected results against a new payload.

That record contains pure R134a and R32 observations and binary
R32/R1234ze(E) observations. Dataset number 4 contains 438 binary liquid-density
points. Its first point reports T = 283.54 K, P = 3000 kPa, R32 liquid mole
fraction = 0.1742, and mass density = 1199.78 kg/m^3. The pressure normalizes to
3,000,000 Pa; the explicitly derived second fraction is 0.8258. Reported
combined expanded uncertainty is 3.87 kg/m^3 with confidence level 95 and no
stated coverage factor. It must not become an invented standard uncertainty.

The source identifiers can be matched to the installed CoolProp 8.0.0
identifiers. Preliminary evaluations at a separate single binary state proved
adapter feasibility only. They are not parser acceptance, agreement with these
measurements, or qualification of the record's entire temperature/pressure
range. Later stages must record selected domains, reference evidence,
tolerances, and all evaluated failures with their results.

### Required cases

| Case | Required evidence | Owning checkpoint |
| --- | --- | --- |
| F01 | Equivalent pure-density XML/JSON: same interpreted values/context, distinct raw hashes and row identities | 1A–1B |
| F02 | Binary composition as a variable and as a constraint; component order and phase scope preserved | 1A–1B |
| F03 | Repeated identical measurements remain separate; only co-reported properties share a point join | 1B |
| F04 | Exact pressure/temperature conversions; molar quantities never silently become mass quantities | 1B–2A |
| F05 | One binary fraction, two rounded fractions, out-of-range fractions, missing basis, and conflicting component identities | 1A–1B |
| F06 | Missing, standard, expanded, combined, asymmetric, multiple-assessment, and coordinate uncertainties; no inferred coverage factor | 1A–1B, 3C |
| F07 | Unsupported reaction/ternary/special-property records remain in raw inventory with complete accounting | 1A–1B |
| F08 | Unknown qualifiers, variable/constraint conflicts, missing coordinates, null/nonfinite values, and no eligible observations | 1A–1B |
| F09 | Duplicate IDs/JSON keys, dangling references, wrong namespaces/roots, DTD/entity payloads, and each parser resource limit | 1A |
| F10 | Mutation/replacement between preview, parse, hash, and finalization; symlinks, cancellation, and destination collisions | 1A–1C |
| F11 | Backend-unmapped substance imports and plots correctly, but comparison explains the unavailable mapping | 1C–3A |
| F12 | Phase mismatch, missing pair parameters, unsupported property, domain evidence, nonconvergence, and raw backend diagnostics | 3A–3B, 4B |
| F13 | Residual sign, zero reference with valid absolute residual, absent/zero uncertainty, and metric-specific denominators | 3C |
| F14 | PR/SRK zero baseline versus sourced parameters changes identity; one instance cannot contaminate another or legacy generation | 4A–4C |
| F15 | Duplicate source selection, XML/JSON duplicate candidates, overlapping publications, and explicit exclusions preserve lineage | 5A–5C |
| F16 | Same measurement across models and same state across publications never cross partitions; conflicting holdouts and too few groups fail | 6A–6C |
| F17 | Measured/residual target leakage rejected; train-only transformations; manifests, row joins, and array exports round-trip | 6A–6C |
| F18 | Stale source/configuration bindings, late responses, direct-slot guards, busy shutdown, Activity/recovery, and bounded previews | Every desktop checkpoint |
| F19 | Malformed/paginated archive responses, network failure, oversized download, cancellation, no overwrite, and offline reuse | 7A–7C |
| F20 | VLE phase compositions remain separate; target not reused as input; bubble/dew identity and paired phase evidence survive ML export | 8A–8C |
| F21 | Generated Dataset/Sweep/Preparation v1 behavior, old artifact readers, lightweight help, and installed resources remain compatible | Every behavioral milestone |

Numerical model qualification uses authoritative independent reference cases
with documented tolerances; repeating the same CoolProp call is not an accuracy
test. Fixture conversion/identity expectations are exact where appropriate.
Real-source model disagreement is reported rather than automatically treated
as an importer failure or evidence that the experiment is wrong.

### SOURCE-1.1A implemented corpus

The independently hand-authored XML/JSON pair in
`tests/fixtures/thermoml/` covers pure/binary density, repeated observations,
variable/constraint states, samples, methods, precision, and uncertainty.
Focused tests exercise malformed references and values, unsupported records,
composition bases and rounding, exact selections, all parser bounds, unsafe
XML/JSON, cancellation, immutable previews, changed files/configurations, and
backend-free imports. These are parser/eligibility checks; normalization,
bundle finalization, comparison accuracy, and native desktop acceptance remain
assigned to their later checkpoints.

On 2026-09-26, explicit acquisition of the real-record anchor above reproduced
the recorded XML hash. The corresponding JSON was 453,138 bytes, SHA-256
`9b0660c45acf67779c741c21ba6831539a857bfb9d9b30798a833a430d29ee5a`.
Both previews account for **662 density values** across dataset numbers 1–5
(34, 72, 16, 438, and 102 respectively). All 662 property values, variable
values, reported precisions, and row locators agree between encodings, while
source hashes and row identities remain distinct. Both retain unclassified
data-origin warnings; 540 binary values require recorded complement derivation
at normalization. This is evidence of parsing/preview agreement, not model
accuracy or scientific validation of the measurements. Acquired archive files
remain outside the repository and offline CI.

## Verification, handoff, and completion

Use the routed [development workflow](docs/agent-guides/DEVELOPMENT.md).
SOURCE-1.0 requires complete diff review, `git diff --check`, local link checks,
and focused metadata/distribution tests because it adds public prose to the
sdist inventory. It does not require the full runtime or preflight suite.

Behavioral checkpoints require focused parser/scientific/controller regression
checks. Milestone boundaries require the complete applicable source and
distribution gate, synchronized documentation, and native acceptance for new
desktop behavior. Archive acceptance supplements offline CI with explicit
service qualification. Full platform or native-3D promises remain governed by
their existing release/GUI-2 boundaries.

Each handoff records implemented scope, exact verification evidence and
limitations, current/next checkpoint, and the recommended coherent commit and
files to stage. Follow the local clean-worktree requirement before starting the
next milestone; neither this plan nor its acceptance grants Git mutation.

### SOURCE-1.0 completion record

- Evidence and operation contracts: documented in the routed source guide.
- Qualification corpus specification and stage ledger: recorded above.
- Scientific, desktop, README, roadmap, and local status synchronization:
  complete. The public documents are included in the source-distribution
  inventory; maintainer-local status remains unpublished.
- Verification: full change review, `git diff --check`, and local Markdown
  link/whitespace checks passed (11 files, 78 local links).
- Focused metadata/distribution checks:
  `uv run --locked --no-sync pytest tests/test_packaging_metadata.py tests/test_release_tools.py`
  passed: **32 tests in 28.34 s**. The full runtime suite and preflight were not
  required for this documentation/inventory change.
- Runtime implementation, dependencies, model qualification, and native UI
  acceptance: not part of SOURCE-1.0; not performed or claimed.
- Next implementation checkpoint: SOURCE-1.1A after the local stage boundary.

### SOURCE-1.1A completion record

- Implemented: bounded readers, immutable shared evidence, identifier/reference
  checks, density eligibility, source/configuration bindings, and the public
  `preview_source_import` helper with `ImportConfig`, `ImportSelection`,
  `ImportPreview`, and `SourceImportError`.
- Preview projections retain at most 500 selected records and 500 selected
  dataset summaries, with complete counts and explicit omission counts.
- Approved dependency operation: added `defusedxml>=0.7.1,<1`, locked 0.7.1,
  and synchronized the existing environment. No existing package version was
  upgraded; uv also normalized existing conditional dependency markers.
- Source gate: `uv lock --check`,
  `uv run --locked --no-sync python scripts/preflight.py`, and
  `uv pip check --python .venv/bin/python` passed. Preflight includes Ruff,
  formatting, full mypy, the full test suite, and root CLI help. Its final run
  passed **1,402 tests in 569.79 s**; all 169 source files passed mypy.
- The first full run had two desktop worker timeouts (inspection at 30 s and
  validation at 15 s). Both cases passed unchanged in isolation (**2 tests in
  17.66 s**) and in the final full run. No desktop timeout or behavior was
  changed. The final source corpus includes 106 focused parser/preview cases.
- Real-record XML/JSON qualification: all 662 density values, variable values,
  reported precisions, and locators agree, with hashes and limitations recorded
  above. This does not qualify comparison accuracy or validate the measurements.
- Complete change review, `git diff --check`, and local Markdown link/whitespace
  checks passed (10 files, 57 local links). Tracked contracts, user guidance,
  roadmap/desktop boundaries, and unpublished local status are synchronized.
- Next: SOURCE-1.1B. Canonical SI observations, conversion lineage, Parquet
  schemas, protected bundle finalization, and the import CLI are still pending;
  desktop source import remains SOURCE-1.1C. GUI-2 numbering is unchanged.
