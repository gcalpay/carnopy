# Implementation handoff

Read this guide before the final handoff for an implementation checkpoint.
It supplements [the development workflow](DEVELOPMENT.md); local operational
instructions still govern Git, dependencies, and stage transitions.

## What to include

Keep the final response concise, but include all of the following together:

- What changed, the relevant verification result, and any unresolved limitation
  or required acceptance work. Do not describe a checkpoint as complete while
  required work remains.
- A suggested conventional commit message and the exact repository-relative
  files to stage, following the development workflow. Give copyable staging
  and commit commands when useful; recommendations do not authorize Git writes.
- The next concrete step: its milestone/submilestone identifier, where one
  exists, and the outcome it delivers. Check the accepted plan and current
  worktree rather than relying on an earlier conversation summary. Distinguish
  pending verification of this checkpoint from the next product checkpoint.
- Whether that next step needs no further planning, a short focused planning
  pass, or a dedicated planning session/Plan mode. Briefly identify the open
  decisions. Do not reopen settled product decisions or recommend planning
  solely because a new submilestone starts.
- Separate model and reasoning-effort recommendations for planning and
  implementation, with a short task-specific reason for each. If planning is
  unnecessary, say so and mark its model/effort as not needed.

Recommend the next step without automatically starting it or changing modes.
If an unresolved decision prevents a sound recommendation, state the decision
and ask the maintainer rather than inventing certainty.

## Model and effort selection

Use only the GPT-6 family: Astra (`gpt-6-astra`), Sol (`gpt-6-sol`), or Luna
(`gpt-6-luna`). Allowed efforts are `low`, `medium`, `high`, `xhigh`, and `max`.
**Luna must always use `max`.** Follow any narrower local restrictions.

Choose for the actual work rather than defaulting every phase to the largest
model or highest effort. As project starting points:

- Bounded, straightforward work: Luna / `max` or Sol / `low` to `medium`.
- Routine implementation with established contracts: Sol / `medium` to `high`.
- Complex implementation across scientific, worker, and UI boundaries:
  Sol / `xhigh`.
- Difficult architecture, scientific, numerical, or native-integration
  decisions: Astra / `high`, `xhigh`, or `max`, according to the uncertainty.

Give one specific model and effort per needed phase in the handoff, not a range
or a menu. These are task recommendations, informed by
[OpenAI's model-selection guidance](https://developers.openai.com/api/docs/guides/model-selection),
not a requirement to switch models or delegate. They grant no authority to
change agent definitions, model pins, or routing.

## Compact handoff pattern

After the outcome, verification, and suggested staging/commit commands:

- **Next:** checkpoint and intended result.
- **Planning:** need and scope; model / effort, or not needed.
- **Implementation:** model / effort and brief reason.
