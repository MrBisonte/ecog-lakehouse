# Five records, end to end

Five records enter as samples in a `.mat` file and travel to Gold, evidence and the published copy. This page shows their complete tuples at every stage, so the lineage identifier can be watched changing while everything else stays put. Every value is a query result from one build of the synthetic data; digests, paths and commits are cut to their first characters for width, the full values sit in the tables they came from.

Each transformation has its source SQL folded under the paragraph that introduces its result, click the line to open it. Closed, the page is data and flow only.

## 0. Who travels

| n | Experiment | Source subject | Channel | Why this one |
|---|---|---|---|---|
| 1 | fingerflex | aa | 0 | has the NaN burst and the injected 50 Hz tone |
| 2 | motor_basic | aa | 5 | clean channel, same subject as 1 |
| 3 | fingerflex | bb | 1 | has the NaN burst, another subject |
| 4 | motor_basic | cc | 3 | clean channel, third subject |
| 5 | fingerflex | canary | 3 | the planted canary, must stop at Silver |

The source subject code appears in this page only because the data is synthetic. In the real system it exists in Bronze and the keyring alone; a page like this one would be generated from Silver.

## 1. The map

```mermaid
flowchart LR
  F[.mat file<br>sha256] -->|convert| A[ingest_audit<br>ingest_ord, ts_ms]
  A --> B[Bronze<br>lid layer 1<br>...CH<b>2</b>08...]
  B -->|relayer, validate| S[Silver<br>lid layer 2<br>...CH<b>4</b>08...]
  S -->|relayer, validate| G[Gold<br>lid layer 3<br>...CH<b>6</b>08...]
  G --> E[evidence<br>dataset_version]
  G --> M[dataset_manifest<br>lid_lo, lid_hi]
  G --> P[docs/data<br>sha256 per file]
```

One character of the identifier's text form moves as a record climbs: `2`, `4`, `6` at position 11. Everything else in the identifier is fixed at conversion time.

## 2. The file becomes an audit row

`convert_mat.py` hashes the file, writes the Bronze rows, then appends one audit row. The row never changes.

<details>
<summary>sql/bronze/ingest_audit.sql</summary>

```sql
-- bronze/ingest_audit, spec 3.1. One file per converted source file, never rewritten.
COPY (
    SELECT
        '{{ingest_id}}' AS ingest_id,
        '{{source_path}}' AS source_path,
        '{{source_url}}' AS source_url,
        '{{sha256}}' AS sha256,
        {{bytes}}::BIGINT AS bytes,
        {{sample_rate_hz}}::INTEGER AS sample_rate_hz,
        {{rows_written}}::BIGINT AS rows_written,
        '{{tool}}' AS tool,
        '{{tool_version}}' AS tool_version,
        '{{duckdb_version}}' AS duckdb_version,
        TIMESTAMP '{{ingested_at}}' AS ingested_at
) TO '{{data_dir}}/bronze/ingest_audit/{{ingest_id}}.parquet' (FORMAT parquet);
```

</details>

| ingest_id | source_path | source_url | sha256 | bytes | sample_rate_hz | rows_written | tool | tool_version | duckdb_version | ingested_at |
|---|---|---|---|---|---|---|---|---|---|---|
| 01M30739CGE2JX4EXKR65BTC6E | fingerflex/aa.mat | synthetic://fingerflex/aa.mat | 65c157a67f68 | 15485896 | 1000 | 3840000 | convert_mat.py | 868ab53 | 1.5.5 | 2026-09-20 20:11:08.561115 |
| 01M3073A6E8SR2B7JF97DG0H07 | fingerflex/bb.mat | synthetic://fingerflex/bb.mat | 51bdb94158ef | 15485896 | 1000 | 3840000 | convert_mat.py | 868ab53 | 1.5.5 | 2026-09-20 20:11:09.391338 |
| 01M3073AZA3B2PSZTSGH07Y31Y | fingerflex/canary.mat | synthetic://fingerflex/canary.mat | b8a002899aac | 15485904 | 1000 | 3840000 | convert_mat.py | 868ab53 | 1.5.5 | 2026-09-20 20:11:10.188543 |
| 01M3073CEHVGSATDYM49B26G2H | motor_basic/aa.mat | synthetic://motor_basic/aa.mat | d78878cdb442 | 15485896 | 1000 | 3840000 | convert_mat.py | 868ab53 | 1.5.5 | 2026-09-20 20:11:11.698465 |
| 01M3073EJFREB8YATMZYFR5981 | motor_basic/cc.mat | synthetic://motor_basic/cc.mat | c96c66f737e3 | 15485896 | 1000 | 3840000 | convert_mat.py | 868ab53 | 1.5.5 | 2026-09-20 20:11:13.872694 |

`lineage_dim` is a view over the audit. It numbers the files in ingestion order and gives each its first ingestion time in milliseconds; both go into every identifier of that file.

<details>
<summary>sql/lineage/lid_extras.sql, lineage_dim</summary>

```sql
CREATE OR REPLACE VIEW lineage_dim AS
SELECT
    row_number() OVER (ORDER BY a.ingested_at, a.sha256)::SMALLINT AS ingest_ord,
    a.ingest_id,
    a.source_path,
    a.source_url,
    a.sha256,
    epoch_ms(a.ingested_at) AS ts_ms,
    r.experiment
FROM bronze_ingest_audit a
LEFT JOIN (SELECT DISTINCT experiment, ingest_id FROM bronze_recording) r USING (ingest_id);
```

</details>

