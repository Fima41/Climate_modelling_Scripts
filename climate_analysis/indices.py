"""Climate extremes indices computed from daily temperature and rainfall.

Definitions follow the ETCCDI climate-extremes indices where one exists
(TX90p, TN10p, Rx1day, Rx5day, R20mm, R95pTOT, CDD). Percentile thresholds are
calendar-day percentiles from a base period, pooled over a 5-day window.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

BASE_PERIOD = (1961, 1990)
WET_DAY_MM = 1.0


def leap_day_of_year(index: pd.DatetimeIndex) -> np.ndarray:
    """Day of year on a 366-day calendar, so 1 March is always day 61."""
    shift = (~index.is_leap_year) & (index.month > 2)
    return index.dayofyear.to_numpy() + shift.astype(int)


def daily_percentile(series: pd.Series, q: float, base: tuple[int, int] = BASE_PERIOD,
                     window: int = 5) -> pd.Series:
    """Calendar-day percentile threshold, indexed by leap day of year (1-366)."""
    s = series.loc[str(base[0]):str(base[1])].dropna()
    doy = leap_day_of_year(s.index)
    values = s.to_numpy()
    half = window // 2

    thresholds = {}
    for day in range(1, 367):
        distance = np.abs(doy - day)
        distance = np.minimum(distance, 366 - distance)
        thresholds[day] = np.percentile(values[distance <= half], q)
    return pd.Series(thresholds, name=f"p{q:g}")


def exceeds(series: pd.Series, threshold: pd.Series, above: bool = True) -> pd.Series:
    """Boolean series: is each day beyond its calendar-day threshold?"""
    limit = threshold.reindex(leap_day_of_year(series.index)).to_numpy()
    result = series.to_numpy() > limit if above else series.to_numpy() < limit
    return pd.Series(result, index=series.index)


def spells(mask: pd.Series, min_length: int = 1) -> pd.DataFrame:
    """Runs of consecutive True days, as a table of start, end and length."""
    values = mask.to_numpy(bool)
    edges = np.diff(np.concatenate([[0], values.astype(int), [0]]))
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1) - 1
    lengths = ends - starts + 1
    keep = lengths >= min_length
    return pd.DataFrame({
        "start": mask.index[starts[keep]],
        "end": mask.index[ends[keep]],
        "length": lengths[keep],
    })


def heatwaves(tmax: pd.Series, threshold: pd.Series, min_length: int = 3) -> pd.DataFrame:
    """Heatwaves: at least ``min_length`` consecutive days above the Tmax threshold."""
    hot = exceeds(tmax, threshold)
    events = spells(hot, min_length)
    events["peak_tmax"] = [tmax.loc[s:e].max() for s, e in zip(events.start, events.end)]
    return events


def annual_temperature_indices(df: pd.DataFrame, base: tuple[int, int] = BASE_PERIOD) -> pd.DataFrame:
    """Yearly heat and cold indices for complete calendar years."""
    tx90 = daily_percentile(df.tmax, 90, base)
    tn10 = daily_percentile(df.tmin, 10, base)

    hot_days = exceeds(df.tmax, tx90)
    cold_nights = exceeds(df.tmin, tn10, above=False)
    events = heatwaves(df.tmax, tx90)
    by_start = events.groupby(events.start.dt.year)

    years = df.index.year
    counts = pd.Series(years).value_counts()
    complete = counts[counts >= 365].index.sort_values()

    annual = pd.DataFrame({
        "hot_days_pct": hot_days.groupby(years).mean() * 100,
        "cold_nights_pct": cold_nights.groupby(years).mean() * 100,
        "heatwave_events": by_start.size(),
        "heatwave_days": by_start.length.sum(),
        "longest_heatwave": by_start.length.max(),
        "txx": df.tmax.groupby(years).max(),
        "tnn": df.tmin.groupby(years).min(),
    }).reindex(complete)
    heatwave_cols = ["heatwave_events", "heatwave_days", "longest_heatwave"]
    annual[heatwave_cols] = annual[heatwave_cols].fillna(0).astype(int)
    annual.index.name = "year"
    return annual


def monthly_anomaly(series: pd.Series, base: tuple[int, int] = BASE_PERIOD) -> pd.DataFrame:
    """Year x month table of monthly means minus the base-period monthly mean."""
    monthly = series.resample("MS").mean()
    table = monthly.groupby([monthly.index.year, monthly.index.month]).first().unstack()
    climatology = table.loc[base[0]:base[1]].mean()
    return table - climatology


def season_year(index: pd.DatetimeIndex) -> np.ndarray:
    """Rainy-season label: July 2023 to June 2024 is season 2023 (i.e. 2023/24)."""
    return np.where(index.month >= 7, index.year, index.year - 1)


def rain_onset(prcp: pd.Series, start_month: int = 10, rain_mm: float = 20.0,
               over_days: int = 3, dry_spell: int = 10, check_days: int = 30) -> pd.Timestamp | None:
    """First day of a season's rains using a standard agronomic definition.

    Onset is the first day from 1 October on which the ``over_days`` total
    reaches ``rain_mm``, with no dry spell of ``dry_spell`` days in the
    following ``check_days`` days (so a false start does not count).
    """
    season = prcp[prcp.index >= pd.Timestamp(prcp.index[0].year, start_month, 1)]
    totals = season.rolling(over_days).sum()
    for day in totals.index[totals >= rain_mm]:
        following = season.loc[day + pd.Timedelta(days=1): day + pd.Timedelta(days=check_days)]
        if len(following) < check_days:
            return None
        longest_dry = spells(following < WET_DAY_MM).length.max()
        if pd.isna(longest_dry) or longest_dry < dry_spell:
            return day
    return None


def seasonal_rain_indices(prcp: pd.Series, base: tuple[int, int] = BASE_PERIOD) -> pd.DataFrame:
    """Rainy-season (July-June) indices for complete seasons."""
    labels = season_year(prcp.index)
    wet = prcp[prcp >= WET_DAY_MM]
    base_wet = wet[(season_year(wet.index) >= base[0]) & (season_year(wet.index) <= base[1])]
    p95 = np.percentile(base_wet, 95)

    rows = {}
    for season, rain in prcp.groupby(labels):
        if len(rain) < 365:
            continue
        core = rain[(rain.index.month >= 11) | (rain.index.month <= 3)]  # Nov-Mar
        onset = rain_onset(rain)
        rows[season] = {
            "total_mm": rain.sum(),
            "wet_days": int((rain >= WET_DAY_MM).sum()),
            "rx1day_mm": rain.max(),
            "rx5day_mm": rain.rolling(5).sum().max(),
            "heavy_days": int((rain >= 20).sum()),
            "very_wet_mm": rain[rain > p95].sum(),
            "longest_dry_spell": int(spells(core < WET_DAY_MM).length.max()),
            "onset": onset,
            "onset_day": (onset - pd.Timestamp(season, 10, 1)).days if onset is not None else np.nan,
        }
    result = pd.DataFrame.from_dict(rows, orient="index")
    result.index.name = "season"
    return result


def season_label(season: int) -> str:
    return f"{season}/{str(season + 1)[-2:]}"
