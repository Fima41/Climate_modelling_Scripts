"""Figures for the El Niño rainy-season analysis."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap

from . import terrain
from .plots import BASELINE, GRID, INK, INK_MUTED, INK_SECONDARY, SURFACE, _save, _source, _title
from .terrain_plots import composite, _halo

# Stepped classes: brown = drier, teal = wetter; blue = cooler, red = warmer.
RAIN_EDGES = [-50, -35, -20, -5, 5, 20, 35, 50]
RAIN_COLOURS = ["#8c510a", "#bf812d", "#dfc27d", "#f6e8c3", "#f2f1ec",
                "#c7eae5", "#80cdc1", "#35978f", "#01665e"]
RAIN_MM_EDGES = [-100, -60, -30, -10, 10, 30, 60, 100]
TEMP_EDGES = [-1.25, -0.75, -0.25, 0.25, 0.75, 1.25, 1.75, 2.25]
TEMP_COLOURS = ["#2166ac", "#67a9cf", "#d1e5f0", "#f2f1ec", "#fddbc7",
                "#f4a582", "#d6604d", "#b2182b", "#67001f"]
EL_NINO_COLOUR = "#a6611a"
DATA_CREDIT = ("Data: ERA5 monthly means (Copernicus C3S / ECMWF), 0.25° · Oceanic Niño Index: NOAA CPC · "
               "Terrain: Terrain Tiles on AWS (SRTM) · Boundaries: geoBoundaries")


def classify(values: np.ndarray, edges, colours) -> np.ndarray:
    """Values -> sRGB colours (0..1) of their stepped class."""
    palette = np.array([terrain._hex_rgb(c) for c in colours])
    return palette[np.digitize(values, edges)]


def signed(value: float, decimals: int = 0, unit: str = "") -> str:
    """'+5%', '-12 mm', or '0%' (never '-0%')."""
    text = f"{value:+.{decimals}f}"
    if float(text) == 0:
        text = f"{0:.{decimals}f}"
    return f"{text}{unit}"


def season_label(year: int) -> str:
    return f"{year}/{str(year + 1)[-2:]}"


def _stepped_cmap(edges, colours):
    bounds = [edges[0] - (edges[1] - edges[0])] + list(edges) + [edges[-1] + (edges[-1] - edges[-2])]
    return ListedColormap(colours), BoundaryNorm(bounds, len(colours)), bounds


# ---------------------------------------------------------------- 3D small multiples

def seasons_poster(panels: dict, columns: list[dict], rows: list[dict], header: dict, path: Path,
                   lusaka_xy: dict) -> Path:
    """Grid of 3D panels: one row per variable, one column per El Niño season.

    ``panels[(row, col)]`` is (rgb, alpha); ``columns`` give the season title and
    subtitle, ``rows`` the variable name, unit, legend classes and per-panel captions.
    """
    ph, pw = next(iter(panels.values()))[1].shape
    left, right, gap = 420, 340, 16
    head, col_head, caption, row_gap, foot = 400, 120, 80, 50, 170
    width_px = left + len(columns) * pw + (len(columns) - 1) * gap + right
    height_px = head + col_head + len(rows) * (ph + caption) + (len(rows) - 1) * row_gap + foot
    dpi = width_px / 16.0
    fig = plt.figure(figsize=(width_px / dpi, height_px / dpi), dpi=dpi)

    def box(x, y, w, h):  # pixel box from top-left -> figure fraction rect
        return (x / width_px, 1 - (y + h) / height_px, w / width_px, h / height_px)

    def at(x, y):
        return x / width_px, 1 - y / height_px

    fig.text(*at(80, 75), " ".join(header["kicker"].upper()), fontsize=10, color=INK_MUTED, fontweight="bold")
    fig.text(*at(76, 175), header["title"], fontsize=32, color=INK, fontweight="bold")
    fig.text(*at(80, 215), header["subtitle"], fontsize=12.5, color=INK_SECONDARY, va="top", linespacing=1.5)
    fig.add_artist(plt.Line2D([80 / width_px, 1 - 80 / width_px], [1 - 375 / height_px] * 2, color=GRID, lw=0.9))

    y0 = head + col_head
    for j, column in enumerate(columns):
        x = left + j * (pw + gap) + pw / 2
        fig.text(*at(x, head + 55), column["title"], ha="center", fontsize=17, color=INK, fontweight="bold")
        fig.text(*at(x, head + 90), column["subtitle"], ha="center", fontsize=9.5, color=INK_MUTED)

    for i, row in enumerate(rows):
        y = y0 + i * (ph + caption + row_gap)
        fig.text(*at(80, y + ph * 0.42), row["name"], fontsize=15, color=INK, fontweight="bold")
        fig.text(*at(80, y + ph * 0.42 + 30), row["unit"], fontsize=9.5, color=INK_SECONDARY, va="top",
                 linespacing=1.4)
        for j in range(len(columns)):
            rgb, alpha = panels[(i, j)]
            plate = composite(rgb, alpha, shadow_offset=(4, 7), shadow_blur=6.0, shadow_strength=0.25)
            ax = fig.add_axes(box(left + j * (pw + gap), y, pw, ph))
            ax.imshow(plate, interpolation="antialiased")
            ax.axis("off")
            lx, ly = lusaka_xy[(i, j)]
            ax.plot(lx, ly, marker="s", markersize=4.5, color=INK, markeredgecolor=SURFACE, markeredgewidth=1.0)
            if j == 0:
                ax.annotate("Lusaka", (lx, ly), xytext=(5, -5), textcoords="offset points", fontsize=8,
                            color=INK, path_effects=_halo())
            fig.text(*at(left + j * (pw + gap) + pw / 2, y + ph + 30), row["captions"][j], ha="center",
                     fontsize=10.5, color=INK_SECONDARY)

        cmap, norm, bounds = _stepped_cmap(row["edges"], row["colours"])
        cax = fig.add_axes(box(width_px - right + 70, y + 30, 26, ph - 60))
        cb = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), cax=cax, ticks=row["edges"])
        cb.ax.set_yticklabels([row["tick_format"](v) for v in row["edges"]])
        cb.ax.tick_params(labelsize=9, colors=INK_SECONDARY, length=0)
        cb.outline.set_visible(False)
        cax.set_title(row["legend_title"], fontsize=9.5, color=INK_SECONDARY, loc="left", pad=10)

    fig.text(*at(80, height_px - 75), header["notes"], fontsize=8.5, color=INK_MUTED)
    fig.text(*at(80, height_px - 45), DATA_CREDIT, fontsize=8.5, color=INK_MUTED)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, facecolor=SURFACE)
    plt.close(fig)
    return path


# ---------------------------------------------------------------- charts

def monthly_heatmaps(rain: np.ndarray, temp: np.ndarray, seasons: list[int], season_rain: np.ndarray,
                     season_temp: np.ndarray, path: Path) -> Path:
    """Month-by-month Zambia-average anomalies for each El Niño season (rows) and the season as a whole."""
    months = ["Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.4), gridspec_kw={"wspace": 0.12})
    specs = [
        (axes[0], np.column_stack([rain, season_rain]), RAIN_MM_EDGES, RAIN_COLOURS, (0, ""),
         "Rainfall, mm above or below normal"),
        (axes[1], np.column_stack([temp, season_temp]), TEMP_EDGES, TEMP_COLOURS, (1, ""),
         "Temperature, °C above or below normal"),
    ]
    for ax, table, edges, colours, fmt, name in specs:
        cmap, norm, _ = _stepped_cmap(edges, colours)
        ax.imshow(table, cmap=cmap, norm=norm, aspect="auto")
        for (r, c), value in np.ndenumerate(table):
            dark = norm(value) in (0, 1, len(colours) - 2, len(colours) - 1)
            ax.text(c, r, signed(value, *fmt), ha="center", va="center", fontsize=9.5,
                    color=SURFACE if dark else INK, fontweight="bold" if c == len(months) else "normal")
        ax.axvline(len(months) - 0.5, color=SURFACE, linewidth=4)
        ax.set_xticks(range(len(months) + 1), months + ["Oct–Mar"])
        ax.set_yticks(range(len(seasons)), [season_label(y) for y in seasons])
        ax.tick_params(length=0)
        ax.grid(False)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_title(name, fontsize=11.5, loc="left", pad=8)
    axes[1].set_yticklabels([])
    fig.suptitle("Month by month: how each El Niño season unfolded across Zambia", x=0.125, ha="left",
                 fontsize=13, fontweight="semibold", y=1.04)
    fig.text(0.125, 0.955, "Zambia-average anomalies against the 1991–2020 normal for each month",
             color=INK_SECONDARY, fontsize=9.5)
    _source(fig, DATA_CREDIT)
    return _save(fig, path)


def southern_rainfall_record(years: np.ndarray, anomaly: np.ndarray, el_nino: dict, path: Path) -> Path:
    """Rainy-season rainfall anomaly in southern Zambia for every season in the record."""
    fig, ax = plt.subplots(figsize=(12, 4.8))
    highlight = np.isin(years, list(el_nino))
    colours = np.where(highlight, EL_NINO_COLOUR, "#c9c7bf")
    ax.bar(years, anomaly, width=0.75, color=colours)
    ax.axhline(0, color=BASELINE, linewidth=1)
    for year, value in zip(years[highlight], anomaly[highlight]):
        ax.text(year, value - 2.5 if value < 0 else value + 1.5, season_label(int(year)), ha="center",
                va="top" if value < 0 else "bottom", fontsize=8.5, color=EL_NINO_COLOUR, fontweight="bold")
    gap = [y for y in range(int(years.min()), int(years.max())) if y not in set(years.tolist())]
    if gap:
        ax.axvspan(gap[0] - 0.5, gap[-1] + 0.5, color=GRID, alpha=0.5, linewidth=0)
        ax.text((gap[0] + gap[-1]) / 2, ax.get_ylim()[1] * 0.85, "no data", ha="center", fontsize=8.5,
                color=INK_MUTED)
    ax.set_ylabel("Rainfall, % above or below normal")
    ax.set_xlim(years.min() - 1, years.max() + 1)
    ticks = [y for y in years if y % 5 == 0]
    ax.set_xticks(ticks, [season_label(int(y)) for y in ticks])
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: signed(v, unit="%")))
    driest = int(years[np.argmin(anomaly)])
    _title(ax, "Southern Zambia's rainy season, every year on record",
           f"October–March rainfall south of 13.5° S compared with the 1991–2020 normal. El Niño seasons in brown. "
           f"{season_label(driest)} was the driest.")
    _source(fig, DATA_CREDIT)
    return _save(fig, path)
