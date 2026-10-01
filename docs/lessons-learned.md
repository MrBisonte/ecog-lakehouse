# Lessons learned, phase 1

One incident, told end to end: the first full build on real data stalled, then ran out of memory twice, and the fix that shipped is not the fastest one measured. Every number below is a query or a timer, from the runs of 2026-09-21 and from the isolation tests of 2026-09-25, on 871,160,120 Silver rows, 12 CPU threads, 15 GB in the WSL VM, DuckDB 1.5.5 with its 12.1 GB default memory limit.

Sections 2, 4 and 6 were rewritten on 2026-09-25. The first account named the cardinality estimate on the final aggregate as the cause, and a second named the width of the group key. Both were inferred rather than tested, and section 5 shows the tests that rule them out.

## 1. Timeline

```
 download 2 GB ─┬─ stall at 359 MB of motor_basic.zip, no bytes for minutes
                └─ curl restarted with --speed-limit, resumed with Range

 make all #1 ───┬─ Bronze  871M rows   ok
                ├─ Silver  45 partitions ok
                └─ Gold 010_channel_quality: "Could not write .tmp/...: Cannot allocate memory"
                   spill directory was the working directory, the repo on the Windows mount

 fix 1: temp_directory = DATA_DIR/tmp

 make all #2 ───── Gold 010: "Out of Memory: 12.1 GiB / 12.1 GiB used"
 fix 2: preserve_insertion_order = false
 make all #3 ───── Gold 010: same 12.1 GiB, 48 s to fail
 fix 3: rails derived from the first pass, both passes keyed by lid (below)
 make all #4 ───── Gold, checks, publish in 208 s, 103 checks pass
 verifier  ─────── clean clone, make all in 513 s, 68 tests
```

Two side effects of the failed runs, both fixed and tested: an aborted `COPY` leaves a zero byte `data_0.parquet`, and the next `db.connect()` refused it ("too small to be a Parquet file"); and a verifier clone under `/tmp` filled that directory, a 7.6 GB tmpfs in this WSL.

## 2. The query that failed

`gold/channel_quality` needs, per record (one `lid`): sample count, RMS, and the share of samples sitting on the run's voltage rails. The rails are the observed extremes of the run, because the files carry no amplifier range.

### Before

The rails were derived inside the same statement, by grouping all 871 million rows by `experiment`, `subject_pid` and `run`. That aggregate returns 45 rows. The optimizer estimates 907,391,205 and plans the join to the 871 million row scan against the estimate. The second pass then grouped five keys, two of them strings, over the joined rows.

```
silver_recording (871M rows)                 rails (45 rows)
 experiment  subject_pid  run  channel  lid  value   <-- VARCHAR, VARCHAR, ...
      |                                                     |
      +---------- HASH JOIN on (experiment, subject_pid, run) --+
                            |     build side: the rails aggregate,
                            |     45 rows, estimated 907,391,205
                  871M rows x (2 strings + uuid + float)
                            |
        HASH GROUP BY (experiment, subject_pid, run, channel, lid)
                            |
                  count, rms, clipped_pct
                            |
                  12.1 GB pinned  ->  OOM
```

### After, what is committed

The heavy passes touch two fixed width columns, `lid` and `value_uv`, and group by `lid`. Everything descriptive is joined afterwards from `silver/record`, one row per record. Rails per run are derived from the per record extremes instead of a second scan with string keys.

```
silver_record (2,433 rows)                  silver_recording (871M rows)
 lid  experiment  subject_pid  run  channel        lid  value      <-- 16 B + 4 B per row
      |                                                 |
      | kept = non canary lids  ----- SEMI JOIN --------+
      |                                                 |
      |                              pass 1: GROUP BY lid -> min, max  (2,241 rows)
      |                                                 |
      +---- rails per run = min/max over the run's records   (42 rows)
      |                                                 |
      +---- rails_by_lid (2,241 rows) -- HASH JOIN on lid (uuid) --+
                                                        |
                             pass 2: GROUP BY lid -> count, rms, clipped_pct
                                                        |
                              JOIN silver_record for the four labels, ORDER BY
                                                        |
                                   2,241 rows, 208 s for all of Gold
```

`gold/feature_window` got the same treatment: group by `lid` and window, labels from `silver/record` afterwards.

