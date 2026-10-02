# Intent

## Why

A governed lakehouse over implanted neural recordings that anyone can rebuild and check. It makes three claims checkable:

1. Governance can execute. Requirements are rows in a table that generate checks. Every run leaves evidence.
2. Open formats on static storage are a sound default here, and file layout is a performance decision.
3. A performance problem is fixed by changing the design. Each planted fault sits beside its fix, measured before and after.

## For whom

Data engineers who want a governed lakehouse to read end to end, every number traceable to its bytes.

## What it is not

Not a product. Not a model of any organisation's real data. Not a DuckDB benchmark: the timings illustrate design choices, and `docs/bench.md` names the host and engine of each.

## Constraints

| Constraint | Consequence |
|---|---|
| Public data only | Stanford ECoG library (Miller, 2019), CC BY-SA 4.0. Derivatives carry the same licence. |
| Original code only | Everything is written new here. |
| Reproducible by a stranger | One command builds every layer. One URL reruns the checks in a browser. |
| GitHub Pages as storage | Files under 95 MB, `docs/data/` under 500 MB, no third-party request but the pinned DuckDB-WASM CDN. |

## Definition of done

- `make all` builds Bronze, Silver and Gold, runs the checks, writes evidence and publishes. `SYNTH=1` uses generated data.
- The site loads Gold with DuckDB-WASM, reruns the checks and verifies the file digests, with no server.
- `make bench` measures each fault before and after into `docs/bench.md`.
- CI runs `make lint`, `make test` and `make all SYNTH=1` on every pull request.
- `doc/spec.md` is the contract. Decisions live in `adr/`, review passes in `doc/REVIEW.md`.