| ingest_ord | ingest_id | sha256 | ts_ms | experiment |
|---|---|---|---|---|
| 1 | 01M30739CGE2JX4EXKR65BTC6E | 65c157a67f68 | 1789935068561 | fingerflex |
| 2 | 01M3073A6E8SR2B7JF97DG0H07 | 51bdb94158ef | 1789935069391 | fingerflex |
| 3 | 01M3073AZA3B2PSZTSGH07Y31Y | b8a002899aac | 1789935070188 | fingerflex |
| 5 | 01M3073CEHVGSATDYM49B26G2H | d78878cdb442 | 1789935071698 | motor_basic |
| 8 | 01M3073EJFREB8YATMZYFR5981 | c96c66f737e3 | 1789935073872 | motor_basic |

Files 4, 6 and 7 exist; they hold subjects this page does not follow.

## 3. The identifier is minted

One identifier per record, that is per file, run and channel. 128 bits, most significant first:

```
 ts_ms 48 | layer 4 | experiment 8 | reserved 4 || file 16 | run 4 | channel 10 | segment 10 | radioactive 1 | reserved 23
 hi word                                          lo word
```

Decoded, the five Bronze identifiers say exactly where each record sits. The canary's last field is 1.

| n | lid | ts_ms | layer | experiment | file | run | channel | segment | radioactive |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 01M30739CH2080008G00000000 | 1789935068561 | 1 | 1 | 1 | 1 | 0 | 0 | 0 |
| 2 | 01M3073CEJ20G0018G2G000000 | 1789935071698 | 1 | 2 | 5 | 1 | 5 | 0 | 0 |
| 3 | 01M3073A6F208000GG0G000000 | 1789935069391 | 1 | 1 | 2 | 1 | 1 | 0 | 0 |
| 4 | 01M3073EJG20G0020G1G000000 | 1789935073872 | 1 | 2 | 8 | 1 | 3 | 0 | 0 |
| 5 | 01M3073AZC208000RG1G080000 | 1789935070188 | 1 | 1 | 3 | 1 | 3 | 0 | 1 |

Experiment codes: 1 fingerflex, 2 motor_basic. The file number is `ingest_ord` from the table above.

<details>
<summary>sql/bronze/recording.sql, the mint, one lid per channel</summary>

```sql
    JOIN (
        SELECT
            channel_idx,
            lid_to_uuid(lid_encode(epoch_ms(TIMESTAMP '{{ingested_at}}'), 1, {{experiment_code}},
                                {{ingest_ord}}, {{run}}, channel_idx, 0, {{radioactive}})) AS lid
        FROM (SELECT DISTINCT channel_idx FROM src_recording)
    ) l USING (channel_idx)
```

</details>

## 4. Bronze, raw and complete

Samples, one row each, in the file's own units, with the source subject code and the layer 1 identifier of their record. Two samples per record: the first, and one inside the burst that three of the files carry at second 30.

<details>
<summary>sql/bronze/recording.sql</summary>

```sql
-- bronze/recording, spec 3.1. One row per sample, raw units, NaN kept.
-- The lid is computed once per record (channel) and joined, not once per sample.
COPY (
    SELECT
        '{{experiment}}' AS experiment,
        '{{subject_src}}' AS subject_src,
        {{run}}::SMALLINT AS run,
        r.channel_idx::SMALLINT AS channel_idx,
        r.sample_idx::INTEGER AS sample_idx,
        r.value_raw::FLOAT AS value_raw,
        '{{ingest_id}}' AS ingest_id,
        l.lid
    FROM src_recording r
    JOIN (
        SELECT
            channel_idx,
            lid_to_uuid(lid_encode(epoch_ms(TIMESTAMP '{{ingested_at}}'), 1, {{experiment_code}},
                                {{ingest_ord}}, {{run}}, channel_idx, 0, {{radioactive}})) AS lid
        FROM (SELECT DISTINCT channel_idx FROM src_recording)
    ) l USING (channel_idx)
) TO '{{data_dir}}/bronze/recording'
(FORMAT parquet, PARTITION_BY (experiment, subject_src, ingest_id), WRITE_PARTITION_COLUMNS, APPEND);
```

</details>

| n | experiment | subject_src | run | channel_idx | sample_idx | value_raw | ingest_id | lid |
|---|---|---|---|---|---|---|---|---|
| 1 | fingerflex | aa | 1 | 0 | 0 | 61.942 | 01M30739CGE2JX4EXKR65BTC6E | 01M30739CH2080008G00000000 |
| 1 | fingerflex | aa | 1 | 0 | 30250 | NULL | 01M30739CGE2JX4EXKR65BTC6E | 01M30739CH2080008G00000000 |
| 2 | motor_basic | aa | 1 | 5 | 0 | 191.232 | 01M3073CEHVGSATDYM49B26G2H | 01M3073CEJ20G0018G2G000000 |
| 2 | motor_basic | aa | 1 | 5 | 30250 | 30.633 | 01M3073CEHVGSATDYM49B26G2H | 01M3073CEJ20G0018G2G000000 |
| 3 | fingerflex | bb | 1 | 1 | 0 | 129.158 | 01M3073A6E8SR2B7JF97DG0H07 | 01M3073A6F208000GG0G000000 |
| 3 | fingerflex | bb | 1 | 1 | 30250 | NULL | 01M3073A6E8SR2B7JF97DG0H07 | 01M3073A6F208000GG0G000000 |
| 4 | motor_basic | cc | 1 | 3 | 0 | -91.151 | 01M3073EJFREB8YATMZYFR5981 | 01M3073EJG20G0020G1G000000 |
| 4 | motor_basic | cc | 1 | 3 | 30250 | -32.514 | 01M3073EJFREB8YATMZYFR5981 | 01M3073EJG20G0020G1G000000 |
| 5 | fingerflex | canary | 1 | 3 | 0 | 123.349 | 01M3073AZA3B2PSZTSGH07Y31Y | 01M3073AZC208000RG1G080000 |
| 5 | fingerflex | canary | 1 | 3 | 30250 | NULL | 01M3073AZA3B2PSZTSGH07Y31Y | 01M3073AZC208000RG1G080000 |

