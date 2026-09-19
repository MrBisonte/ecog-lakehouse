# Data contracts and validation stages

Source: DataLocker, the author's data contract validation engine (personal repository, unpublished at the time of writing). Only the pattern is carried over; no code.

## The pattern

Validation is a pipeline stage, not a report. Checks run at four points and each point asks a different question.

```
 source ──► PRE_INGEST ──► ingest ──► POST_INGEST ──► store ──► PRE_FETCH ──► fetch ──► POST_FETCH ──► consumer
             is the input      did we store         may this      did the consumer
             what it says    what we read         consumer      receive what the
             it is            without loss         read this     contract promises
```

| Stage | Question | Typical checks |
|---|---|---|
| PRE_INGEST | Is the input what it says it is? | file digest, schema presence, sample rate, row count bounds |
| POST_INGEST | Did we store what we read without loss? | row counts match, digest recorded, no NULL where the source had values |
| PRE_FETCH | May this consumer read this? | no direct identifiers, retention not exceeded, contract version matches |
| POST_FETCH | Did the consumer receive what the contract promises? | column set and types, uniqueness, freshness |

## Rules carried over

- Every check is declared in metadata and executed by an engine; no check lives only in code.
- A failing check blocks the stage; it does not log and continue.
- Evidence of every run is stored with the run, queryable, never overwritten.
- The engine runs inside the analytical database (DuckDB), so checks are SQL and cost nothing to deploy.

## Applied here

`pipeline/checks.py` implements PRE_INGEST (hash_match), POST_INGEST (row_count_min, partition_layout, unique, not_null) and PRE_FETCH (no_direct_identifier, retention). POST_FETCH is exercised by the browser page rerunning the same checks on the published slice. A stage column is added to `governance/requirements.csv` when phase 1 lands.
