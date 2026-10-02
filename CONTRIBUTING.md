# Contributing

Setup, build and reset are in [docs/manual.md](docs/manual.md).

## Propose a change

1. Branch from `master`: `git switch -c <type>/<short-description>`.
2. Before every commit: `make lint && make test`.
3. To build without the download: `make all SYNTH=1`.
4. Open a pull request against `master`.

## Commits

- Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `chore:`.
- One logical change per commit.

## Rules

| Rule | Why |
|---|---|
| Commas, never dashes | `make lint` fails on an em or en dash. |
| Every number is a query result | A number typed by hand goes stale. |
| Data lives in `DATA_DIR`, outside the repository | `docs/data/` is the one published copy inside it. |
| `doc/spec.md` is the contract | If code and spec disagree, fix one and say which. |
