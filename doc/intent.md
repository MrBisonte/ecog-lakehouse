# intent.md

## Why this repository exists

A working example of a governed data platform for implanted neural recordings, built to be shown in one hour and reproduced by anyone with a browser and the DuckDB CLI. It exists to make three claims checkable rather than stated:

1. Governance can execute. Regulatory requirements are rows in a table that generate checks; every run leaves evidence.
2. Open formats on object storage are the right default for this kind of data, and the file layout is a performance decision, not a detail.
3. The author fixes performance problems by changing the design, and can show the before and after with numbers.

## Who it is for

The technical team at a Barcelona neurotechnology company, including the interim data architect, during and after a technical interview. Secondary audience: anyone evaluating the author's data architecture work.

## What it is not

Not a product. Not a claim about how the company's real data is structured. Not a benchmark of DuckDB; the numbers are illustrations of design choices, produced on the author's machine and reproducible from the README.

## Constraints the design accepts

| Constraint | Consequence |
|---|---|
| Public data only | Stanford ECoG library (Miller, 2019), CC BY-SA 4.0. Published derivatives carry the same licence and attribution. |
| No employer code | Everything is written new in this repository. No code from DataLocker, Quackrail or any Dynatrace work. |
| Reproducible by a stranger | One command builds everything from the raw files; one URL runs the governance checks in the browser; two CLI commands reproduce the performance comparison. |
| GitHub Pages as storage | Every published file under 95 MB; total published data under 500 MB; no third-party request at view time. |
| Demo in under five minutes | Four planted faults, each with a fix and a measurement. Nothing else is shown live. |

## Definition of done

- `make all` builds Bronze, Silver, Gold, runs the checks and writes evidence, from either the real data or the synthetic generator.
- The GitHub Pages site loads the Gold layer with DuckDB-WASM, runs the checks and displays the evidence table, with no server.
- The README contains the exact CLI commands for each fault's before and after, and the numbers observed on the author's machine.
- `doc/intent.md`, `doc/spec.md`, `doc/plan.md`, `CLAUDE.md` and `doc/REVIEW.md` are committed and current. Decisions live in `adr/`.
