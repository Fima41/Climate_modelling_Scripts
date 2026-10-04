"""Poster and chart figures for the 3D terrain analysis."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import patheffects
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Polygon

from . import terrain
from .plots import GRID, INK, INK_MUTED, INK_SECONDARY, SURFACE, _save, _source, _title

WATER = "#3d7fb8"
WATER_FILL = "#7fb0d9"
WATER_TEXT = "#24608f"
RELIEF_TEXT = "#5b4030"
DATA_CREDIT = ("Data: Terrain Tiles on AWS (SRTM, GMTED2010, ETOPO1) · geoBoundaries (CC BY 4.0) · "
               "Natural Earth")

ELEVATION_CMAP = LinearSegmentedColormap.from_list(
    "hypsometric",
    [((h - terrain.HYPSOMETRIC_STOPS[0][0]) /
      (terrain.HYPSOMETRIC_STOPS[-1][0] - terrain.HYPSOMETRIC_STOPS[0][0]), c)
     for h, c in terrain.HYPSOMETRIC_STOPS],
)


@dataclass(frozen=True)
class Label:
    text: str
    lon: float
    lat: float
    kind: str = "city"          # city, capital, relief, water, waterpoint, country
    dx: float = 6.0             # text offset from the anchor, in points
    dy: float = 4.0
    ha: str = "left"
    rotation: float = 0.0


# ---------------------------------------------------------------- compositing helpers

def premultiplied_alpha(rgb: np.ndarray, covered: np.ndarray) -> np.ndarray:
    """Alpha for a render whose background is pure black.

    Edge pixels mix terrain colour with black, so their brightness relative to
    the nearest fully covered neighbour estimates how much of the pixel the
    terrain covers. Interior pixels are opaque and empty pixels transparent.
    """
    from scipy.ndimage import binary_erosion, grey_dilation

    luminance = rgb.astype(float).max(axis=-1)
    interior = binary_erosion(covered, iterations=1)
    reference = grey_dilation(np.where(interior, luminance, 0.0), size=5)
    alpha = np.where(reference > 0, luminance / np.maximum(reference, 1.0), 0.0)
    alpha = np.clip(alpha, 0.0, 1.0)
    alpha[interior] = 1.0
    alpha[~covered & (luminance <= 0)] = 0.0
    return alpha


def composite(rgb: np.ndarray, alpha: np.ndarray, background: str = SURFACE,
              shadow_offset: tuple[int, int] = (10, 16), shadow_blur: float = 14.0,
              shadow_strength: float = 0.28) -> np.ndarray:
    """Place a premultiplied render on a paper background with a soft drop shadow."""
    from scipy.ndimage import gaussian_filter, shift

    bg = np.array(terrain._hex_rgb(background))
    shadow = gaussian_filter(shift(alpha, (shadow_offset[1], shadow_offset[0]), order=1), shadow_blur)
    paper = bg[None, None, :] * (1.0 - shadow_strength * shadow[..., None])
    return np.clip(rgb.astype(float) / 255.0 + paper * (1.0 - alpha[..., None]), 0.0, 1.0)


def draw_layer(width: int, height: int, draw) -> np.ndarray:
    """Draw with matplotlib onto a transparent pixel-exact canvas; returns RGBA 0..1."""
    fig = plt.figure(figsize=(width / 100, height / 100), dpi=100)
    fig.patch.set_alpha(0.0)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(-0.5, width - 0.5)
    ax.set_ylim(height - 0.5, -0.5)
    ax.axis("off")
    ax.patch.set_alpha(0.0)
    draw(ax)
    canvas = FigureCanvasAgg(fig)
    canvas.draw()
    layer = np.asarray(canvas.buffer_rgba(), dtype=float) / 255.0
    plt.close(fig)
    return layer


def over(base: np.ndarray, layer: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    alpha = layer[..., 3:4] * (1.0 if mask is None else mask[..., None])
    return base * (1.0 - alpha) + layer[..., :3] * alpha


# ---------------------------------------------------------------- the poster

POSTER_INCHES = (16.0, 11.0)
HEADER = 0.12   # figure fraction above the map
FOOTER = 0.16   # figure fraction below the map
POSTER_DPI = 200


def map_size(width_px: int) -> tuple[int, int]:
    """Pixel size of the map panel for a poster ``width_px`` wide."""
    height_px = width_px * POSTER_INCHES[1] / POSTER_INCHES[0]
    return width_px, int(round(height_px * (1.0 - HEADER - FOOTER)))


def terrain_poster(image: np.ndarray, alpha: np.ndarray, project, water_lines, water_polys,
                   labels: list[Label], stats: dict, africa: list[dict], country_geom: dict,
                   path: Path, exaggeration: float = 25.0) -> Path:
    """Compose the final poster: header, the 3D map, and a footer with legend and key numbers.

    ``project(lon, lat, on_terrain=True)`` maps geographic points to map-panel pixels;
    ``water_lines`` are (lon/lat array, width) pairs and ``water_polys`` lon/lat rings.
    """
    h, w = alpha.shape

    def draw_water(ax):
        segments = [project(coords[:, 0], coords[:, 1]) for coords, _ in water_lines]
        ax.add_collection(LineCollection(segments, colors=WATER, linewidths=[wd for _, wd in water_lines],
                                         capstyle="round", joinstyle="round", alpha=0.9))
        for ring in water_polys:
            ax.add_patch(Polygon(project(ring[:, 0], ring[:, 1]), closed=True, facecolor=WATER_FILL,
                                 edgecolor=WATER, linewidth=0.6))

    plate = over(composite(image, alpha), draw_layer(w, h, draw_water), mask=alpha)

    dpi = w / POSTER_INCHES[0]
    fig = plt.figure(figsize=POSTER_INCHES, dpi=dpi)
    ax = fig.add_axes((0, FOOTER, 1, 1 - HEADER - FOOTER))
    ax.imshow(plate, interpolation="none")
    ax.set_xlim(-0.5, w - 0.5)
    ax.set_ylim(h - 0.5, -0.5)
    ax.axis("off")
    _place_labels(ax, labels, project)
    _header(fig)
    _footer(fig, stats, exaggeration)
    _legend(fig)
    _locator(fig, africa, country_geom)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, facecolor=SURFACE)
    plt.close(fig)
    return path


def _halo(color=SURFACE, width=2.2):
    return [patheffects.withStroke(linewidth=width, foreground=color, alpha=0.8)]


def _place_labels(ax, labels: list[Label], project) -> None:
    styles = {
        "capital": dict(fontsize=12.5, fontweight="bold", color=INK),
        "city": dict(fontsize=9.5, color=INK),
        "relief": dict(fontsize=8.5, color=RELIEF_TEXT, style="italic", fontweight="bold"),
        "water": dict(fontsize=9, color=WATER_TEXT, style="italic"),
        "waterpoint": dict(fontsize=9, color=WATER_TEXT, style="italic"),
        "country": dict(fontsize=10, color=INK_MUTED),
    }
    for label in labels:
        x, y = project(np.array([label.lon]), np.array([label.lat]),
                       on_terrain=label.kind != "country")[0]
        text = label.text.upper() if label.kind in ("relief", "country") else label.text
        if label.kind in ("relief", "country"):
            text = " ".join(text)  # thin-space letter spacing for area names
        if label.kind == "capital":
            ax.plot(x, y, marker="s", markersize=7, color=INK, markeredgecolor=SURFACE,
                    markeredgewidth=1.4, zorder=5)
        elif label.kind == "city":
            ax.plot(x, y, marker="o", markersize=4.5, color=INK, markeredgecolor=SURFACE,
                    markeredgewidth=1.1, zorder=5)
        elif label.kind == "waterpoint":
            ax.plot(x, y, marker="v", markersize=6, color=WATER, markeredgecolor=SURFACE,
                    markeredgewidth=1.0, zorder=5)
        ax.annotate(text, (x, y), xytext=(label.dx, label.dy), textcoords="offset points",
                    ha=label.ha, va="center", rotation=label.rotation, rotation_mode="anchor", zorder=6,
                    path_effects=None if label.kind == "country" else _halo(), **styles[label.kind])


def _header(fig) -> None:
    fig.text(0.035, 0.955, " ".join("THE CENTRAL AFRICAN PLATEAU"), fontsize=10,
             color=INK_MUTED, fontweight="bold")
    fig.text(0.032, 0.893, "Zambia", fontsize=48, color=INK, fontweight="bold")
    fig.text(0.285, 0.942,
             "A high, gently rolling plateau, broken by the deep rift valleys\n"
             "of the Luangwa and the middle Zambezi. Shaded relief, path-traced in 3D.",
             fontsize=12.5, color=INK_SECONDARY, va="top", linespacing=1.5)
    fig.add_artist(plt.Line2D([0.035, 0.965], [0.882, 0.882], color=GRID, linewidth=0.9))


def _footer(fig, stats: dict, exaggeration: float) -> None:
    fig.add_artist(plt.Line2D([0.035, 0.965], [FOOTER - 0.005, FOOTER - 0.005], color=GRID, linewidth=0.9))
    callouts = [
        (f"{stats['share_above_1000']:.0f}%", "of the country lies more than\n1,000 m above sea level"),
        (f"{stats['max']:,.0f} m", "highest ground, in the Mafinga\nHills on the Malawi border"),
        (f"{stats['min']:,.0f} m", "lowest ground, where the\nLuangwa joins the Zambezi"),
    ]
    for i, (value, caption) in enumerate(callouts):
        x = 0.335 + i * 0.155
        fig.text(x, 0.103, value, fontsize=22, color=INK, fontweight="bold")
        fig.text(x, 0.089, caption, fontsize=9.5, color=INK_SECONDARY, va="top", linespacing=1.4)
    fig.text(0.035, 0.030,
             f"Vertical exaggeration {exaggeration:.0f}×  ·  Lambert azimuthal equal-area projection  ·  "
             "Path-traced on the GPU with forge3d", fontsize=8, color=INK_MUTED)
    fig.text(0.035, 0.014, DATA_CREDIT, fontsize=8, color=INK_MUTED)


def _legend(fig) -> None:
    cax = fig.add_axes((0.035, 0.097, 0.235, 0.014))
    gradient = np.linspace(0, 1, 512)[None, :]
    lo, hi = terrain.HYPSOMETRIC_STOPS[0][0], terrain.HYPSOMETRIC_STOPS[-1][0]
    cax.imshow(gradient, aspect="auto", cmap=ELEVATION_CMAP, extent=(lo, hi, 0, 1))
    cax.set_yticks([])
    ticks = [500, 1000, 1500, 2000]
    cax.set_xticks(ticks, [f"{t:,}" for t in ticks])
    cax.tick_params(axis="x", length=3, color=INK_MUTED, labelsize=8.5, labelcolor=INK_SECONDARY)
    for spine in cax.spines.values():
        spine.set_visible(False)
    cax.grid(False)
    cax.set_title("Elevation (metres above sea level)", fontsize=9.5, color=INK_SECONDARY,
                  loc="left", fontweight="normal", pad=7)


def _locator(fig, africa: list[dict], country_geom: dict) -> None:
    ax = fig.add_axes((0.865, 0.03, 0.10, 0.12))
    ax.set_aspect("equal")
    for feature in africa:
        for ring in _rings(feature["geometry"]):
            ax.add_patch(Polygon(ring, closed=True, facecolor="#e4e2da", edgecolor=SURFACE, linewidth=0.3))
    for ring in _rings(country_geom):
        ax.add_patch(Polygon(ring, closed=True, facecolor=INK, edgecolor=INK, linewidth=0.3))
    ax.set_xlim(-19, 53)
    ax.set_ylim(-36, 38)
    ax.axis("off")
    fig.text(0.825, 0.103, "Location\nin Africa", fontsize=9.5, color=INK_SECONDARY, va="top",
             ha="right", linespacing=1.4)


def _rings(geometry: dict) -> list[np.ndarray]:
    if geometry["type"] == "Polygon":
        return [np.asarray(geometry["coordinates"][0])[:, :2]]
    if geometry["type"] == "MultiPolygon":
        return [np.asarray(poly[0])[:, :2] for poly in geometry["coordinates"]]
    return []


# ---------------------------------------------------------------- supporting charts

def elevation_profile(distance: np.ndarray, elevation: np.ndarray, inside: np.ndarray,
                      marks: list[tuple[float, str]], title: str, subtitle: str, path: Path) -> Path:
    """Cross-section of the country, filled with hypsometric tints by height."""
    fig, ax = plt.subplots(figsize=(11, 4.6))
    floor, top = 200.0, max(1900.0, float(np.nanmax(elevation)) + 450)
    lo, hi = terrain.HYPSOMETRIC_STOPS[0][0], terrain.HYPSOMETRIC_STOPS[-1][0]
    shown = np.where(inside, elevation, np.nan)
    fill = ax.fill_between(distance, floor, shown, color="none", linewidth=0)
    tint = ax.imshow(np.linspace(top, floor, 600)[:, None], aspect="auto", cmap=ELEVATION_CMAP,
                     vmin=lo, vmax=hi, extent=(distance[0], distance[-1], floor, top), zorder=1)
    clip = fill.get_paths()
    from matplotlib.path import Path as MplPath
    tint.set_clip_path(MplPath.make_compound_path(*clip), transform=ax.transData)
    ax.plot(distance, shown, color=INK, linewidth=1.0, zorder=3)
    ax.plot(distance, np.where(inside, np.nan, elevation), color=INK_MUTED, linewidth=0.9,
            linestyle=":", zorder=3)
    for d, name in marks:
        window = np.abs(distance - d) < 20
        peak = float(np.nanmax(elevation[window]))
        ax.plot([d, d], [peak + 40, peak + 170], color=INK_MUTED, linewidth=0.8, zorder=3)
        ax.text(d, peak + 200, name, ha="center", va="bottom", fontsize=9, color=INK_SECONDARY)
    ax.set_xlim(distance[0], distance[-1])
    ax.set_ylim(floor, top)
    ax.set_xlabel("Distance (km)")
    ax.set_ylabel("Elevation (m)")
    _title(ax, title, subtitle)
    _source(fig, DATA_CREDIT)
    return _save(fig, path)


def elevation_bands(edges, shares: np.ndarray, path: Path) -> Path:
    """Share of the country's area in each elevation band."""
    fig, ax = plt.subplots(figsize=(11, 4.6))
    mids = (np.asarray(edges[:-1]) + np.asarray(edges[1:])) / 2
    colours = ELEVATION_CMAP((mids - terrain.HYPSOMETRIC_STOPS[0][0]) /
                             (terrain.HYPSOMETRIC_STOPS[-1][0] - terrain.HYPSOMETRIC_STOPS[0][0]))
    labels = [f"{lo:,}–{hi:,}" for lo, hi in zip(edges[:-1], edges[1:])]
    bars = ax.bar(labels, shares, color=colours, edgecolor=INK_MUTED, linewidth=0.4, width=0.78)
    for bar, share in zip(bars, shares):
        ax.text(bar.get_x() + bar.get_width() / 2, share + 0.6, f"{share:.0f}%" if share >= 1 else "<1%",
                ha="center", va="bottom", fontsize=9, color=INK_SECONDARY)
    ax.set_ylabel("Share of land area (%)")
    ax.set_xlabel("Elevation band (m)")
    ax.set_ylim(0, max(shares) * 1.18)
    ax.grid(axis="y", color=GRID)
    _title(ax, "How high is Zambia?",
           "Share of the country's land area in each elevation band, measured on an equal-area grid")
    _source(fig, DATA_CREDIT)
    return _save(fig, path)
