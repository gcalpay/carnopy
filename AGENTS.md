# Carnopy contributor and coding-agent guide

## Authority and startup

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
publication boundaries. Do not infer permission from this public guide when the
local file is more restrictive.

This file and its routed references are one tracked contributor guide. They are
authoritative for public scientific behavior, schemas, compatibility contracts,
architecture, packaging, and contribution standards. Local instructions may
narrow operational authority but must not silently alter those public
contracts.

Before starting an implementation stage, inspect the worktree and follow the
stage-boundary rules in `.agents/local.md` when unrelated or uncommitted work
is present. Preserve unrelated changes. Git mutation remains human-owned unless
a local instruction explicitly grants narrower authority.

Canonical names:

```text
Project: Carnopy
Repository: carnopy
Distribution: carnopy
Import package: carnopy
CLI: carnopy
```

CoolProp is the first backend dependency, not the project identity.

## Required task routing

After reading local instructions, select every applicable row below and read
each referenced document **in full before acting**. Multiple rows commonly
apply. A routed document is mandatory for its scope, not optional background
reading.

| Work being performed | Required tracked guidance |
| --- | --- |
| Any implementation, test, documentation, or commit handoff | [Development and contribution workflow](docs/agent-guides/DEVELOPMENT.md) |
| Product identity, boundaries, future scope, or roadmap priority | [Product scope and direction](PRODUCT_SCOPE.md) |
| Delegating work or changing project-agent definitions | [Codex delegation policy](docs/agent-guides/DELEGATION.md) and the applicable files under `.codex/agents/` |
| Scientific behavior, configuration, sampling, CLI/API, rows, provenance, preparation, visualization, or core architecture | [Public scientific and application contracts](docs/agent-guides/SCIENTIFIC_CONTRACTS.md) |
| Desktop controllers, QML, Widgets, worker boundaries, packaging of desktop resources, native 3D, or frontend retirement | [Desktop architecture](DESKTOP_ARCHITECTURE.md) and, while GUI-2 is active, [GUI-2 plan](GUI2_PLAN.md) |
| Preparation workflows, diagnostics, feature engineering, or research directions | [Public scientific and application contracts](docs/agent-guides/SCIENTIFIC_CONTRACTS.md) and [ML preparation roadmap](ML_PREPARATION_ROADMAP.md) |
| Packaging metadata, dependency extras, distribution contents, CI publishing, tags, or releases | [Packaging and release safeguards](docs/agent-guides/RELEASE.md) and [Development and contribution workflow](docs/agent-guides/DEVELOPMENT.md) |
| User-facing installation or workflow documentation | [README](README.md) plus every contract document applicable to the changed behavior |

When a task crosses scopes, combine the references. Repository source and tests
establish current behavior; these tracked contracts constrain what may change.
If they disagree, stop and surface the contradiction instead of silently
blending them.

## Project boundary

Carnopy is an open and auditable thermophysical-data workbench. Current
behavior and exclusions live in the scientific contracts; durable product
direction and roadmap status live in [PRODUCT_SCOPE.md](PRODUCT_SCOPE.md).
Planned directions are not implemented capabilities or authority to broaden a
public contract without maintainer approval.

## Always-on safeguards

- Use the project-local locked environment and authoritative
  `pyproject.toml`/`uv.lock`; do not recreate requirements files.
- Preserve scientific, data-integrity, no-overwrite, security, accessibility,
  and worker-isolation boundaries. Never simplify them away.
- Look for an existing repository helper before writing another abstraction.
  Prefer the standard library or native Qt/platform behavior, then the smallest
  correct change. Do not add speculative frameworks or scaffolding.
- Keep heavy scientific/data imports and side effects out of lightweight module
  import paths. Root and subcommand help must not import CoolProp, NumPy,
  pandas, PyArrow, or Matplotlib.
- Use temporary directories for generated test artifacts. Do not commit
  generated datasets or figures.
- Match verification to the change class defined in the routed development
  guide. Read-only planning requires no quality gate. Pure prose documentation
  requires diff inspection and only directly relevant documentation checks,
  never the complete test or preflight suite by default.
- Add focused verification for behavior changes. Test count is not a target,
  and brittle golden thermodynamic data or pixel-perfect figure tests are not
  substitutes for contract tests.
- Documentation synchronization is part of implementation. Review and update
  the active plan, durable architecture, public contracts, examples, and
  user-facing guidance made stale by a change before declaring it complete.
- If a required command or dependency is unavailable, preserve the exact
  failure and ask before installing, upgrading, or substituting anything.
- Operational authority comes from `.agents/local.md`. A technical workflow or
  commit recommendation never grants Git, dependency, credential, publication,
  or external-service authority.

Read the routed development guide for exact commands, documentation policy,
test posture, and commit handoff requirements.