The burst arrives as NULL: the file holds NaN, and DuckDB reads NaN from the numpy array as NULL. Bronze keeps the row; the gap is counted later, not hidden.

Electrodes, one row per channel, same identifier as the samples of that channel.

<details>
<summary>sql/bronze/electrode.sql</summary>

```sql
-- bronze/electrode, spec 3.1. One row per channel, NULL where the file has no location.
COPY (
    SELECT
        '{{experiment}}' AS experiment,
        '{{subject_src}}' AS subject_src,
        channel_idx::SMALLINT AS channel_idx,
        x_mm::FLOAT AS x_mm,
        y_mm::FLOAT AS y_mm,
        z_mm::FLOAT AS z_mm,
        brain_area::VARCHAR AS brain_area,
        '{{ingest_id}}' AS ingest_id,
        lid_to_uuid(lid_encode(epoch_ms(TIMESTAMP '{{ingested_at}}'), 1, {{experiment_code}},
                            {{ingest_ord}}, {{run}}, channel_idx, 0, {{radioactive}})) AS lid
    FROM src_electrode
) TO '{{data_dir}}/bronze/electrode'
(FORMAT parquet, PARTITION_BY (experiment, subject_src), WRITE_PARTITION_COLUMNS, APPEND);
```

</details>

| n | experiment | subject_src | channel_idx | x_mm | y_mm | z_mm | brain_area | ingest_id | lid |
|---|---|---|---|---|---|---|---|---|---|
| 1 | fingerflex | aa | 0 | 0.000 | 0.000 | 40.000 | precentral | 01M30739CGE2JX4EXKR65BTC6E | 01M30739CH2080008G00000000 |
| 2 | motor_basic | aa | 5 | 50.000 | 0.000 | 40.000 | postcentral | 01M3073CEHVGSATDYM49B26G2H | 01M3073CEJ20G0018G2G000000 |
| 3 | fingerflex | bb | 1 | 10.000 | 0.000 | 40.000 | postcentral | 01M3073A6E8SR2B7JF97DG0H07 | 01M3073A6F208000GG0G000000 |
| 4 | motor_basic | cc | 3 | 30.000 | 0.000 | 40.000 | temporal | 01M3073EJFREB8YATMZYFR5981 | 01M3073EJG20G0020G1G000000 |
| 5 | fingerflex | canary | 3 | 30.000 | 0.000 | 40.000 | temporal | 01M3073AZA3B2PSZTSGH07Y31Y | 01M3073AZC208000RG1G080000 |

Events belong to the run, not to a channel, so their identifier has channel 0. The first cue of each file:

<details>
<summary>sql/bronze/event.sql</summary>

```sql
-- bronze/event, spec 3.1. One row per cue onset. Events belong to the run, not to a channel,
-- so their lid carries channel 0.
COPY (
    SELECT
        '{{experiment}}' AS experiment,
        '{{subject_src}}' AS subject_src,
        {{run}}::SMALLINT AS run,
        e.sample_idx::INTEGER AS sample_idx,
        e.event_code::SMALLINT AS event_code,
        l.event_label::VARCHAR AS event_label,
        '{{ingest_id}}' AS ingest_id,
        lid_to_uuid(lid_encode(epoch_ms(TIMESTAMP '{{ingested_at}}'), 1, {{experiment_code}},
                            {{ingest_ord}}, {{run}}, 0, 0, {{radioactive}})) AS lid
    FROM src_event e
    LEFT JOIN src_label l USING (event_code)
) TO '{{data_dir}}/bronze/event'
(FORMAT parquet, PARTITION_BY (experiment, subject_src), WRITE_PARTITION_COLUMNS, APPEND);
```

</details>

| n | experiment | subject_src | run | sample_idx | event_code | event_label | ingest_id | lid |
|---|---|---|---|---|---|---|---|---|
| 1 | fingerflex | aa | 1 | 0 | 1 | thumb | 01M30739CGE2JX4EXKR65BTC6E | 01M30739CH2080008G00000000 |
| 2 | motor_basic | aa | 1 | 0 | 1 | hand | 01M3073CEHVGSATDYM49B26G2H | 01M3073CEJ20G0018G00000000 |
| 3 | fingerflex | bb | 1 | 0 | 1 | thumb | 01M3073A6E8SR2B7JF97DG0H07 | 01M3073A6F208000GG00000000 |
| 4 | motor_basic | cc | 1 | 0 | 1 | hand | 01M3073EJFREB8YATMZYFR5981 | 01M3073EJG20G0020G00000000 |
| 5 | fingerflex | canary | 1 | 0 | 1 | thumb | 01M3073AZA3B2PSZTSGH07Y31Y | 01M3073AZC208000RG00080000 |

Record 1 is channel 0, so its event identifier and its sample identifier coincide. For records 2 to 5 compare the two: the channel characters differ, the rest is the same.

## 5. Silver, pseudonymised and typed

```mermaid
flowchart LR
  B[Bronze row<br>subject_src, value_raw, sample_idx, lid layer 1] --> K{{keyring.duckdb<br>HMAC-SHA256}}
  K --> S[Silver row<br>subject_pid, value_uv, ts_ms, lid layer 2]
  B -.->|NaN dropped| X((counted in Gold))
```

