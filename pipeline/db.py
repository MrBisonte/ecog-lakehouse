"""Paths shared by every pipeline script."""

import os
from pathlib import Path


def data_dir() -> Path:
    """Root for raw, bronze, silver, gold and keyring.duckdb. Never inside the repository."""
    return Path(os.environ.get("DATA_DIR", Path.home() / "data" / "ibrain"))
