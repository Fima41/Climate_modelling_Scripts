"""Figures for the extreme weather events analysis."""

from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TwoSlopeNorm

from .indices import WET_DAY_MM, leap_day_of_year, season_label, spells
from .plots import COOL, DIVERGING, INK, INK_MUTED, INK_SECONDARY, WARM, _save, _title
from .trends import SenTrend

SOURCE = "Data: ERA5 reanalysis (Copernicus/ECMWF) via Open-Meteo, district average"
RAIN = "#2a78d6"
RAIN_HEAVY = "#104281"
DRY = "#eb6834"


def _source(fig) -> None:
    fig.text(0.01, -0.03, SOURCE, color=INK_MUTED, fontsize=8)


def _trend_line(ax, trend: SenTrend, series: pd.Series) -> pd.Series:
    """Draw a Theil-Sen trend line through the median of the data and return it."""
    x = series.index.to_numpy(float)
    slope = trend.slope_per_decade / 10
    intercept = np.median(series.to_numpy() - slope * x)
    line = pd.Series(intercept + slope * x, index=series.index)
    ax.plot(line.index, line, color=INK, linewidth=2)
    return line


def heatwave_days(annual: pd.DataFrame, trend: SenTrend, place: str, path: Path) -> Path:
    days = annual.heatwave_days
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar(days.index, days, width=0.75, color=WARM)
    _trend_line(ax, trend, days)

    ax.text(0.01, 0.95, f"Black line: trend of {trend.slope_per_decade:+.1f} days per decade "
                        f"(p = {trend.p_value:.1g})",
            transform=ax.transAxes, color=INK, fontsize=9, fontweight="semibold")
    peak = days.idxmax()
    ax.annotate(f"{peak}: {days.max()} days", (peak, days.max()), xytext=(-6, 4),
                textcoords="offset points", ha="right", color=INK, fontsize=9)

    ax.set_ylabel("Heatwave days per year")
    ax.set_xlim(days.index[0] - 1, days.index[-1] + 1)
    _title(ax, f"{place}: heatwave days per year, {days.index[0]}–{days.index[-1]}",
           "Days in a run of 3 or more days with maximum temperature above the "
           "1961–1990 90th percentile for that time of year")
    _source(fig)
    return _save(fig, path)


def hot_days_cold_nights(annual: pd.DataFrame, place: str, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot([annual.index[0] - 1, annual.index[-1]], [10, 10], color=INK_MUTED, linewidth=1,
            linestyle=(0, (4, 3)))
    ax.annotate("10% = baseline", (annual.index[-1], 10), xytext=(12, 0),
                textcoords="offset points", va="center", color=INK_SECONDARY, fontsize=9)

    for column, color, label in [("hot_days_pct", WARM, "Hot days"),
                                 ("cold_nights_pct", COOL, "Cold nights")]:
        smooth = annual[column].rolling(5, center=True, min_periods=5).mean()
        ax.plot(annual.index, annual[column], color=color, linewidth=1, alpha=0.35)
        ax.plot(smooth.index, smooth, color=color, linewidth=2, label=f"{label} (5-year average)")
        last = smooth.dropna()
        ax.annotate(label, (last.index[-1], last.iloc[-1]), xytext=(8, 0),
                    textcoords="offset points", va="center", color=INK, fontsize=9,
                    fontweight="semibold")

    ax.set_ylim(bottom=0)
    ax.set_ylabel("Share of days (%)")
    ax.set_xlim(annual.index[0] - 1, annual.index[-1] + 8)
    ax.legend(loc="upper left", bbox_to_anchor=(0, 0.93), frameon=False, labelcolor=INK_SECONDARY)
    _title(ax, f"{place}: more hot days, fewer cold nights",
           "Hot days: max temperature above the 90th percentile · Cold nights: "
           "min temperature below the 10th percentile (thin lines: single years)")
    _source(fig)
    return _save(fig, path)


def compound_event(daily: pd.DataFrame, threshold: pd.Series, events: pd.DataFrame,
                   start: str, end: str, place: str, path: Path) -> Path:
    """Daily Tmax against its heatwave threshold, above daily rainfall."""
    window = daily.loc[start:end]
    limit = threshold.reindex(leap_day_of_year(window.index)).to_numpy()

    fig, (top, bottom) = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True,
                                      gridspec_kw={"height_ratios": [3, 2], "hspace": 0.12})
    for _, event in events.iterrows():
        if event.end >= window.index[0] and event.start <= window.index[-1]:
            for ax in (top, bottom):
                ax.axvspan(event.start - pd.Timedelta(hours=12), event.end + pd.Timedelta(hours=12),
                           color=WARM, alpha=0.10, linewidth=0)
            if event.length >= 10:
                top.text(event.start + (event.end - event.start) / 2, 0.98,
                         f"{event.length}-day heatwave", transform=top.get_xaxis_transform(),
                         ha="center", va="top", color=INK, fontsize=9, fontweight="semibold")

    top.plot(window.index, window.tmax, color=WARM, linewidth=2, label="Daily max temperature")
    top.plot(window.index, limit, color=INK_MUTED, linewidth=1, linestyle=(0, (4, 3)),
             label="Heatwave threshold (90th percentile)")
    top.legend(loc="lower right", frameon=False, labelcolor=INK_SECONDARY)
    top.set_ylabel("Max temperature (°C)")

    bottom.bar(window.index, window.prcp, width=0.8, color=RAIN)
    dry = [s for s in _dry_spells(window.prcp) if s[2] >= 10]
    for s, e, n in dry:
        bottom.annotate(f"{n} dry days", (s + (e - s) / 2, 0), xytext=(0, 6),
                        textcoords="offset points", ha="center", color=INK, fontsize=9,
                        fontweight="semibold")
        bottom.plot([s, e], [0, 0], color=DRY, linewidth=4, solid_capstyle="butt")
    bottom.set_ylabel("Rainfall (mm/day)")
    bottom.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))

    _title(top, f"{place}: heat and drought together, {pd.Timestamp(start):%b}–"
                f"{pd.Timestamp(end):%b %Y}",
           "A record heatwave arrived during a mid-season dry spell in the 2023/24 El Niño season")
    _source(fig)
    return _save(fig, path)