The keyring maps each source code to a pseudonym once, and only the keyring holds the pair. Silver sees the pseudonym.

<details>
<summary>pipeline/keyring.py, the pseudonym, then sql/silver/010_subject.sql</summary>

```sql
-- pipeline/keyring.py: subject_pid = hmac_sha256(secret, subject_src)[:16], one row per
-- new subject_src in keyring.key_map(subject_src, subject_pid, created_at).

-- silver/subject, spec 3.2. One row per pseudonym present in Bronze.
COPY (
    SELECT k.subject_pid, k.created_at AS first_seen_at
    FROM keyring.key_map k
    JOIN (SELECT DISTINCT subject_src FROM bronze_recording) b USING (subject_src)
    ORDER BY 1
) TO '{{data_dir}}/silver/subject/data_0.parquet' (FORMAT parquet);
```

</details>

| subject_pid | first_seen_at |
|---|---|
| 330a1a33c4ea905e | 2026-09-20 20:11:14.744459 |
| 4870aca0c2bc23d6 | 2026-09-20 20:11:14.744455 |
| 8697935b255ab403 | 2026-09-20 20:11:14.744435 |
| feff3135d21f3fc6 | 2026-09-20 20:11:14.744458 |

One `silver/record` row per record, the lineage dimension. The loader validates that the incoming identifier is layer 1, then sets layer 2. `n_samples_src` counts the source samples, burst included.

<details>
<summary>sql/silver/020_record.sql</summary>

```sql
-- silver/record, spec 12.2. One row per record (file, run, channel), the lineage dimension
-- of Silver. The lid is the Bronze lid with the layer set to 2, validated on the way.
-- n_samples_src counts source samples including NaN, so Gold derives missing_samples from
-- Silver alone.
COPY (
    SELECT
        lid_to_uuid(lid_relayer(lid_from_uuid(r.lid), 1)) AS lid,
        r.experiment,
        k.subject_pid,
        r.run,
        r.channel_idx,
        count(*)::BIGINT AS n_samples_src
    FROM bronze_recording r
    JOIN keyring.key_map k USING (subject_src)
    GROUP BY ALL
    ORDER BY 1
) TO '{{data_dir}}/silver/record/data_0.parquet' (FORMAT parquet);
```

</details>

| n | lid | experiment | subject_pid | run | channel_idx | n_samples_src |
|---|---|---|---|---|---|---|
| 1 | 01M30739CH4080008G00000000 | fingerflex | 8697935b255ab403 | 1 | 0 | 60000 |
| 2 | 01M3073CEJ40G0018G2G000000 | motor_basic | 8697935b255ab403 | 1 | 5 | 60000 |
| 3 | 01M3073A6F408000GG0G000000 | fingerflex | 4870aca0c2bc23d6 | 1 | 1 | 60000 |
| 4 | 01M3073EJG40G0020G1G000000 | motor_basic | 330a1a33c4ea905e | 1 | 3 | 60000 |
| 5 | 01M3073AZC408000RG1G080000 | fingerflex | feff3135d21f3fc6 | 1 | 3 | 60000 |

Decoded, only the layer moved. `lid_parent` returns the Bronze identifier with no lookup.

<details>
<summary>sql/lineage/lid_extras.sql, lid_parent</summary>

```sql
CREATE OR REPLACE MACRO lid_parent(lid) AS
    CASE WHEN lid_layer(lid_from_uuid(lid)) <= 1 THEN error('lid_parent: Bronze has no parent')
    ELSE lid_to_uuid(lid_from_uuid(lid) - (1::UHUGEINT << 76))
    END;
```

</details>

| n | lid | layer | file | channel | radioactive | lid_parent |
|---|---|---|---|---|---|---|
| 1 | 01M30739CH4080008G00000000 | 2 | 1 | 0 | 0 | 01M30739CH2080008G00000000 |
| 2 | 01M3073CEJ40G0018G2G000000 | 2 | 5 | 5 | 0 | 01M3073CEJ20G0018G2G000000 |
| 3 | 01M3073A6F408000GG0G000000 | 2 | 2 | 1 | 0 | 01M3073A6F208000GG0G000000 |
| 4 | 01M3073EJG40G0020G1G000000 | 2 | 8 | 3 | 0 | 01M3073EJG20G0020G1G000000 |
| 5 | 01M3073AZC408000RG1G080000 | 2 | 3 | 3 | 1 | 01M3073AZC208000RG1G080000 |

The same two samples in `silver/recording`: microvolts (raw times 0.1), milliseconds, pseudonym, the record's identifier and the source sample index. The three burst samples are absent, not NULL.

<details>
<summary>sql/silver/030_recording.sql</summary>

```sql
-- silver/recording, spec 3.2 and 12.2. Microvolts, milliseconds, pseudonyms, NaN dropped.
-- Executed once per (experiment, subject_pid) partition by pipeline/run.py: DuckDB 1.5's
-- partitioned COPY does not keep the ORDER BY across its buffer flushes, a plain COPY does.
-- Sorted by lid, sample_idx inside the file. Row groups of at most 200,000 rows: DuckDB
-- rounds the size up to a multiple of 2048, so 198,656 is the largest value under the limit.
COPY (
    SELECT
        r.experiment,
        k.subject_pid,
        r.run,
        r.channel_idx,
        (r.sample_idx::BIGINT * 1000 / a.sample_rate_hz)::INTEGER AS ts_ms,
        (r.value_raw * u.uv_per_unit)::FLOAT AS value_uv,
        s.lid,
        r.sample_idx
    FROM bronze_recording r
    JOIN keyring.key_map k USING (subject_src)
    JOIN bronze_ingest_audit a USING (ingest_id)
    JOIN (SELECT lid, lid_parent(lid) AS bronze_lid FROM silver_record) s ON s.bronze_lid = r.lid
    JOIN (VALUES {{unit_scale_values}}) u(experiment, uv_per_unit) ON u.experiment = r.experiment
    WHERE r.experiment = '{{experiment}}' AND k.subject_pid = '{{subject_pid}}'
      AND NOT isnan(r.value_raw)
    ORDER BY s.lid, r.sample_idx
) TO '{{data_dir}}/silver/recording/experiment={{experiment}}/subject_pid={{subject_pid}}/data_0.parquet'
(FORMAT parquet, ROW_GROUP_SIZE 198656);
```

