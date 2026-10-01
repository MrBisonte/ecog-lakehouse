# Lessons learned, phase 1

The first build on real data ran out of memory. This page shows why, what fixed it, and what we got wrong on the way.

Setup: 871,160,120 Silver rows, 12 threads, 15 GB in the WSL VM, DuckDB 1.5.5, memory limit 12.1 GB. Every number is a query result or a timer.

## 1. The cause, in one picture

```
 one query builds a tiny table (45 rows) and joins it to a huge one (871M rows)
                         │
 the planner cannot see that it is tiny: it estimates 907,391,205 rows
                         │
 it plans a join of two huge tables  ──►  12.1 GB used  ──►  out of memory
```

A table computed inside the same statement has no row count. Handed the same 45 rows as a real table, the identical query finishes in about 8 seconds.

## 2. Timeline

```
 download 2 GB ──── stalls at 359 MB        fix: resume with a Range request
 build #1 ───────── Gold: "Cannot allocate memory" writing a spill file
                    the spill folder was the repo, on the Windows mount
                                            fix 1: spill under DATA_DIR/tmp
 build #2 ───────── Gold: out of memory, 12.1 of 12.1 GiB
                                            fix 2: preserve_insertion_order = false
 build #3 ───────── Gold: same, fails in 48 s
                                            fix 3: rewrite the query (section 3)
 build #4 ───────── Gold, checks, publish in 208 s, 103 checks pass
 verifier ───────── clean clone, full build in 513 s, 68 tests
```

Fix 2 changed nothing. Fix 3 is the one that worked.

## 3. The query, before and after

`gold/channel_quality` needs three numbers per record: sample count, RMS, and `clipped_pct`, the share of samples sitting on the rails. The rails are the lowest and highest voltage seen in a run.

**Before:** the rails come from a second pass over all 871M rows, grouped by three label columns.

```
 silver_recording (871M rows)              rails (45 rows, estimated 907M)
        │                                          │
        └────── JOIN on experiment, subject, run ──┘
                         │
          GROUP BY five columns, two of them text
                         │
                 12.1 GB  ──►  out of memory
```

**After:** the big passes read only `lid` and `value_uv`. The rails come from the 2,241 rows the first pass already produced. Labels are joined at the end.

```
 silver_recording (871M rows)
        │
 pass 1: GROUP BY lid  ──►  min, max per record        (2,241 rows)
        │                          │
        │                   rails per run              (42 rows)
        │                          │
 pass 2: JOIN on lid, GROUP BY lid ──►  count, RMS, clipped_pct
        │
 JOIN silver_record for the labels  ──►  2,241 rows
```

`gold/feature_window` got the same treatment.

## 4. The proof

Each test ran twice. Only one thing helps: giving the planner a real row count.

| Test | Result | |
|---|---|---|
| The rails aggregate alone | 45 rows in 1.9 s | ✔ |
| Rails computed inline | out of memory, 27.9 s and 25.7 s | ✘ |
| Rails as a `MATERIALIZED` CTE | out of memory, 22.5 s and 24.1 s | ✘ |
| Group key narrowed to `lid`, rails still inline | out of memory, 17.6 s and 15.5 s | ✘ |
| Rails handed over as a table of the same 45 rows | 2,241 rows in 7.9 s and 7.7 s | ✔ |
| The committed query | 2,241 rows in 6.2 s and 6.3 s | ✔ |

## 5. What we got wrong

Four explanations were written down before they were tested. All four were wrong.

| We said | The test said |
|---|---|
| The estimate sized the final hash table | Inferred, never tested; section 4 points at the join instead |
| The group key was too wide | Narrowed to `lid` alone, it still ran out of memory |
| Variant B is four times faster than A | Remeasured: no gap (section 6) |
| Over a CDN, 38 row groups lose because of 38 round trips | Measured: it is bytes, not round trips (section 8) |

## 6. Three query shapes, timed

Alex asked to compare the committed query with a variant that measures clipping against each record's own extremes.

| Variant | 2026-09-21 | 2026-10-02, three interleaved runs |
|---|---|---|
| A: rails per run | 37.1 s, 39.9 s, 33.5 s | 7.1 s, 6.9 s, 7.8 s |
| B: each record's own extremes | 9.3 s, 8.3 s | 7.1 s, 9.1 s, 6.9 s |
| C: one scan with a window function | 29.9 s | not rerun |
| A with `MATERIALIZED` | 34.3 s | not rerun |