def _dry_spells(prcp: pd.Series) -> list[tuple[pd.Timestamp, pd.Timestamp, int]]:
    table = spells(prcp < WET_DAY_MM)
    return list(zip(table.start, table.end, table.length))


def rainy_seasons(seasons: pd.DataFrame, place: str, path: Path) -> Path:
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(11, 7), sharex=True,
                                      gridspec_kw={"height_ratios": [3, 2], "hspace": 0.15})
    other = seasons.total_mm - seasons.very_wet_mm
    top.bar(seasons.index, other, width=0.75, color=RAIN, label="Other rain")
    top.bar(seasons.index, seasons.very_wet_mm, bottom=other, width=0.75, color=RAIN_HEAVY,
            label="Rain on very wet days (>95th percentile)")
    base_mean = seasons.loc[1961:1990, "total_mm"].mean()
    top.axhline(base_mean, color=INK_MUTED, linewidth=1, linestyle=(0, (4, 3)),
                label=f"1961–1990 average ({base_mean:.0f} mm)")
    top.set_ylabel("Season total (mm)")
    top.legend(loc="upper left", frameon=False, ncols=3, labelcolor=INK_SECONDARY,
               bbox_to_anchor=(0, 1.0))
    top.set_ylim(0, seasons.total_mm.max() * 1.18)

    bottom.bar(seasons.index, seasons.longest_dry_spell, width=0.75, color=DRY)
    for season in seasons.longest_dry_spell.nlargest(2).index:
        bottom.annotate(season_label(season), (season, seasons.longest_dry_spell[season]),
                        xytext=(0, 3), textcoords="offset points", ha="center",
                        color=INK, fontsize=9)
    bottom.set_ylabel("Longest dry spell,\nNov–Mar (days)")
    bottom.set_xlim(seasons.index[0] - 1, seasons.index[-1] + 1)
    bottom.set_xlabel("Rainy season starting year (e.g. 2023 = 2023/24)")

    _title(top, f"{place}: rainy season totals and dry spells",
           "Rainy season runs July–June; dry days have less than 1 mm of rain")
    _source(fig)
    return _save(fig, path)


def monthly_heatmap(anomaly: pd.DataFrame, place: str, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(11, 4.2))
    limit = float(np.nanmax(np.abs(anomaly.to_numpy())))
    norm = TwoSlopeNorm(vcenter=0, vmin=-limit, vmax=limit)
    image = ax.imshow(anomaly.T.to_numpy(), aspect="auto", cmap=DIVERGING, norm=norm,
                      extent=(anomaly.index[0] - 0.5, anomaly.index[-1] + 0.5, 12.5, 0.5))
    ax.set_yticks(range(1, 13), ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
    ax.grid(False)
    for side in ("bottom",):
        ax.spines[side].set_visible(False)
    colorbar = fig.colorbar(image, ax=ax, pad=0.01, fraction=0.03)
    colorbar.set_label("°C vs 1961–1990", color=INK_SECONDARY)
    colorbar.outline.set_visible(False)
    colorbar.ax.tick_params(color=INK_MUTED, labelcolor=INK_MUTED)
    _title(ax, f"{place}: monthly maximum temperature anomaly",
           "Each cell is one month; red is warmer and blue cooler than the 1961–1990 average")
    _source(fig)
    return _save(fig, path)
