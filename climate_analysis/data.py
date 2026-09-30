"""Download and parse NASA GISTEMP v4 surface temperature anomaly tables.

GISTEMP anomalies are in degrees Celsius relative to the 1951-1980 mean.
Source: https://data.giss.nasa.gov/gistemp/
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://data.giss.nasa.gov/gistemp/tabledata_v4/{code}.Ts+dSST.csv"

DATASETS = {
    "global": ("GLB", "Global"),
    "north": ("NH", "Northern Hemisphere"),
    "south": ("SH", "Southern Hemisphere"),
}

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SEASONS = ["DJF", "MAM", "JJA", "SON"]
ANNUAL = "J-D"
BASELINE = "1951-1980"


def download(dataset: str, data_dir: Path | str = "data", refresh: bool = False) -> Path:
    """Download a GISTEMP table to ``data_dir`` and return its path.

    The file is cached; pass ``refresh=True`` to fetch the latest release.
    """
    code, _ = DATASETS[dataset]
    path = Path(data_dir) / f"gistemp_{code}.csv"
    if path.exists() and not refresh:
        return path

    response = requests.get(BASE_URL.format(code=code), timeout=60)
    response.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(response.text, encoding="utf-8")
    return path


def parse_gistemp(text: str) -> pd.DataFrame:
    """Parse a GISTEMP CSV table into a DataFrame indexed by year.

    The first line of the file is a title, and missing values are ``***``.
    """
    df = pd.read_csv(io.StringIO(text), skiprows=1, na_values="***")
    df = df.set_index("Year")
    df.index = df.index.astype(int)
    return df.apply(pd.to_numeric, errors="coerce")


def load(dataset: str = "global", data_dir: Path | str = "data",
         refresh: bool = False) -> pd.DataFrame:
    """Download (if needed) and parse a GISTEMP table."""
    path = download(dataset, data_dir, refresh)
    return parse_gistemp(path.read_text(encoding="utf-8"))


def annual_series(df: pd.DataFrame) -> pd.Series:
    """Return annual mean anomalies, dropping incomplete years."""
    return df[ANNUAL].dropna().rename("anomaly")
