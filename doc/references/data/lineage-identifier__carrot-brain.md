# Lineage identifier

Source: the trace and decode functions the author built for the C3 commission platform at Carrot (2017 to 2024), where an identifier accumulated a sequence from the previous record in the processing chain and a decode function returned the chain up to the source. Redesigned for a lakehouse in this repository; the specification is `doc/spec.md` section 12 and the decision is `adr/ADR-0004.md`.

| From C3 | Here | Why it changed |
|---|---|---|
| Identifier decodes to its full ancestry without a join | Same | The whole point |
| Trace back and trace forward as first-class functions | `lid_trace`, `lid_children`, `lid_parent` | Same |
| Sequence accumulated from the previous record | Position encoded in fixed bit fields | Parallel writers and reruns need a deterministic, order-free scheme |
| Integer key in a relational table | 128-bit ULID-shaped UUID | Sorts, indexes and prunes in Parquet, DuckDB and PostgreSQL alike; text form for humans |
| Integrity implied by the chain | Integrity separate: file digest and dataset digest | Per-row hashing costs more than it proves; digests at file and dataset level cover Part 11 |
