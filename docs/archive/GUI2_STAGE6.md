# GUI-2 Stage 6 historical record

GUI-2 Stage 6 is accepted. It adds the private, nonvisual pipeline that turns
verified Carnopy dataset and Preparation tables into bounded, hashed,
renderer-neutral 3D scenes without inventing scientific data.

The durable current ownership is maintained in
[`DESKTOP_ARCHITECTURE.md`](../../DESKTOP_ARCHITECTURE.md), and the scientific
rules are maintained in
[`SCIENTIFIC_CONTRACTS.md`](../agent-guides/SCIENTIFIC_CONTRACTS.md). Remaining
GUI-2 work stays in [`GUI2_PLAN.md`](../../GUI2_PLAN.md). Source and tests remain
authoritative for exact private schemas and behavior.

## Delivered scene pipeline

- immutable copied source bindings, field profiles, exact categorical and
  inclusive numeric filters, normalized scene requests, canonical identities,
  capabilities, structured failures, and hard limits;
- authoritative profiling for verified dataset runs, model-sweep child
  datasets, prepared main tables, and prepared scenario partitions, with
  deterministic topology-first defaults and exact source revision checks;
- finite retained-point projection with original table-row positions and
  stable `case_id` or `prepared_row_id` identities;
- scientific-context blocks separating artifact, run, fluid, backend model,
  phase, saturation endpoint, scenario, and partition;
- exact one-dimensional adjacency edges and exact two-dimensional ordered
  quads in original verified sampler order;
- bounded deterministic `scene.bin` encoding and canonical `scene.json`
  publication in parent-created workspace-session leases;
- the private `profile_scene`, `build_scene`, and `resolve_scene_pick` worker
  operations with cooperative cancellation and protected publication;
- independent parent verification and replacement that preserves the previous
  accepted scene after cancellation, failure, source change, or tampering;
- QtCore-only draft, controller, workspace-session, conservative cleanup,
  stale-state, and shutdown ownership; and
- exact direct, sweep-child, prepared-main, and prepared-partition pick
  resolution with joined prepared provenance and diagnostics.

## Scientific invariants

- A retained point corresponds to one source-valid row with finite selected X,
  Y, Z, and optional scalar values. No numeric tolerance or implicit coercion
  selects or repairs it.
- Connectivity follows only verified source sampling coordinates in original
  materialized level order. Display-coordinate sorting never defines
  adjacency.
- Context blocks never share connectivity. Missing, invalid, filtered, or
  omitted intermediate levels remain gaps.
- Duplicate topology locations remain distinct source points but block
  ambiguous connectivity rather than being merged.
- One-dimensional blocks connect only consecutive verified levels.
  Two-dimensional blocks retain one ordered quad per complete adjacent cell as
  `[i,j]`, `[i+1,j]`, `[i+1,j+1]`, `[i,j+1]`.
- Exact zero-length edges and repeated-vertex or exactly collinear quads are
  omitted and counted without an epsilon.
- Unsupported or unavailable topology remains explicit. Points can remain
  usable while wireframe or surface capability is blocked.
- No triangle, interpolation, smoothing, extrapolation, resampling, backend
  evaluation, or silent repair occurs in scene preparation.
- The accepted limits are 250,000 points, 499,999 edges, 249,999 quads, and a
  64 MiB complete manifest-plus-binary bundle.

## Integrity and lifecycle boundaries

Private scene storage uses UUID lease directories beneath
`.carnopy-gui/scene-leases`. A canonical `lease.json` binds the directory,
device, inode, and owning workspace session. The session owner holds a QtCore
`QLockFile` for its workspace lifetime.

The binary begins with the exact 16-byte little-endian `<8sHHI` header using
`b"CARN3D\0\0"`, header and scene schema version 1, and the `0x01020304`
endian marker.
Every absolute buffer offset is 8-byte aligned; padding is deterministic zero;
buffer ranges cannot overlap, alias, reorder, or escape the file; and whole-file
and per-buffer SHA-256 identities are mandatory. Declared block ranges partition
all points and primitives, and globally valid connectivity is still rejected
when it crosses a block.

The lightweight parent verifier rejects unsupported versions, header/manifest
disagreement, wrong magic or endianness, noncanonical metadata, malformed
descriptors, inconsistent counts and scientific evidence, invalid or ambiguous
identities, hostile connectivity, and source, lease, manifest, or binary
tampering. Startup cleanup removes only a fully recognized lease whose session
lock can be acquired. Malformed, replaced, symlinked, unrecognized, or
apparently live candidates are preserved rather than recursively deleted.

## Public and presentation boundary

Stage 6 adds no visible QML page, VTK integration, camera, authoritative image
export, public API, CLI command, YAML field, generated artifact schema,
dependency, version, tag, or release. Scene schemas are private, versioned,
workspace-session-only implementation details with no migration promise.

The current published `0.1.0a5` distributions predate Stage 6. Qualification
archives built with that unchanged source version are local rehearsal artifacts
and must not be published or used to replace the released payloads. Stage 7
owns interactive reconstruction and presentation; Stage 8 owns the optional
native dependency, platform, distribution, versioning, and release boundary.

## Implementation record

The reviewed feature-branch sequence begins at
`5a02616c6ecadaf650b3e2c4166bf777a3109c30` and runs through the hostile and
lifecycle acceptance checkpoint at
`7648e15c326dcd679e40160158dabe84d4e2e19d`. Git history preserves the smaller
contracts, lease, profiling, projection, topology, primitive, assembly,
encoding, writer, worker, draft, controller, lifecycle, pick, CI, and acceptance
commits. Branch integration, the final commit, and any pull-request reference
remain human-owned Git operations.

## Verification and acceptance

The final locked source gate passed on 2026-08-27. Ruff accepted all source,
all 258 files were formatted, strict mypy passed across 159 source files,
preflight and CLI help passed, all 70 installed packages were compatible, and
the complete suite passed **1,290 tests**.

An isolated sdist and wheel-from-sdist build of the branch passed Twine and the
exact distribution checker. That inventory explicitly requires all twenty
Stage 6 application modules in both archives. A task-scoped installed-wheel
prefix then imported those packaged modules and ran both generated public
launchers, `carnopy-gui` and `carnopy-app`, through their offscreen smoke path.

The hostile verifier matrix and real-process lifecycle tests prove the required
version, magic, endianness, buffer, count, connectivity, tamper, live-lock, and
conservative-cleanup boundaries. No manual native UI acceptance was required
because Stage 6 changes no visible QML or renderer behavior.
