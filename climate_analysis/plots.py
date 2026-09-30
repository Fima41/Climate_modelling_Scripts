"""Publication-style figures for temperature anomaly analysis."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

from .trends import Trend

# Palette: blue <-> red diverging pair with a neutral gray midpoint.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
COOL = "#2a78d6"
WARM = "#e34948"

DIVERGING = LinearSegmentedColormap.from_list(
    "anomaly", ["#0d366b", "#2a78d6", "#9ec5f4", "#f0efec", "#f2a6a5", "#e34948", "#8f1d1c"]
)

plt.rcParams.update({
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"],
    "font.size": 10,
    "text.color": INK,
    "axes.labelcolor": INK_SECONDARY,
    "axes.edgecolor": BASELINE,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.spines.left": False,
    "axes.grid": True,
    "axes.grid.axis": "y",
    "axes.axisbelow": True,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "xtick.color": INK_MUTED,
    "ytick.color": INK_MUTED,
    "ytick.left": False,
    "axes.titlesize": 13,
    "axes.titleweight": "semibold",
    "axes.titlelocation": "left",
})


def _title(ax, title: str, subtitle: str) -> None:
    ax.set_title(title, pad=24)
    ax.text(0, 1.02, subtitle, transform=ax.transAxes, color=INK_SECONDARY, fontsize=9.5)


def _source(fig, text: str = "Data: NASA GISTEMP v4") -> None:
    fig.text(0.01, -0.03, text, color=INK_MUTED, fontsize=8)


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def anomaly_bars(series: pd.Series, smooth: pd.Series, region: str, path: Path) -> Path:
    """Annual anomaly bars coloured by sign, with a smoothed trend line."""
    fig, ax = plt.subplots(figsize=(11, 5))
    colors = np.where(series >= 0, WARM, COOL)
    ax.bar(series.index, series, width=0.75, color=colors)
    ax.plot(smooth.index, smooth, color=INK, linewidth=2)
    ax.axhline(0, color=BASELINE, linewidth=1)

    last = smooth.dropna()
    ax.annotate("10-year average", (last.index[-1], last.iloc[-1]),
                xytext=(-8, 14), textcoords="offset points", ha="right",
                color=INK_SECONDARY, fontsize=9)
    hottest = series.idxmax()
    ax.annotate(f"{hottest}: +{series.max():.2f} °C", (hottest, series.max()),
                xytext=(-6, 6), textcoords="offset points", ha="right",
                color=INK, fontsize=9, fontweight="semibold")

    ax.set_ylabel("Anomaly vs 1951–1980 (°C)")
    ax.set_xlim(series.index[0] - 1, series.index[-1] + 1)
    _title(ax, f"{region} surface temperature anomaly, {series.index[0]}–{series.index[-1]}",
           "Red bars: warmer than the 1951–1980 average · Blue bars: cooler")
    _source(fig)
    return _save(fig, path)


def warming_stripes(series: pd.Series, region: str, path: Path) -> Path:
    """Ed Hawkins-style warming stripes: one stripe per year."""
    fig, ax = plt.subplots(figsize=(11, 2.8))
    limit = float(np.abs(series).max())
    norm = TwoSlopeNorm(vcenter=0, vmin=-limit, vmax=limit)
    ax.bar(series.index, 1, width=1.0, color=DIVERGING(norm(series.to_numpy())))
    ax.set_xlim(series.index[0] - 0.5, series.index[-1] + 0.5)
    ax.set_ylim(0, 1)
    ax.set_yticks([])
    ax.grid(False)
    ax.spines["bottom"].set_visible(False)
    ax.tick_params(axis="x", length=0)
    _title(ax, f"{region} warming stripes, {series.index[0]}–{series.index[-1]}",
           "Each stripe is one year, coloured from coolest (blue) to warmest (red)")
    _source(fig)
    return _save(fig, path)


def rolling_trend_plot(rolling: pd.Series, full: Trend, window: int,
                       region: str, path: Path) -> Path:
    """How fast the planet warmed over each trailing window."""
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.axhline(0, color=BASELINE, linewidth=1)
    ax.axhline(full.slope_per_decade, color=INK_MUTED, linewidth=1, linestyle=(0, (4, 3)))
    ax.annotate(f"Long-term rate ({full.start}–{full.end})",
                (rolling.index[-1], full.slope_per_decade), xytext=(0, -6),
                textcoords="offset points", ha="right", va="top",
                color=INK_SECONDARY, fontsize=9)
    ax.plot(rolling.index, rolling, color=WARM, linewidth=2)
    ax.plot(rolling.index[-1], rolling.iloc[-1], "o", color=WARM, markersize=8,
            markeredgecolor=SURFACE, markeredgewidth=2)
    ax.annotate(f"{rolling.iloc[-1]:+.2f} °C/decade", (rolling.index[-1], rolling.iloc[-1]),
                xytext=(-10, 0), textcoords="offset points", ha="right", va="center",
                color=INK, fontsize=9, fontweight="semibold")

    ax.set_ylabel("Warming rate (°C per decade)")
    _title(ax, f"{region} warming rate over trailing {window}-year windows",
           f"Each point is the linear trend of the {window} years ending that year")
    _source(fig)
    return _save(fig, path)


def seasonal_trends(trends: dict[str, Trend], region: str, path: Path) -> Path:
    """Warming rate per season with 95% confidence intervals."""
    labels = {"DJF": "Dec–Feb", "MAM": "Mar–May", "JJA": "Jun–Aug", "SON": "Sep–Nov"}
    names = list(trends)[::-1]
    slopes = [trends[n].slope_per_decade for n in names]
    errors = [trends[n].ci95_per_decade for n in names]
    period = next(iter(trends.values()))

    fig, ax = plt.subplots(figsize=(9, 4))
    y = np.arange(len(names))
    ax.barh(y, slopes, height=0.55, color=WARM, xerr=errors,
            error_kw={"ecolor": INK_SECONDARY, "elinewidth": 1.2, "capsize": 4})
    for yi, slope, err in zip(y, slopes, errors):
        ax.text(slope + err + 0.005, yi, f"{slope:+.3f}", va="center",
                color=INK, fontsize=9)
    ax.set_yticks(y, [labels.get(n, n) for n in names], color=INK_SECONDARY)
    ax.grid(axis="x")
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Warming rate (°C per decade), with 95% confidence interval")
    ax.set_xlim(0, max(s + e for s, e in zip(slopes, errors)) * 1.2)
    _title(ax, f"{region} warming by season, {period.start}–{period.end}",
           "Northern Hemisphere season names")
    _source(fig)
    return _save(fig, path)
