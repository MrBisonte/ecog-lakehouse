# The ponytail ladder

Source: the author's `ponytail` skill family (ponytail, ponytail-review, ponytail-audit, ponytail-debt). Lazy means efficient, not careless. The best code is the code never written.

## Ladder, stop at the first rung that holds

1. Does this need to exist at all? Speculative need is skipped, and said so in one line.
2. Already in this codebase? Reuse it.
3. Standard library does it? Use it.
4. Native platform feature covers it? A database constraint over application code, CSS over JavaScript.
5. An already installed dependency solves it? Use it. Never add one for what a few lines can do.
6. Can it be one line? One line.
7. Only then: the minimum code that works.

## Rules

- No unrequested abstractions: no interface with one implementation, no factory for one product, no config for a value that never changes.
- No scaffolding for later.
- Deletion over addition. Boring over clever.
- Bug fix means root cause: one guard where all callers route through, not a patch in the path the ticket names.
- Deliberate shortcuts with a known ceiling carry a `ponytail:` comment naming the ceiling and the upgrade path. `ponytail-debt` harvests them into a ledger.
- Output pattern: code, then at most three lines: what was skipped, when to add it.