</details>

| n | asked | experiment | subject_pid | run | channel_idx | ts_ms | value_uv | lid | sample_idx |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 0 | fingerflex | 8697935b255ab403 | 1 | 0 | 0 | 6.194 | 01M30739CH4080008G00000000 | 0 |
| 1 | 30250 | absent | | | | | | | |
| 2 | 0 | motor_basic | 8697935b255ab403 | 1 | 5 | 0 | 19.123 | 01M3073CEJ40G0018G2G000000 | 0 |
| 2 | 30250 | motor_basic | 8697935b255ab403 | 1 | 5 | 30250 | 3.063 | 01M3073CEJ40G0018G2G000000 | 30250 |
| 3 | 0 | fingerflex | 4870aca0c2bc23d6 | 1 | 1 | 0 | 12.916 | 01M3073A6F408000GG0G000000 | 0 |
| 3 | 30250 | absent | | | | | | | |
| 4 | 0 | motor_basic | 330a1a33c4ea905e | 1 | 3 | 0 | -9.115 | 01M3073EJG40G0020G1G000000 | 0 |
| 4 | 30250 | motor_basic | 330a1a33c4ea905e | 1 | 3 | 30250 | -3.251 | 01M3073EJG40G0020G1G000000 | 30250 |
| 5 | 0 | fingerflex | feff3135d21f3fc6 | 1 | 3 | 0 | 12.335 | 01M3073AZC408000RG1G080000 | 0 |
| 5 | 30250 | absent | | | | | | | |

Electrodes and events mirror Bronze with the pseudonym, milliseconds instead of sample index, and no `ingest_id`; the file is inside the identifier now.

<details>
<summary>sql/silver/040_electrode.sql and 050_event.sql</summary>

```sql
-- silver/electrode, spec 3.2: Bronze with subject_src replaced by subject_pid, ingest_id removed.
COPY (
    SELECT
        b.experiment,
        k.subject_pid,
        b.channel_idx,
        b.x_mm,
        b.y_mm,
        b.z_mm,
        b.brain_area,
        lid_to_uuid(lid_relayer(lid_from_uuid(b.lid), 1)) AS lid
    FROM bronze_electrode b
    JOIN keyring.key_map k USING (subject_src)
    ORDER BY lid
) TO '{{data_dir}}/silver/electrode'
(FORMAT parquet, PARTITION_BY (experiment, subject_pid), WRITE_PARTITION_COLUMNS, OVERWRITE);

-- silver/event, spec 3.2: Bronze with subject_pid for subject_src, ts_ms for sample_idx,
-- ingest_id removed.
COPY (
    SELECT
        b.experiment,
        k.subject_pid,
        b.run,
        (b.sample_idx::BIGINT * 1000 / a.sample_rate_hz)::INTEGER AS ts_ms,
        b.event_code,
        b.event_label,
        lid_to_uuid(lid_relayer(lid_from_uuid(b.lid), 1)) AS lid
    FROM bronze_event b
    JOIN keyring.key_map k USING (subject_src)
    JOIN bronze_ingest_audit a USING (ingest_id)
    ORDER BY lid, ts_ms
) TO '{{data_dir}}/silver/event'
(FORMAT parquet, PARTITION_BY (experiment, subject_pid), WRITE_PARTITION_COLUMNS, OVERWRITE);
```

</details>

| n | experiment | subject_pid | channel_idx | x_mm | y_mm | z_mm | brain_area | lid |
|---|---|---|---|---|---|---|---|---|
| 1 | fingerflex | 8697935b255ab403 | 0 | 0.000 | 0.000 | 40.000 | precentral | 01M30739CH4080008G00000000 |
| 2 | motor_basic | 8697935b255ab403 | 5 | 50.000 | 0.000 | 40.000 | postcentral | 01M3073CEJ40G0018G2G000000 |
| 3 | fingerflex | 4870aca0c2bc23d6 | 1 | 10.000 | 0.000 | 40.000 | postcentral | 01M3073A6F408000GG0G000000 |
| 4 | motor_basic | 330a1a33c4ea905e | 3 | 30.000 | 0.000 | 40.000 | temporal | 01M3073EJG40G0020G1G000000 |
| 5 | fingerflex | feff3135d21f3fc6 | 3 | 30.000 | 0.000 | 40.000 | temporal | 01M3073AZC408000RG1G080000 |

| n | experiment | subject_pid | run | ts_ms | event_code | event_label | lid |
|---|---|---|---|---|---|---|---|
| 1 | fingerflex | 8697935b255ab403 | 1 | 0 | 1 | thumb | 01M30739CH4080008G00000000 |
| 2 | motor_basic | 8697935b255ab403 | 1 | 0 | 1 | hand | 01M3073CEJ40G0018G00000000 |
| 3 | fingerflex | 4870aca0c2bc23d6 | 1 | 0 | 1 | thumb | 01M3073A6F408000GG00000000 |
| 4 | motor_basic | 330a1a33c4ea905e | 1 | 0 | 1 | hand | 01M3073EJG40G0020G00000000 |
| 5 | fingerflex | feff3135d21f3fc6 | 1 | 0 | 1 | thumb | 01M3073AZC408000RG00080000 |

