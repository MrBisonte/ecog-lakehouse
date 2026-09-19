# Site rules

Source: flightdeck, the author's data architecture portfolio site (https://mrbisonte.github.io/flightdeck/), a data pipeline and analytics site with DuckDB-WASM querying published Parquet in the browser.

| Rule | Reason |
|---|---|
| Every number on the page is the result of a query, none typed by hand, and the footer says so | Trust; a day was once spent removing hardcoded values |
| No third-party request at view time, other than the pinned DuckDB-WASM CDN | Privacy, reproducibility, no tracking |
| No font files committed; system font stacks only | Repository size, licensing |
| DuckDB-WASM reads the published Parquet directly over HTTP range requests; no server | The page is the proof that the data layer works |
| Gold feeds the page; the page never computes what Gold should have | Layer discipline |
| No commas in chart legends and table labels; a middle dot separates list items | House style |
| Front end effort is minimal by design; the data is the product | Priorities |

Applied here: `docs/index.html`, spec section 8, plus click-to-trace on every number (spec 12.4).
