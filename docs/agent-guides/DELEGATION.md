# Codex delegation policy

This document is an authoritative routed part of the root
[contributor and coding-agent guide](../../AGENTS.md). Read it in full before
delegating work or changing project-agent definitions. It does not grant
operational authority beyond `.agents/local.md`.

## Codex delegation policy

Delegate only bounded, independent work where parallelism materially improves
quality or speed. The only project agents that may be delegated to are the
explicit definitions under `.codex/agents/`: `explorer`, `worker`, `reviewer`,
and `architect`. The project `explorer` and `worker` intentionally override the
built-in roles with the same names.

Every active project agent must pin its model, reasoning effort, and sandbox.
Only GPT-6 Astra (`gpt-6-astra`), GPT-6 Sol (`gpt-6-sol`), and GPT-6 Luna
(`gpt-6-luna`) are approved. Luna must always use Max (`max`), including for
read-only work. Other model families, automatic model selection, and automatic
review are forbidden. Do not add or use another project role without maintainer
review. Parent-model preferences, exact-selection failures, and observable
fallback handling belong in `.agents/local.md`.

The reviewed project-agent assignments are:

| Role | Purpose | Sandbox | Model | Effort | Typical tier |
| --- | --- | --- | --- | --- | --- |
| `explorer` | Focused codebase lookup and evidence collection | `read-only` | GPT-6 Luna | Max | Bounded read-only |
| `worker` | Bounded, already-designed implementation | `workspace-write` | GPT-6 Luna | Max | Easy write |
| `reviewer` | Correctness, regression, security, and scientific review | `read-only` | GPT-6 Sol | XHigh | Hard read-only |
| `architect` | Difficult architecture, native, scientific, numerical, and release decisions | `read-only` | GPT-6 Astra | Max | Most difficult |

These are exact pins, not minimums. Parent-session model and reasoning choices
remain in `.agents/local.md`; do not override a project role's pin to match
them. A stuck agent reports the limitation to the parent; it does not alter its
own model or reasoning effort.

Dispatch project agents only through Codex's native custom-agent path. Before
spawning, verify that the callable spawn operation exposes an `agent_type`
argument, pass exactly one of `explorer`, `worker`, `reviewer`, or `architect`,
and require the spawned thread or native agent UI to report a display nickname
from that role's `nickname_candidates`. The stable `name` in each TOML is the
role selector; its nickname is presentation-only. A `task_name` is only a
canonical thread-path label and is never a role selector or display nickname.
A free-form task name, matching label, or prompt that says to act as one of
these roles is not evidence that its TOML profile was loaded.

Do not substitute a generic collaboration wrapper when `agent_type`, an
inspectable native subagent thread, the Subagents/background-agent UI, or the
native `close_agent` operation is unavailable. Continue in the parent thread
instead. Codex chooses unused nickname candidates without a guaranteed order;
do not predict the next nickname or treat a historical Done-row label as proof
that a custom profile was loaded.

Subagent use does not require Ultra, and Ultra is not approved for this project.
Delegation depth is one, so delegated agents must not spawn descendants. Close
every spawned agent through `close_agent` immediately after its result is
integrated or discarded, including agents already marked completed.
`interrupt_agent` stops a turn but leaves its thread open, so it is never a
substitute for `close_agent`. If the active surface does not provide the
required lifecycle operation, do not spawn project agents from that surface.
