# AI-native SDLC and the coordination ledger

Source: Quackrail and crow-archer, where the author runs multi-agent builds following the AI-native SDLC playbook (claude.com/blog/the-ai-native-sdlc-playbook).

## Committed artefacts

| File | Holds |
|---|---|
| `doc/intent.md` | Why the repository exists, for whom, what it is not, definition of done |
| `doc/spec.md` | The contract: schemas, behaviour, limits |
| `doc/plan.md` | Phases, order, budget, risks, not doing |
| `CLAUDE.md` | Under one page: stack, rules, commands, hooks, review cadence |
| `doc/REVIEW.md` | One entry per phase: checked, failed, changed |
| `adr/` | Decisions |

## Working rules

- Plan mode before build. The agent proposes a numbered plan and waits.
- Hooks as guardrails: lint and tests on every commit; red never commits.
- A verifier subagent reruns the build from a clean clone before a phase is marked done.
- One commit per plan step, Conventional Commits.
- Guesses are allowed and must be listed in the report.

## Coordination ledger

When more than one agent works on the repository, a `COORDINATION.md` ledger at the root tracks who owns what: one row per work item with owner, branch, status, blocker. The ledger is local only and removed from the public tree before publishing. Not needed in phase 0; add it the moment a second agent starts.
