"""Read ERA5 monthly means from a Copernicus CDS GRIB download and build seasonal anomalies.

Expected download: "ERA5 monthly averaged data on single levels", product type
"monthly averaged reanalysis", variables 2m temperature and total precipitation,
on the 0.25° grid. In that product total precipitation is the mean daily
accumulation (metres per day) and 2m temperature is in kelvin.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

SEASON_MONTHS = (10, 11, 12, 1, 2, 3)    # October-March rainy season
BASE_SEASONS = (1991, 2020)              # seasons 1991/92 to 2020/21

# El Niño seasons and their peak Oceanic Niño Index (NOAA CPC, ERSSTv5).
EL_NINO = {1982: 2.2, 1991: 1.7, 1997: 2.4, 2015: 2.6, 2023: 2.0}


@dataclass(frozen=True)
class Monthly:
    """Monthly fields on a regular latitude/longitude grid."""

    time: pd.DatetimeIndex        # first day of each month
    lat: np.ndarray               # descending, cell centres
    lon: np.ndarray               # ascending, cell centres
    t2m: np.ndarray               # (time, lat, lon) °C
    precip: np.ndarray            # (time, lat, lon) mm per day

    @property
    def resolution(self) -> float:
        return float(abs(self.lon[1] - self.lon[0]))


def load_grib(path: Path | str) -> Monthly:
    import cfgrib

    fields = {}
    for ds in cfgrib.open_datasets(str(path), backend_kwargs={"indexpath": ""}):
        for name in ds.data_vars:
            time = pd.to_datetime(ds.valid_time.values).to_period("M").to_timestamp()
            fields[name] = (time, ds.latitude.values, ds.longitude.values, ds[name].values)
    t_time, lat, lon, t2m = fields["t2m"]
    p_time, _, _, tp = fields["tp"]
    if not t_time.equals(p_time):
        raise ValueError("temperature and precipitation cover different months")
    order = np.argsort(t_time.values)
    return Monthly(pd.DatetimeIndex(t_time[order]), lat, lon,
                   (t2m[order] - 273.15).astype(np.float32), (tp[order] * 1000.0).astype(np.float32))


def season_of(time: pd.DatetimeIndex) -> np.ndarray:
    """Season start year: October 1997 to March 1998 is season 1997."""
    return np.where(time.month >= 10, time.year, time.year - 1)


@dataclass(frozen=True)
class Seasons:
    years: np.ndarray             # season start years with all six months present
    rain: np.ndarray              # (season, lat, lon) season total, mm
    temp: np.ndarray              # (season, lat, lon) day-weighted mean, °C

    def index(self, year: int) -> int:
        return int(np.flatnonzero(self.years == year)[0])


def seasonal(data: Monthly, months=SEASON_MONTHS) -> Seasons:
    in_season = np.isin(data.time.month, months)
    season = season_of(data.time)
    days = data.time.days_in_month.values.astype(np.float32)
    years, rains, temps = [], [], []
    for year in np.unique(season[in_season]):
        pick = in_season & (season == year)
        if pick.sum() != len(months):
            continue
        d = days[pick][:, None, None]
        years.append(year)
        rains.append((data.precip[pick] * d).sum(axis=0))
        temps.append((data.t2m[pick] * d).sum(axis=0) / d.sum())
    return Seasons(np.array(years), np.array(rains), np.array(temps))


def climatology(seasons: Seasons, base=BASE_SEASONS) -> tuple[np.ndarray, np.ndarray]:
    pick = (seasons.years >= base[0]) & (seasons.years <= base[1])
    expected = base[1] - base[0] + 1
    if pick.sum() != expected:
        raise ValueError(f"baseline needs {expected} complete seasons, found {pick.sum()}")
    return seasons.rain[pick].mean(axis=0), seasons.temp[pick].mean(axis=0)


def monthly_anomalies(time: pd.DatetimeIndex, rain: np.ndarray, temp: np.ndarray, base=BASE_SEASONS):
    """Rain (mm, from monthly totals) and temperature (°C) anomalies of monthly series,
    against the calendar-month means of the baseline seasons."""
    season = season_of(time)
    in_base = (season >= base[0]) & (season <= base[1])
    rain_anom = np.full(len(time), np.nan)
    temp_anom = np.full(len(time), np.nan)
    for month in range(1, 13):
        pick = time.month == month
        rain_anom[pick] = rain[pick] - rain[pick & in_base].mean()
        temp_anom[pick] = temp[pick] - temp[pick & in_base].mean()
    return rain_anom, temp_anom


def cell_weights(data: Monthly, country, boundary: dict, supersample: int = 10) -> np.ndarray:
    """Share of each grid cell inside the country, times cos(latitude) for cell area."""
    from rasterio.features import rasterize
    from rasterio.transform import from_origin

    res = data.resolution / supersample
    transform = from_origin(data.lon[0] - data.resolution / 2, data.lat[0] + data.resolution / 2, res, res)
    shape = (len(data.lat) * supersample, len(data.lon) * supersample)
    fine = rasterize([(boundary, 1)], out_shape=shape, transform=transform, fill=0, dtype="uint8")
    share = fine.reshape(len(data.lat), supersample, len(data.lon), supersample).mean(axis=(1, 3))
    return share * np.cos(np.radians(data.lat))[:, None]


def area_mean(field: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Weighted mean over the last two (lat, lon) axes, ignoring NaN."""
    w = np.where(np.isfinite(field), weights, 0.0)
    return np.nansum(field * w, axis=(-2, -1)) / w.sum(axis=(-2, -1))


def to_grid(field: np.ndarray, data: Monthly, country, grid) -> np.ndarray:
    """Bilinear-resample a lat/lon field onto the terrain's equal-area grid."""
    from rasterio.transform import from_origin
    from rasterio.warp import Resampling, reproject

    src = np.ascontiguousarray(field, dtype=np.float32)
    out = np.full((grid.height, grid.width), np.nan, dtype=np.float32)
    transform = from_origin(data.lon[0] - data.resolution / 2, data.lat[0] + data.resolution / 2,
                            data.resolution, data.resolution)
    reproject(src, out, src_transform=transform, src_crs="EPSG:4326", dst_transform=grid.transform,
              dst_crs=country.crs, resampling=Resampling.bilinear, src_nodata=np.nan, dst_nodata=np.nan)
    return out