## 6. Gold, every value a query result

The marts read Silver and refuse any record whose identifier carries the canary bit. Record 5 stops here. The others get layer 3.

`gold/channel_quality`, one row per record. `missing_samples` is `n_samples_src` minus what Silver holds: the 500 sample burst shows up as 500. `line_noise_ratio` is the share of power at 50 and 60 Hz in the first 10 s; record 1 carries the injected tone, so it stands out at 0.030 against 0.002.

<details>
<summary>sql/gold/010_channel_quality.sql, and the line noise excerpt from pipeline/line_noise.py</summary>

```sql
-- gold/channel_quality, spec 3.3. One row per record. Silver carries no amplifier range, so
-- the rails for clipped_pct are the observed extremes of value_uv within the run.
-- missing_samples is the record's source sample count minus the samples present in Silver.
-- Canary records (radioactive bit, spec 12.5) never enter a Gold mart.
COPY (
    WITH rails AS (
        SELECT experiment, subject_pid, run, min(value_uv) AS lo, max(value_uv) AS hi
        FROM silver_recording
        GROUP BY ALL
    ),
    q AS (
        SELECT
            r.experiment,
            r.subject_pid,
            r.run,
            r.channel_idx,
            r.lid,
            count(*)::BIGINT AS n_samples,
            sqrt(avg(r.value_uv * r.value_uv))::FLOAT AS rms_uv,
            (100.0 * count(*) FILTER (WHERE r.value_uv = rails.lo OR r.value_uv = rails.hi)
                / count(*))::FLOAT AS clipped_pct
        FROM silver_recording r
        JOIN rails USING (experiment, subject_pid, run)
        WHERE r.lid IN (SELECT lid FROM silver_record WHERE lid_radioactive(lid_from_uuid(lid)) = 0)
        GROUP BY ALL
    )
    SELECT
        q.experiment,
        q.subject_pid,
        q.run,
        q.channel_idx,
        q.n_samples,
        (s.n_samples_src - q.n_samples)::BIGINT AS missing_samples,
        q.rms_uv,
        q.clipped_pct,
        n.line_noise_ratio::FLOAT AS line_noise_ratio,
        lid_to_uuid(lid_relayer(lid_from_uuid(q.lid), 2)) AS lid
    FROM q
    JOIN silver_record s USING (lid)
    LEFT JOIN line_noise n USING (lid)
    ORDER BY 1, 2, 3, 4
) TO '{{data_dir}}/gold/channel_quality/data_0.parquet' (FORMAT parquet);

-- pipeline/line_noise.py fills the line_noise temp table: this query takes the first
-- 10 s of each record, Python runs rfft on it and keeps the 49 to 51 and 59 to 61 Hz share.
WITH rate AS (
    SELECT s.lid, a.sample_rate_hz
    FROM silver_record s
    JOIN lineage_dim d ON d.ingest_ord = lid_file(lid_from_uuid(s.lid))
    JOIN bronze_ingest_audit a USING (ingest_id)
)
SELECT r.lid, rate.sample_rate_hz, list(r.value_uv ORDER BY r.sample_idx) AS excerpt
FROM silver_recording r
JOIN rate USING (lid)
WHERE r.sample_idx < 10 * rate.sample_rate_hz
GROUP BY 1, 2
```

</details>

| n | experiment | subject_pid | run | channel_idx | n_samples | missing_samples | rms_uv | clipped_pct | line_noise_ratio | lid |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | fingerflex | 8697935b255ab403 | 1 | 0 | 59500 | 500 | 41.246 | 0.000 | 0.030 | 01M30739CH6080008G00000000 |
| 2 | motor_basic | 8697935b255ab403 | 1 | 5 | 60000 | 0 | 40.518 | 0.000 | 0.002 | 01M3073CEJ60G0018G2G000000 |
| 3 | fingerflex | 4870aca0c2bc23d6 | 1 | 1 | 59500 | 500 | 40.578 | 0.000 | 0.002 | 01M3073A6F608000GG0G000000 |
| 4 | motor_basic | 330a1a33c4ea905e | 1 | 3 | 60000 | 0 | 40.567 | 0.000 | 0.002 | 01M3073EJG60G0020G1G000000 |
| 5 | absent, canary | | | | | | | | | |

`gold/feature_window`, one row per record and second. The window that holds sample 30250: for the burst records the window starts at sample 30500, because samples 30000 to 30499 are gone, and `sample_lo` says so.

<details>
<summary>sql/gold/030_feature_window.sql</summary>

```sql
-- gold/feature_window, spec 3.3 and 12.2. One row per record and 1,000 ms window, with the
-- window's source sample range inside the record. Canary records (spec 12.5) are left out.
COPY (
    SELECT
        experiment,
        subject_pid,
        run,
        channel_idx,
        (ts_ms // 1000 * 1000)::INTEGER AS window_start_ms,
        avg(value_uv)::FLOAT AS mean_uv,
        stddev_pop(value_uv)::FLOAT AS std_uv,
        (max(value_uv) - min(value_uv))::FLOAT AS p2p_uv,
        lid_to_uuid(lid_relayer(lid_from_uuid(lid), 2)) AS lid,
        min(sample_idx)::INTEGER AS sample_lo,
        max(sample_idx)::INTEGER AS sample_hi
    FROM silver_recording
    WHERE lid IN (SELECT lid FROM silver_record WHERE lid_radioactive(lid_from_uuid(lid)) = 0)
    GROUP BY experiment, subject_pid, run, channel_idx, window_start_ms, lid
    ORDER BY lid, window_start_ms
) TO '{{data_dir}}/gold/feature_window/data_0.parquet' (FORMAT parquet);
```