## 3. The comparison Alex asked for

Alex's first pick was to drop the rails join and measure clipping against each record's own extremes. Three shapes were timed on the same connection, results into temp tables, nothing written to disk.

| Variant | Shape | Cold cache | Warm cache |
|---|---|---|---|
| A, committed | two passes, rails per run, join on `lid` | 37.1 s | 39.9 s, 33.5 s |
| B, Alex's pick | two passes, each record's own extremes, join on `lid` | 9.3 s | 8.3 s |
| C | one scan, own extremes through `min() OVER (PARTITION BY lid)` | 29.9 s | |
| A with `MATERIALIZED` on both CTEs | as A | | 34.3 s |

Agreement: A and B return identical `n` and `rms` on all 2,241 records. `clipped_pct` differs on 2,107 of them, which is the definition changing, rails per run against rails per record, not an error.

What the numbers say:

- B is four times faster than A on a warm cache, with the same two scans and the same 2,241 row build side keyed by `lid`. Materialising the CTEs did not close the gap, so the cause is in the plan of A, not in CTE inlining. Profiling A is the next step before changing anything.
- C, the single scan, is not the fastest: the window has to hash partition 871 million rows by `lid` and spill, and pays more than a second streaming aggregate.
- The first cold run of A was faster than its warm reruns. With 8.5 GB of Silver in a 15 GB VM, "cold" and "warm" are not clean states here; three warm runs are the number to trust.

Decision pending: the spec defines rails per run, so A stayed. Switching to B is one SQL change plus one spec line, and a verifier rerun.

### Remeasured, 2026-10-02

The gap does not reproduce. Same SQL for A as on 2026-09-21, same engine, DuckDB 1.5.5, 12 threads, results into temp tables on one connection, the two variants interleaved:

| Variant | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| A, rails per run | 7.1 s | 6.9 s | 7.8 s |
| B, own extremes | 7.1 s | 9.1 s | 6.9 s |

- Agreement is as before: 2,241 records, `n` and `rms` identical, `clipped_pct` differing on 2,107.
- `EXPLAIN ANALYZE` shows the same shape for both: the 859,640,120 row scan is the probe side, the build side has 2,241 rows, and A's two extra joins handle 2,241 and 42 rows in 0.00 s. There is nothing in A's plan to cost 30 s.
- So the 33 to 40 s of A was the state of the machine, not the query. The likeliest cause is the one the third bullet above already names: 8.5 GB of Silver in a 15 GB VM, measured in the hours after the out of memory runs, with A timed first. That cannot be proven after the fact, and it is not claimed. Section 5 already had the committed query at 6.2 s and 6.3 s on 2026-09-25, and nobody set that beside the 33 s above.
- The decision is no longer pending: both readings are in the mart since #25, `clipped_pct` from A and `clipped_own_pct` from B, in one pass.

Lesson: a timing that surprises gets rerun in a fresh process, interleaved with its rival, before it is written down as a finding. A four times gap between two plans of the same shape was a measurement to doubt, and it stood in this page for eleven days.

## 4. What is in place now

| Piece | Where | Why |
|---|---|---|
| Spill files under `DATA_DIR/tmp` | `pipeline/db.py` connect | spec 7 puts every DuckDB working file outside the repo; the Windows mount refused the spill |
| `preserve_insertion_order = false` | `pipeline/db.py` connect | every ORDER BY in `sql/` is explicit; the setting alone did not fix the OOM but removes a buffer that serves nothing |
| Zero byte Parquet removed at connect | `pipeline/db.py` views, tested | an aborted write must not break the next run |
| `channel_quality` and `feature_window` derive their rails from the first pass | `sql/gold/010_*.sql`, `sql/gold/030_*.sql` | the planner has no row count for an aggregate computed in the same statement; deriving the rails from 2,241 already aggregated rows keeps the join's build side small |
| Verifier under `$HOME` | `~/verify_phase1.sh` | `/tmp` is a 7.6 GB tmpfs |
| Download with stall detection and resume | `pipeline/fetch.py` Range header; curl `--speed-limit` during the session | the Stanford host stalled once at 359 MB |

## 5. What was tested

Each row is two runs on the rebuilt lakehouse, DuckDB 1.5.5, 12.1 GB limit, results materialised so no aggregate expression is pruned.

