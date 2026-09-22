# Lessons learned, phase 1

One incident, told end to end: the first full build on real data stalled, then ran out of memory twice, and the fix that shipped is not the fastest one measured. Every number below is a query or a timer from the runs of 2026-09-21 on 871,160,120 Silver rows, 12 CPU threads, 15 GB in the WSL VM, DuckDB 1.5.5 with its 12.1 GB default memory limit.

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
 fix 3: lid keyed passes (below)
 make all #4 ───── Gold, checks, publish in 208 s, 103 checks pass
 verifier  ─────── clean clone, make all in 513 s, 68 tests
```

Two side effects of the failed runs, both fixed and tested: an aborted `COPY` leaves a zero byte `data_0.parquet`, and the next `db.connect()` refused it ("too small to be a Parquet file"); and a verifier clone under `/tmp` filled that directory, a 7.6 GB tmpfs in this WSL.

## 2. The query that failed

`gold/channel_quality` needs, per record (one `lid`): sample count, RMS, and the share of samples sitting on the run's voltage rails. The rails are the observed extremes of the run, because the files carry no amplifier range.

### Before

One pass over Silver carried five group keys, three of them strings, through a join whose probe side was every sample row. The optimizer estimated 164 million groups, so the hash aggregate was sized for that, and every in-flight row held two heap allocated strings plus a UUID.

```
silver_recording (871M rows)                 rails (2.4k rows)
 experiment  subject_pid  run  channel  lid  value   <-- VARCHAR, VARCHAR, ...
      |                                                     |
      +---------- HASH JOIN on (experiment, subject_pid, run) --+
                            |
                  871M rows x (2 strings + uuid + float)
                            |
        HASH GROUP BY (experiment, subject_pid, run, channel, lid)
              estimated 164M groups, sized for that
                            |
                  count, rms, clipped_pct
                            |
                  12.1 GB pinned  ->  OOM
```

### After, what is committed

The heavy passes touch two fixed width columns, `lid` and `value_uv`, and group by `lid`. Everything descriptive is joined afterwards from `silver/record`, one row per record. Rails per run are derived from the per record extremes instead of a second scan with string keys.

```
silver_record (2.4k rows)                   silver_recording (871M rows)
 lid  experiment  subject_pid  run  channel        lid  value      <-- 16 B + 4 B per row
      |                                                 |
      | kept = non canary lids  ----- SEMI JOIN --------+
      |                                                 |
      |                              pass 1: GROUP BY lid -> min, max   (2.4k rows)
      |                                                 |
      +---- rails per run = min/max over the run's records (2.4k rows)
      |                                                 |
      +---- rails_by_lid (2.4k rows) -- HASH JOIN on lid (uuid) --+
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

## 4. What is in place now

| Piece | Where | Why |
|---|---|---|
| Spill files under `DATA_DIR/tmp` | `pipeline/db.py` connect | spec 7 puts every DuckDB working file outside the repo; the Windows mount refused the spill |
| `preserve_insertion_order = false` | `pipeline/db.py` connect | every ORDER BY in `sql/` is explicit; the setting alone did not fix the OOM but removes a buffer that serves nothing |
| Zero byte Parquet removed at connect | `pipeline/db.py` views, tested | an aborted write must not break the next run |
| `channel_quality` and `feature_window` keyed by `lid` | `sql/gold/010_*.sql`, `sql/gold/030_*.sql` | fixed width keys through the heavy passes, labels joined once per record |
| Verifier under `$HOME` | `~/verify_phase1.sh` | `/tmp` is a 7.6 GB tmpfs |
| Download with stall detection and resume | `pipeline/fetch.py` Range header; curl `--speed-limit` during the session | the Stanford host stalled once at 359 MB |

## 5. Lessons

1. **Fixed width keys through the heavy pass, strings afterwards.** A 16 byte UUID per row costs 14 GB over 871 million rows; two VARCHAR keys on top of it cost the memory limit. Join the labels once per record, never once per sample.
2. **Look at the cardinality estimate before the memory.** "Estimated 164,482,128 groups" for 2,241 real ones was in the profile of the failing query. The estimate sized the hash table; the strings filled it.
3. **A settings change is a guess until measured.** `preserve_insertion_order` was the documented first suggestion in the error text and changed nothing here. It stayed because it is right, not because it helped.
4. **Fewest scans is not fastest.** The window variant scans once and loses to two streaming aggregates. Measure, do not count passes.
5. **Compare on equal footing.** Cold then warm in sequence flatters the second query. Repeat, alternate, and report the spread.
6. **A failed write is a state, handle it.** Zero byte files and stale spill directories broke the next run twice. The pipeline now cleans what it can and puts the rest where the spec says.
7. **Know the machine.** `/tmp` as tmpfs, a clock that jumps when the host sleeps, a mount that reports ENOMEM on a temp file: none of these were in the plan and all three cost a run.
8. **Write the definition down before optimising it.** B is faster because it computes something else. The spec's rails per run is the reason A is still in place, and the reason the choice is Alex's, not the optimizer's.
