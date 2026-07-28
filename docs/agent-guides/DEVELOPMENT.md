# Development and contribution workflow

This document is an authoritative routed part of the root
[contributor and coding-agent guide](../../AGENTS.md). Read it in full before
implementation, testing, documentation changes, Graphify use, or a commit
handoff. Checkout-local authority remains in `.agents/local.md`.

## Development workflow

Use the project-local environment and locked uv workflow described by local
instructions. `pyproject.toml` and `uv.lock` are authoritative; do not recreate
requirements files.

Normal synchronization:

```bash
uv sync --locked --extra all --group dev
```

Release tooling:

```bash
uv sync --locked --extra all --group dev --group release
```

Required quality gate:

```bash
uv lock --check
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src/carnopy
uv run --locked pytest
uv run --locked python scripts/preflight.py
uv pip check --python .venv/bin/python
```

Maintainers can run the complete source, package, Twine, and distribution
inspection gate with:

```bash
bash scripts/local_gate.sh prerelease/local-gate
```

GitHub verification keeps core and desktop dependencies separate. General
quality and Python-matrix jobs do not install the `app` extra or Qt runtime
packages; the dedicated Linux app job owns desktop typing and tests. Pull
requests also receive dependency review and CodeQL analysis. Scheduled
workflows audit locked dependency profiles and exercise the core package on
Linux, Windows, and macOS.

If a required command or dependency is unavailable, preserve the exact failure
and ask before installing, upgrading, or substituting anything.

Documentation synchronization is part of implementation, not optional
follow-up work. Before handing off any completed implementation:

- inspect the applicable tracked documentation, including active stage plans,
  durable architecture records, user-facing guidance, public contracts,
  examples, and contributor instructions;
- update every document made stale by the change and record current stage or
  implementation status where an active plan provides that record;
- include those documentation edits in the same coherent implementation change
  unless an approved plan explicitly assigns a separate documentation commit;
- never declare an implementation complete while tracked documentation still
  describes the previous behavior; and
- if no tracked document requires a change, state in the final handoff which
  documentation was reviewed and why it remains accurate.

Do not wait for the maintainer to request this synchronization. Generated
Graphify artifacts remain separate: refresh them only when intentionally
updating the public graph, as described below.

Use:

- `rg` for searches;
- `graphify query` for broad architecture, dependency, or codebase-navigation
  questions only when `graphify-out/graph.json` exists and passes the freshness
  gate below;
- `apply_patch` for repository file edits;
- temporary directories for generated test artifacts;
- focused tests for every behavior change.

Graphify is optional local analysis tooling. Its existence does not make it
current. Before any query, use the exact source revision recorded by the public
graph report. For a legacy graph without one, conservatively use the latest
commit that changed the complete public artifact set:

```bash
git log -1 --format=%H -- \
  graphify-out/GRAPH_REPORT.md \
  graphify-out/graph.html \
  graphify-out/graph.json
git rev-list --count <graph-source-revision>..HEAD
```

Apply this repository-wide gate:

- zero intervening commits: the graph may guide navigation, with exact claims
  still verified against source;
- one through five intervening commits: the graph is navigation-only and every
  conclusion must be checked against current source;
- six or more intervening commits, or any completed architecture stage absent
  from the graph: the graph is hard-stale and no Graphify query, path, explain,
  or other traversal may be run for current repository work.

Do not maintain a manual counter; Git history is the counter. A hard-stale graph
is either intentionally refreshed as one separately reviewed artifact update or
bypassed completely in favor of source, tests, and scoped `rg`. Do not load or
query it merely to confirm that it is stale.

When the graph passes that gate, prefer scoped queries such as:

```bash
graphify query "how does preparation resolve semantic fields?" --graph graphify-out/graph.json
```

Use the graph to narrow the search space before broad `rg` or repeated file
reads. For exact implementation changes, verify against the source files before
editing. Commit only the public graph artifacts when intentionally refreshing
the graph:

```text
graphify-out/GRAPH_REPORT.md
graphify-out/graph.html
graphify-out/graph.json
```

Do not commit Graphify cache, interpreter, manifest, cost, or `.graphify_*`
intermediate files.

Avoid:

- monolithic modules;
- speculative frameworks;
- heavy imports and side effects at module import time;
- brittle golden thermodynamic datasets;
- pixel-perfect figure tests.

Test count is not a target. Prefer a focused regression for each distinct
contract or failure mode, use parametrization where cases share behavior, and
remove redundant tests. The suite can still contain many tests because
configuration, scientific modes, provenance, visualization, CLI behavior,
packaging, and release tooling are separate public contracts.

Root and subcommand help must not import CoolProp, NumPy, pandas, PyArrow, or
Matplotlib.

## Commit messages

Use:

```text
<type>(<scope>): <imperative summary>
```

Rules:

- lowercase type and scope;
- imperative mood: `add`, `fix`, `validate`, `reject`, `document`;
- concise summary, ideally no more than 72 characters;
- no trailing period;
- body only when the reason or tradeoff matters.

After completing and verifying an implementation and synchronizing its tracked
documentation, include a recommended commit message in the final handoff. Also
list the exact repository-relative files to stage. If more than one commit is
recommended, give the file group for each commit and state whether hunk-level
staging is required. Prefer one coherent commit unless the proposed
intermediate commits are independently reviewable and verifiable. This is
guidance for the human operator and does not grant Git mutation authority.

Common types:

```text
feat fix test docs refactor chore ci build perf style
```

Recommended scopes:

```text
dataset schema sampler coolprop cli validation metadata tests docs ci
packaging viz app
```

Examples:

```text
feat(viz): add configured visualization outputs
fix(validation): reject duplicate canonical fluids
test(sampler): cover descending stepspace ranges
docs(project): consolidate public guidance
build(packaging): declare parquet runtime dependency
```