</details>

| n | experiment | subject_pid | run | channel_idx | window_start_ms | mean_uv | std_uv | p2p_uv | lid | sample_lo | sample_hi |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | fingerflex | 8697935b255ab403 | 1 | 0 | 30000 | 0.522 | 41.131 | 203.212 | 01M30739CH6080008G00000000 | 30500 | 30999 |
| 2 | motor_basic | 8697935b255ab403 | 1 | 5 | 30000 | -0.047 | 40.280 | 197.758 | 01M3073CEJ60G0018G2G000000 | 30000 | 30999 |
| 3 | fingerflex | 4870aca0c2bc23d6 | 1 | 1 | 30000 | 0.383 | 41.294 | 193.428 | 01M3073A6F608000GG0G000000 | 30500 | 30999 |
| 4 | motor_basic | 330a1a33c4ea905e | 1 | 3 | 30000 | -0.363 | 40.012 | 205.377 | 01M3073EJG60G0020G1G000000 | 30000 | 30999 |
| 5 | absent, canary | | | | | | | | | | |

`gold/experiment_summary`, one row per experiment and subject. It spans records, so it carries no identifier; the canary subject is left out by its pseudonym.

<details>
<summary>sql/gold/020_experiment_summary.sql</summary>

```sql
-- gold/experiment_summary, spec 3.3. One row per experiment and subject. duration_s is the
-- sum over runs of the last present sample time plus one millisecond. A subject whose
-- records carry the canary bit (spec 12.5) is left out.
COPY (
    WITH canary AS (
        SELECT DISTINCT subject_pid FROM silver_record WHERE lid_radioactive(lid_from_uuid(lid)) = 1
    ),
    runs AS (
        SELECT experiment, subject_pid, run,
               count(DISTINCT channel_idx) AS n_channels,
               max(ts_ms) + 1 AS duration_ms
        FROM silver_recording
        WHERE subject_pid NOT IN (SELECT subject_pid FROM canary)
        GROUP BY ALL
    ),
    events AS (
        SELECT experiment, subject_pid, count(*) AS n_events
        FROM silver_event
        GROUP BY ALL
    )
    SELECT
        r.experiment,
        r.subject_pid,
        count(*)::SMALLINT AS n_runs,
        max(r.n_channels)::SMALLINT AS n_channels,
        (sum(r.duration_ms) / 1000.0)::FLOAT AS duration_s,
        coalesce(any_value(e.n_events), 0)::INTEGER AS n_events
    FROM runs r
    LEFT JOIN events e USING (experiment, subject_pid)
    GROUP BY 1, 2
    ORDER BY 1, 2
) TO '{{data_dir}}/gold/experiment_summary/data_0.parquet' (FORMAT parquet);
```

</details>

| n | experiment | subject_pid | n_runs | n_channels | duration_s | n_events |
|---|---|---|---|---|---|---|
| 1 | fingerflex | 8697935b255ab403 | 1 | 64 | 60.000 | 30 |
| 2 | motor_basic | 8697935b255ab403 | 1 | 64 | 60.000 | 30 |
| 3 | fingerflex | 4870aca0c2bc23d6 | 1 | 64 | 60.000 | 30 |
| 4 | motor_basic | 330a1a33c4ea905e | 1 | 64 | 60.000 | 30 |
| 5 | absent, canary | | | | | |

## 7. Back to the file, forward to the records

`lid_trace` on the Gold identifier of record 1 decodes the bits and joins `lineage_dim` once. The number 41.246 above came from this file, this digest, this run and channel.

<details>
<summary>sql/lineage/lid_extras.sql, lid_trace</summary>

```sql
CREATE OR REPLACE MACRO lid_trace(lid) AS TABLE
    SELECT d.source_path, d.source_url, d.sha256, f.ts_ms, f.layer, e.experiment,
           f.run, f.channel, f.segment
    FROM (SELECT lid_decode(lid_from_uuid(lid)) AS f)
    JOIN lineage_dim d ON d.ingest_ord = f.file
    JOIN lineage_experiment e ON e.code = f.experiment;
```

</details>

| source_path | source_url | sha256 | ts_ms | layer | experiment | run | channel | segment |
|---|---|---|---|---|---|---|---|---|
| fingerflex/aa.mat | synthetic://fingerflex/aa.mat | 65c157a67f68 | 1789935068561 | 3 | fingerflex | 1 | 0 | 0 |

`lid_children(1)` is a range scan between two identifiers; it returns every Silver record of file 1.

<details>
<summary>sql/lineage/lid_extras.sql, lid_prefix_lo, lid_prefix_hi, lid_children</summary>

```sql
CREATE OR REPLACE MACRO lid_prefix_lo(ing) AS (
    SELECT lid_to_uuid(lid_encode(d.ts_ms, 2, e.code, ing, 0, 0, 0, 0))
    FROM lineage_dim d JOIN lineage_experiment e USING (experiment)
    WHERE d.ingest_ord = ing);

CREATE OR REPLACE MACRO lid_prefix_hi(ing) AS (
    SELECT lid_to_uuid(lid_encode(d.ts_ms, 2, e.code, ing, 15, 1023, 1023, 1) | ((1::UHUGEINT << 23) - 1))
    FROM lineage_dim d JOIN lineage_experiment e USING (experiment)
    WHERE d.ingest_ord = ing);

CREATE OR REPLACE MACRO lid_children(ing) AS TABLE
    SELECT * FROM silver_record
    WHERE lid BETWEEN lid_prefix_lo(ing) AND lid_prefix_hi(ing);
```