| Test | Result |
|---|---|
| The rails aggregate on its own | 45 rows in 1.9 s |
| The mart, rails as an inline CTE | out of memory, 27.9 s and 25.7 s |
| The mart, rails as a `MATERIALIZED` CTE | out of memory, 22.5 s and 24.1 s |
| The mart, rails handed over as a table of the same 45 rows | 2,241 rows in 7.9 s and 7.7 s |
| The mart, group key narrowed to `lid`, rails still a CTE | out of memory, 17.6 s and 15.5 s |
| The committed query | 2,241 rows in 6.2 s and 6.3 s |

## 6. Lessons

1. **An aggregate computed in the same statement has no row count.** The rails aggregate returns 45 rows and the planner estimates 907,391,205, so the join to the 871 million row scan is planned against the estimate. Handed the same 45 rows as a table, the identical query completes in about 8 seconds. `MATERIALIZED` does not help, because it does not supply a row count either.
2. **Test the explanation, do not infer it.** Two explanations were written down before they were tested and both were wrong: that the estimate sized the final hash table, and that the width of the group key was the cause. Narrowing the group key from five columns to `lid` alone leaves the failure unchanged, in two runs. The evidence is in the table below.
3. **A settings change is a guess until measured.** `preserve_insertion_order` was the documented first suggestion in the error text and changed nothing here. It stayed because it is right, not because it helped.
4. **Fewest scans is not fastest.** The window variant scans once and loses to two streaming aggregates. Measure, do not count passes.
5. **Compare on equal footing.** Cold then warm in sequence flatters the second query. Repeat, alternate, and report the spread.
6. **A failed write is a state, handle it.** Zero byte files and stale spill directories broke the next run twice. The pipeline now cleans what it can and puts the rest where the spec says.
7. **Know the machine.** `/tmp` as tmpfs, a clock that jumps when the host sleeps, a mount that reports ENOMEM on a temp file: none of these were in the plan and all three cost a run.
8. **Write the definition down before optimising it.** B computes something else, and its speed was a measurement artefact, section 3. The spec's rails per run is the reason A stayed, and the reason the choice was Alex's, not the optimizer's. Both readings are in the mart now.

## 7. Addendum, the same faults against GitHub Pages

The tables in section 3 were loopback. With Pages on and `BASE_URL` pointing at it, three things changed the picture.

- **The CDN lies about identity.** Pages returned `6ab394b5-385b0b5` for a file from one Fastly edge and `6ab394b4-385b0b5` from another. DuckDB pins the first ETag with If-Match, the next range request lands on the other edge, 412. The read that worked on loopback failed on the real host. `unsafe_disable_etag_checks` is the documented way through, and the sha256 in the manifest is the integrity check that remains. Lesson: a correctness check inside the client can fail on infrastructure the client does not control; know which check you are relying on.
- **Fault A inverted.** Loopback showed no gap; Pages showed the partitioned layout slower, 2.7 s against 1.0 s. The first explanation written here, 38 row groups are 38 round trips, was a guess. Measured on 2026-10-02, it is bytes: the aggregate needs two columns, about 17 MB in either layout; from the single row group DuckDB fetched 21.5 MiB in 11 requests, from the 38 row groups it fetched 72.7 MiB in 38, every row group whole, the file's full size. The partitioned files are also 47 percent larger, 76.3 MB against 52.0 MB: `ts_ms` and `sample_idx` take 28.9 MB each where the single row group stores each in 17.0 MB, because one dictionary over 7.2 million rows compresses what a dictionary per 198,656 sorted rows cannot. The same day, the retrieval the layout exists for, one record by `lid`: 0.65 s, 5 requests and 6.7 MiB partitioned, against 1.71 s, 10 requests and 19.5 MiB from the single row group. Partitioning pays when a predicate prunes row groups, and costs when the query reads every row. The layout is still right for the range retrieval that `lid_children` does, and still what the partition_layout check demands, but the "faster aggregate" claim needs a file big enough for parallel streams to beat request latency. Lesson: measure the claim on the network it will be made on, and write down the one that did not hold.
- **Fault D and F held.** 5.1 s against 0.3 s for the download loop; 0 of 10 against 10 of 10 without and with retries. The stories that are about request count and failure handling survive real latency; the one about parallel streams did not at this size.
