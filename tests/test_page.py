"""String checks on docs/index.html. They prove what the page's code says, not what a browser does."""

from pipeline import db

PAGE = (db.REPO / "docs" / "index.html").read_text(encoding="utf-8")


def test_page_queries_the_bytes_it_verified():
    """Each Gold file is fetched once, by a URL that carries its digest, and registered as a buffer."""
    assert "registerFileURL" not in PAGE
    assert "db.registerFileBuffer(f.path, bytes)" in PAGE
    assert "fetch(`data/${f.path}?v=${f.sha256}`)" in PAGE
    assert PAGE.count("fetch(") == 5, "manifest, summary.json, Gold files, lid.sql, checks.json, nothing else"


def test_page_paints_the_summary_before_the_engine_downloads():
    """summary.json is fetched, verified and painted before the engine module is imported, and
    the repository link is static HTML, so both are there whatever the CDN does."""
    assert "import * as duckdb" not in PAGE
    assert PAGE.index("fetch(`data/summary.json?v=${summaryFile.sha256}`)") < PAGE.index("await import(ENGINE)")
    assert 'href="https://github.com/MrBisonte/ecog-lakehouse"' in PAGE


def test_page_counts_four_steps():
    """The progress line names the four steps of spec section 8, not the old five."""
    assert "of 5" not in PAGE
    for n in range(1, 5):
        assert f"Step {n} of 4" in PAGE
