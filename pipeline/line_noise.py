"""line_noise_ratio per record, spec 3.3: power in 49 to 51 Hz and 59 to 61 Hz over total
power, on the first 10 s of the record. DuckDB has no FFT, so this one Gold number is computed
in Python from a query result and handed back to SQL as the table `line_noise`.
"""

import numpy as np
from scipy.fft import rfft, rfftfreq

EXCERPT_S = 10

EXCERPTS = """
WITH rate AS (
    SELECT s.lid, a.sample_rate_hz
    FROM silver_record s
    JOIN lineage_dim d ON d.ingest_ord = lid_file(lid_from_uuid(s.lid))
    JOIN bronze_ingest_audit a USING (ingest_id)
)
SELECT r.lid, rate.sample_rate_hz, list(r.value_uv ORDER BY r.sample_idx) AS excerpt
FROM silver_recording r
JOIN rate USING (lid)
WHERE r.sample_idx < {excerpt_s} * rate.sample_rate_hz
GROUP BY 1, 2
"""


def ratio(values, sample_rate_hz: int) -> float | None:
    """NULL when fewer than 10 s of samples are present, else the band power share."""
    n = EXCERPT_S * sample_rate_hz
    if len(values) < n:
        return None
    x = np.asarray(values[:n], dtype=np.float64)
    power = np.abs(rfft(x - x.mean())) ** 2
    freq = rfftfreq(n, 1.0 / sample_rate_hz)
    band = ((freq >= 49) & (freq <= 51)) | ((freq >= 59) & (freq <= 61))
    total = power.sum()
    return float(power[band].sum() / total) if total > 0 else None


def register(con):
    """Create the temp table line_noise(lid, line_noise_ratio), one row per Silver record."""
    con.execute("CREATE OR REPLACE TEMP TABLE line_noise (lid UUID, line_noise_ratio FLOAT)")
    rows = con.execute(EXCERPTS.format(excerpt_s=EXCERPT_S)).fetchall()
    con.executemany(
        "INSERT INTO line_noise VALUES (?, ?)",
        [(str(lid), ratio(excerpt, rate)) for lid, rate, excerpt in rows] or [(None, None)],
    )
    return len(rows)
