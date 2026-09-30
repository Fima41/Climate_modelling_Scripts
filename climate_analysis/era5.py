"""Download daily ERA5 reanalysis for a district, averaged over its grid cells.

ERA5 is the fifth-generation ECMWF global atmospheric reanalysis, produced by
the Copernicus Climate Change Service. It is gridded at 0.25° (about 28 km), so
a district value is the mean of the grid cells covering the district. Data are
fetched from the free Open-Meteo historical weather API.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import requests

API_URL = "https://archive-api.open-meteo.com/v1/archive"
GRID = 0.25
VARIABLES = {
    "temperature_2m_max": "tmax",
    "temperature_2m_min": "tmin",
    "precipitation_sum": "prcp",
}


@dataclass(frozen=True)
class District:
    name: str
    south: float
    north: float
    west: float
    east: float
    timezone: str

    def cells(self) -> list[tuple[float, float]]:
        """Centres of the ERA5 grid cells inside the district's bounding box."""
        lats = np.arange(math.ceil(self.south / GRID), math.floor(self.north / GRID) + 1) * GRID
        lons = np.arange(math.ceil(self.west / GRID), math.floor(self.east / GRID) + 1) * GRID
        return [(float(lat), float(lon)) for lat in lats for lon in lons]


DISTRICTS = {
    "lusaka": District("Lusaka District, Zambia", south=-15.55, north=-15.20,
                       west=28.15, east=28.55, timezone="Africa/Lusaka"),
}


def download(district: str, start: str, end: str, data_dir: Path | str = "data",
             refresh: bool = False) -> Path:
    """Fetch daily district-mean Tmax, Tmin and precipitation, cached as CSV."""
    path = Path(data_dir) / f"era5_{district}_{start}_{end}.csv"
    if path.exists() and not refresh:
        return path

    info = DISTRICTS[district]
    cells = info.cells()
    params = {
        "latitude": ",".join(str(lat) for lat, _ in cells),
        "longitude": ",".join(str(lon) for _, lon in cells),
        "start_date": start,
        "end_date": end,
        "daily": ",".join(VARIABLES),
        "models": "era5",
        "timezone": info.timezone,
    }
    response = requests.get(API_URL, params=params, timeout=300)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):  # a single cell returns an object, not a list
        payload = [payload]

    frames = [pd.DataFrame(cell["daily"]).set_index("time") for cell in payload]
    district_mean = pd.concat(frames).groupby(level=0).mean().rename(columns=VARIABLES)
    district_mean.index.name = "date"

    path.parent.mkdir(parents=True, exist_ok=True)
    district_mean.round(2).to_csv(path)
    return path


def load(district: str = "lusaka", start: str = "1950-01-01", end: str = "2026-06-30",
         data_dir: Path | str = "data", refresh: bool = False) -> pd.DataFrame:
    """Daily district-mean data indexed by date, with columns tmax, tmin, prcp."""
    path = download(district, start, end, data_dir, refresh)
    return pd.read_csv(path, index_col="date", parse_dates=True)