- **The four times gap was not real.** Both plans have the same shape: an 859,640,120 row scan joined to 2,241 rows. A's two extra joins handle 2,241 and 42 rows in 0.00 s.
- **The slow A runs were the machine, not the query.** 8.5 GB of Silver in a 15 GB VM, timed in the hours after the out of memory runs. This is the likeliest cause; it cannot be proven now.
- **The page contradicted itself for eleven days.** Section 4 had the committed query at 6.2 s since 2026-09-25, beside the 33 s here.
- **A and B agree** on count and RMS for all 2,241 records. `clipped_pct` differs on 2,107, because the definition differs, not because of an error.
- **C is not the fastest.** One scan, but the window function has to partition 871M rows by `lid` and spill to disk.
- **Both readings are in the mart** since #25: `clipped_pct` from A, `clipped_own_pct` from B.

## 7. What is in place now

| Piece | Where | Why |
|---|---|---|
| Spill files under `DATA_DIR/tmp` | `pipeline/db.py` | The Windows mount refused the spill file |
| `preserve_insertion_order = false` | `pipeline/db.py` | Did not fix the failure; kept because every `ORDER BY` in `sql/` is explicit |
| Zero byte Parquet removed at connect | `pipeline/db.py`, tested | An aborted write left an empty file that broke the next run |
| Rails derived from the first pass | `sql/gold/010_*.sql`, `030_*.sql` | Section 1 |
| Verifier runs under `$HOME` | `~/verify_phase1.sh` | `/tmp` is a 7.6 GB RAM disk in this WSL and filled up |
| Download with resume | `pipeline/fetch.py` | The Stanford host stalled at 359 MB |

## 8. The same faults against GitHub Pages

Run on the real host instead of the local machine, three things changed.

**The CDN gave one file two identities.** Pages returned ETag `6ab394b5-385b0b5` from one server and `6ab394b4-385b0b5` from another. DuckDB pins the first one, the next request lands on the other server, and the read fails with a 412. The way through is `unsafe_disable_etag_checks`; the sha256 in the manifest is the integrity check that remains.

**Fault A inverted.** The partitioned layout was slower for an aggregate and faster for fetching one record. Measured on 2026-10-02:

| Layout | Size | Aggregate over every row | One record by `lid` |
|---|---|---|---|
| One row group | 52.0 MB | 1.50 s, 21.5 MiB, 11 requests | 1.71 s, 19.5 MiB, 10 requests |
| 38 sorted row groups | 76.3 MB | 3.76 s, 72.7 MiB, 38 requests | 0.65 s, 6.7 MiB, 5 requests |

- The aggregate needs two columns, about 17 MB in either layout. From the 38 row groups DuckDB fetched every row group whole: the full size of the files.
- The partitioned files are 47 percent larger. `ts_ms` and `sample_idx` take 28.9 MB each there, against 17.0 MB each in the single row group. One dictionary over 7.2 million rows compresses what a dictionary per 198,656 sorted rows cannot.
- Partitioning pays when a filter skips row groups. It costs when the query reads every row.
- The layout stays: it is right for the range retrieval `lid_children` does, and the `partition_layout` check demands it.

**Faults D and F held.** D: 5.1 s for the download loop against 0.3 s for one statement. F: 0 of 10 reads succeed without retries, 10 of 10 with.

## 9. Lessons

1. **A table computed in the same statement has no row count.** `MATERIALIZED` does not supply one either.
2. **Test the explanation, do not infer it.** Section 5.
3. **A settings change is a guess until measured.** The setting the error text suggested changed nothing.
4. **Fewest scans is not fastest.** Measure, do not count passes.
5. **A surprising timing gets rerun.** Fresh process, interleaved with its rival, before it is written down.
6. **A failed write is a state.** Clean up empty files and stale spill folders.
7. **Know the machine.** A RAM disk for `/tmp`, a clock that jumps when the host sleeps, a mount that refuses temp files: each cost a run.
8. **Write the definition down before optimising it.** A and B compute different things. Which one is right was Alex's call, not the optimizer's.
9. **Measure on the network the claim is made on.** And write down the claim that did not hold.
