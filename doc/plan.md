# plan.md

Built in the week of 21 September 2026. Phases are ordered so that a demo exists after phase 2 even if nothing else lands. D means the publish day.

| Phase | When | Where | Work | Done when |
|---|---|---|---|---|
| 0 Skeleton | Sat 19 Sep, here | Claude chat, container | Repo layout, `CLAUDE.md`, `Makefile`, synthetic generator, Bronze to Gold SQL, contracts, requirements table, check generator, evidence, tests. All run on synthetic data | `make all SYNTH=1` passes in the container; zip handed over |
| 1 Real data | Sat 19 to Sun 20 | Claude Code on WSL2 | `make fetch` for two or three experiments, one adapter per experiment in `convert_mat.py`, sha256 in `governance/sources.csv`. Replace synthetic with real | `make all` passes on real data; row counts in `docs/bench.md` |
| 2 Faults and bench | Sun 20 | Claude Code on WSL2 | Faults A, D, F, G with plant, fix and bench. DuckDB v2.0 alpha CLI installed, exact build recorded. Publish fault files under `docs/data/faults/` | `make bench` writes four before and after tables |
| 3 Site | Mon 21 | Claude Code on WSL2 | `docs/index.html` with DuckDB-WASM, evidence and summary tables, manifest. Enable GitHub Pages from `docs/` on a private repo first | Page loads and runs checks from a stranger's browser |
| 4 Rehearsal | D minus 1 | Chat plus a timer | Five-minute run through: README on screen, page, fault A live, one of D, F or G, close. Fix what breaks | Two clean rehearsals under five minutes |
| 5 Publish | D, one hour before | GitHub | Flip the repository to public, confirm the Pages URL, confirm the two README commands work from a clean shell | URL in the README |

## Budget

| Phase | Estimate |
|---|---|
| 0 | This session |
| 1 | 2 to 3 hours of Claude Code, download time dominated by the Stanford repository |
| 2 | 2 hours |
| 3 | 1 to 2 hours |
| 4 | 30 minutes |

## Order inside phase 0

1. `CLAUDE.md`, `Makefile`, `pyproject.toml`, `.gitignore` (`data/`, `keyring.duckdb`, `*.mat`)
2. `pipeline/synth.py`: three subjects, two experiments, 64 channels, 60 s at 1 kHz, events every 2 s, one NaN burst per subject to exercise `missing_samples`
3. `sql/bronze/*.sql`, `pipeline/convert_mat.py` with the synthetic adapter only
4. `sql/silver/*.sql`, keyring creation, pseudonymisation
5. `sql/gold/*.sql`, line noise in Python
6. `contracts/*.yaml`, `governance/requirements.csv`, `pipeline/checks.py`, evidence
7. `tests/`: contracts match SQL output, evidence is append-only, `no_direct_identifier` fails when `subject_src` leaks into Silver, generator rejects malformed SQL
8. `REVIEW.md` first pass

## Risks

| Risk | Mitigation |
|---|---|
| DuckDB v2.0 alpha not available for WSL2 or broken | Fault A bench falls back to v1.5.x with `ROW_GROUP_SIZE` variations only; the async comparison is described from the DuckDB post's numbers with a note |
| `.mat` files are v7.3 (HDF5) for some experiments | Adapter uses `h5py` for those; add to dependencies only if needed |
| Stanford download is slow or a file is missing | Synthetic fallback keeps `make all` green; publish what converted |
| GitHub Pages caching hides a republished file | Cache-busting query string on the manifest; bench uses raw file URLs |
| Demo laptop network is slow on the day | Numbers from `docs/bench.md` are on screen even if the live run stalls |
| Async I/O not in DuckDB-WASM | Site is governance only; performance stays in the CLI, as decided |

## Not doing

Wide layout for recordings, Iceberg or Delta catalogue, Azure deployment, FFT in SQL, any authentication on the page, any front-end framework.