</details>

| records | first | last |
|---|---|---|
| 64 | 01M30739CH4080008G00000000 | 01M30739CH4080008GZG000000 |

## 8. Evidence, manifest, publication

Checks run over the datasets, not over single records, so their `lid` is NULL. Three rows of the last run: the identifier rule for Silver, the canary rule for Gold, the file layout rule.

<details>
<summary>sql/checks/no_direct_identifier.sql, sql.sql, partition_layout.sql, the three templates behind these rows</summary>

```sql
-- no_direct_identifier: forbidden columns present in the dataset. Expected 0.
SELECT count(*) AS observed
FROM information_schema.columns
WHERE table_name = '{{view}}' AND column_name IN ({{forbidden_columns}})

-- sql: rows returned by the requirement's own query. Expected 0.
SELECT count(*) AS observed FROM ({{query}})

-- partition_layout: files with a row group over the maximum or fewer row groups than the
-- minimum. Expected 0.
SELECT count(*) AS observed
FROM (
    SELECT file_name,
           count(DISTINCT row_group_id) AS row_groups,
           max(row_group_num_rows) AS max_rows
    FROM parquet_metadata('{{data_dir}}/{{dataset}}/**/*.parquet')
    GROUP BY 1
)
WHERE row_groups < {{min_row_groups}} OR max_rows > {{max_rows_per_row_group}}
```

</details>

| run_id | check_id | requirement_id | framework | dataset | dataset_version | check_kind | result | observed | expected | ran_at | engine_version | git_commit | lid |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 01M3075NM9ZSF1P822HXTA9W34 | GDPR-Art9/no_direct_identifier/silver/recording/['subject_src'] | GDPR-Art9 | GDPR-Art9 | silver/recording | 04eacd2c0a53 | no_direct_identifier | pass | 0 | 0 | 2026-09-20 20:12:26.633977 | 1.5.5 | 868ab53 | NULL |
| 01M3075NM9ZSF1P822HXTA9W34 | GDPR-Art9/sql/gold/channel_quality/SELECT 1 FROM gold_channel_quality WHERE lid_radioactive(lid_from_uuid(lid)) = 1 | GDPR-Art9 | GDPR-Art9 | gold/channel_quality | 2612b79bcb85 | sql | pass | 0 | 0 | 2026-09-20 20:12:26.633977 | 1.5.5 | 868ab53 | NULL |
| 01M3075NM9ZSF1P822HXTA9W34 | ISO13485-4.2.5/partition_layout/silver/recording/200000/2 | ISO13485-4.2.5 | ISO13485 | silver/recording | 04eacd2c0a53 | partition_layout | pass | 0 | 0 | 2026-09-20 20:12:26.633977 | 1.5.5 | 868ab53 | NULL |

`gold/dataset_manifest` names the build: the same `dataset_version` the evidence carries, the identifier range of the records, the number of source files behind them.

<details>
<summary>pipeline/manifest.py, the two queries per dataset, and pipeline/db.py dataset_version</summary>

```sql
-- per dataset view with a lid column
SELECT count(*), min(lid), max(lid) FROM {view};

SELECT DISTINCT d.sha256
FROM (SELECT DISTINCT lid FROM {view} WHERE lid IS NOT NULL) v
JOIN lineage_dim d ON d.ingest_ord = lid_file(lid_from_uuid(v.lid))
ORDER BY 1;

-- dataset_version, pipeline/db.py: sha256 of the sorted sha256 of the dataset's Parquet files
-- digests = sorted(sha256(file) for file in dataset/**/*.parquet)
-- dataset_version = sha256('\n'.join(digests))
```

</details>

| dataset_version | dataset | layer | lid_lo | lid_hi | n_records | files | produced_at | git_commit |
|---|---|---|---|---|---|---|---|---|
| 2612b79bcb85 | gold/channel_quality | 3 | 01M30739CH6080008G00000000 | 01M3073EJG60G0020GZG000000 | 384 | 6 | 2026-09-20 20:12:24.243828 | 868ab53 |
| 04eacd2c0a53 | silver/recording | 2 | 01M30739CH4080008G00000000 | 01M3073EJG40G0020GZG000000 | 30718000 | 8 | 2026-09-20 20:12:24.243828 | 868ab53 |

Silver has 8 files behind it, Gold 6: the two canary files never reach a mart. `docs/data/manifest.json` records the published copies with their own digests.

<details>
<summary>pipeline/publish.py, the refusal query per published file</summary>

```sql
SELECT count(*) FROM read_parquet('{path}')
WHERE lid IS NOT NULL AND lid_radioactive(lid_from_uuid(lid)) = 1
-- any row above zero refuses the whole publish
```

</details>

| path | bytes | sha256 |
|---|---|---|
| gold/channel_quality/data_0.parquet | 7360 | 9605d0fa03d0 |
| gold/dataset_manifest/data_0.parquet | 4309 | 1b3c443a0443 |

## 9. What the five showed

| n | Lesson |
|---|---|
| 1 | A gap in the source is kept in Bronze, dropped in Silver, counted in Gold, and visible in the window range. The injected tone is measurable. |
| 2 | Same subject as 1, other experiment: a different file, a different identifier, the same pseudonym. |
| 3 | The burst lands on a different channel per subject; the identifier's channel field and `sample_lo` tell which. |
| 4 | A clean record moves through with nothing lost and every value a query result. |
| 5 | The canary bit set at conversion survives Silver and stops every Gold mart, without any column to lose. |
