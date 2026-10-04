"""Map a country's terrain in 3D and measure how its land is distributed by height.

Builds an equal-area elevation grid from public data, computes elevation
statistics and a cross-section, and path-traces a 3D poster with forge3d.

Usage:
    python -m climate_analysis.terrain_3d --country zambia
    python -m climate_analysis.terrain_3d --country zambia --size 1600 --samples 16  # quick preview
    python -m climate_analysis.terrain_3d --country zambia --no-render               # statistics only
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np

from . import render3d, terrain, terrain_plots
from .terrain_plots import Label

RESOLUTION = 600         # analysis grid spacing (m)
RENDER_FACTOR = 2        # render grid = analysis grid averaged in 2 x 2 blocks (1.2 km)
EXAGGERATION = 25.0
BAND_EDGES = [300, 600, 900, 1000, 1100, 1200, 1300, 1400, 1600, 2400]

PLACES = {  # lon, lat
    "Lusaka": (28.2833, -15.4167),
    "Ndola": (28.6366, -12.9587),
    "Kitwe": (28.2132, -12.8024),
    "Kabwe": (28.4464, -14.4469),
    "Livingstone": (25.8544, -17.8419),
    "Chipata": (32.6447, -13.6333),
    "Kasama": (31.1800, -10.2129),
    "Mongu": (23.1333, -15.2833),
    "Solwezi": (26.3833, -12.1833),
    "Mansa": (28.8941, -11.1999),
}

LABELS = [
    Label("Lusaka", *PLACES["Lusaka"], kind="capital", dx=8, dy=-7),
    Label("Kabwe", *PLACES["Kabwe"], dx=7, dy=3),
    Label("Ndola", *PLACES["Ndola"], dx=7, dy=-4),
    Label("Kitwe", *PLACES["Kitwe"], dx=-7, dy=5, ha="right"),
    Label("Livingstone", *PLACES["Livingstone"], dx=-6, dy=8, ha="right"),
    Label("Chipata", *PLACES["Chipata"], dx=-7, dy=-7, ha="right"),
    Label("Kasama", *PLACES["Kasama"], dx=7, dy=4),
    Label("Mongu", *PLACES["Mongu"], dx=7, dy=4),
    Label("Solwezi", *PLACES["Solwezi"], dx=7, dy=4),
    Label("Mansa", *PLACES["Mansa"], dx=7, dy=4),
    Label("Victoria Falls", 25.857, -17.924, kind="waterpoint", dx=8, dy=-3),
    Label("Luangwa Valley", 31.75, -12.75, kind="relief", ha="center", dx=0, dy=0, rotation=38),
    Label("Muchinga Escarpment", 30.65, -12.45, kind="relief", ha="center", dx=0, dy=0, rotation=34),
    Label("Mafinga Hills", 33.30, -9.95, kind="relief", ha="right", dx=-8, dy=6),
    Label("Barotse Floodplain", 23.05, -16.05, kind="relief", ha="center", dx=0, dy=0),
    Label("Kafue Flats", 27.25, -15.75, kind="relief", ha="center", dx=0, dy=0),
    Label("Lake Kariba", 27.75, -16.95, kind="water", dx=10, dy=-10),
    Label("Lake Bangweulu", 29.85, -11.10, kind="water", dx=12, dy=0),
    Label("Lake Mweru", 28.80, -9.05, kind="water", dx=-10, dy=0, ha="right"),
    Label("Lake Tanganyika", 31.10, -8.62, kind="water", dx=8, dy=4),
    Label("Zambezi", 23.30, -13.70, kind="water", ha="center", dx=-10, dy=0, rotation=-80),
    Label("Kafue", 26.60, -14.20, kind="water", ha="center", dx=0, dy=0, rotation=60),
    Label("Angola", 22.60, -11.30, kind="country", ha="center", dx=0, dy=0),
    Label("DR Congo", 25.40, -9.70, kind="country", ha="center", dx=0, dy=0),
    Label("Tanzania", 32.70, -8.25, kind="country", ha="center", dx=0, dy=0),
    Label("Malawi", 34.05, -12.20, kind="country", ha="center", dx=0, dy=0),
    Label("Mozambique", 32.10, -15.75, kind="country", ha="center", dx=0, dy=0),
    Label("Zimbabwe", 29.20, -17.70, kind="country", ha="center", dx=0, dy=0),
    Label("Namibia", 23.70, -18.05, kind="country", ha="center", dx=0, dy=0),
]

RIVER_WIDTH = {3: 1.7, 6: 1.25, 7: 1.0, 8: 0.85, 9: 0.7}
PROFILE = ("Mongu", "Chipata")


def _dms(lon: float, lat: float) -> str:
    return f"{abs(lat):.2f}° {'S' if lat < 0 else 'N'}, {abs(lon):.2f}° {'W' if lon < 0 else 'E'}"


def _within(country: terrain.Country, lon: float, lat: float) -> bool:
    west, south, east, north = country.bbox
    return west - 2 <= lon <= east + 2 and south - 2 <= lat <= north + 2


def load(country: terrain.Country, data_dir: Path, refresh: bool):
    boundary = terrain.download_boundary(country, data_dir, refresh)
    mosaic, transform = terrain.download_elevation(country, zoom=8, data_dir=data_dir, refresh=refresh)
    grid = terrain.equal_area_grid(country, boundary, RESOLUTION)
    elevation = terrain.reproject_elevation(mosaic, transform, country, grid)
    elevation = terrain.despike(terrain.despike(elevation), floor=25.0)
    mask = terrain.rasterize_mask(boundary, country, grid)
    return boundary, grid, elevation, mask


class TerrainScene:
    """The country's terrain as a fixed 3D scene that any surface colouring can be draped over.

    Heights, camera and padding are prepared once; ``render`` then path-traces the
    terrain with a colour field defined on the analysis grid, and ``project`` maps
    lon/lat points onto the image for overlays.
    """

    def __init__(self, country, grid, elevation, mask, width: int, height: int,
                 factor: int = RENDER_FACTOR, tilt_deg: float = 48.0, fill_x: float = 0.84,
                 fill_y: float = 0.92, centre_y: float = 0.49):
        from scipy.ndimage import binary_dilation, grey_dilation

        self.country, self.grid, self.factor = country, grid, factor
        elev = terrain.block_mean(elevation, factor)
        valid = terrain.block_mean(mask.astype(np.float32), factor) > 0.5
        base = float(elev[valid].min()) - 250.0
        heights = render3d.heights_to_units(np.where(valid, elev, base) - base,
                                            RESOLUTION * factor, EXAGGERATION)
        camera = render3d.Camera(heights.shape, width, height, tilt_deg=tilt_deg,
                                 target_y=float(heights[valid].mean()))
        rows, cols = np.nonzero(valid)
        pick = slice(None, None, max(1, len(rows) // 20000))
        outline = camera.world(rows[pick] + 0.5, cols[pick] + 0.5, heights[rows[pick], cols[pick]])
        camera = render3d.fit_camera(camera, outline, fill_x=fill_x, fill_y=fill_y, centre_y=centre_y)
        self.heights, self.valid, _, self.camera, self.pads = render3d.pad_to_frame(
            heights, valid, np.zeros((*heights.shape, 3)), camera)
        # Border rivers in Natural Earth run up to a few km outside the country edge and
        # would slide down the slab walls, so overlays are draped on the highest terrain
        # within three cells and river sections further out than that are dropped.
        self.surface = grey_dilation(self.heights, size=7)
        self.near = binary_dilation(self.valid, iterations=3)

    def render(self, colours: np.ndarray, samples: int = 64) -> tuple[np.ndarray, np.ndarray]:
        """Path-trace with ``colours`` (sRGB 0..1 on the analysis grid); returns (rgb, alpha)."""
        small = terrain.block_mean(colours, self.factor)
        pr, pc = self.pads
        small = np.pad(small, ((pr, pr), (pc, pc), (0, 0)))
        drawn, small = render3d.wall_ring(self.valid, small)
        started = time.perf_counter()
        rgb = render3d.render(self.heights, small, drawn, self.camera, samples=samples)
        print(f"Rendered {self.camera.width}x{self.camera.height} from a "
              f"{self.heights.shape[1]}x{self.heights.shape[0]} heightmap in {time.perf_counter() - started:.0f} s")
        alpha = terrain_plots.premultiplied_alpha(rgb, render3d.coverage(rgb))
        return render3d.grade(rgb), alpha

    def to_render_grid(self, lon, lat):
        row, col = self.grid.to_pixel(*terrain.project_lonlat(self.country, lon, lat))
        return row / self.factor + self.pads[0], col / self.factor + self.pads[1]

    def near_runs(self, coords: np.ndarray) -> list[np.ndarray]:
        """Split a lon/lat polyline into the runs that lie on or next to the country."""
        row, col = self.to_render_grid(coords[:, 0], coords[:, 1])
        r = np.clip(row.astype(int), 0, self.near.shape[0] - 1)
        c = np.clip(col.astype(int), 0, self.near.shape[1] - 1)
        keep = self.near[r, c]
        edges = np.flatnonzero(np.diff(np.r_[0, keep.astype(int), 0]))
        return [coords[a:b] for a, b in zip(edges[::2], edges[1::2]) if b - a > 1]

    def project(self, lon, lat, on_terrain: bool = True) -> np.ndarray:
        row, col = self.to_render_grid(lon, lat)
        h = terrain.bilinear(self.surface, row, col) if on_terrain else np.zeros_like(row)
        return self.camera.project(self.camera.world(row, col, h))


def render_poster(country, boundary, grid, elevation, mask, stats, data_dir, refresh, path: Path,
                  size: int, samples: int) -> Path:
    width, height = terrain_plots.map_size(size)
    scene = TerrainScene(country, grid, elevation, mask, width, height)
    rgb, alpha = scene.render(terrain.hypsometric_rgb(elevation), samples)
    project, near_runs = scene.project, scene.near_runs

    rivers = terrain.features_in_bbox(
        terrain.download_natural_earth("ne_10m_rivers_lake_centerlines", data_dir, refresh), country.bbox)
    lakes = terrain.features_in_bbox(terrain.download_natural_earth("ne_10m_lakes", data_dir, refresh),
                                     country.bbox)
    lines = []
    for feature in rivers:
        width_pt = RIVER_WIDTH.get(int(feature["properties"].get("scalerank") or 9), 0.7)
        geometry = feature["geometry"]
        parts = geometry["coordinates"] if geometry["type"] == "MultiLineString" else [geometry["coordinates"]]
        lines += [(run, width_pt) for part in parts if len(part) > 1
                  for run in near_runs(np.asarray(part)[:, :2])]
    rings = [ring for feature in lakes for ring in terrain_plots._rings(feature["geometry"])]

    africa = [f for f in terrain.download_natural_earth("ne_50m_admin_0_countries", data_dir, refresh)
              if f["properties"].get("CONTINENT") == "Africa"]
    labels = [label for label in LABELS if _within(country, label.lon, label.lat)]
    return terrain_plots.terrain_poster(rgb, alpha, project, lines, rings, labels, stats, africa,
                                        boundary, path, exaggeration=EXAGGERATION)


def analyse(country_key: str, data_dir: Path, out_dir: Path, refresh: bool = False,
            size: int = 3200, samples: int = 64, render: bool = True) -> str:
    country = terrain.COUNTRIES[country_key]
    boundary, grid, elevation, mask = load(country, data_dir, refresh)
    stats = terrain.elevation_stats(elevation, mask, grid)
    shares = terrain.area_by_band(elevation, mask, BAND_EDGES)

    def lonlat(rc):
        x, y = grid.to_xy(rc[0] + 0.5, rc[1] + 0.5)
        lon, lat = terrain.unproject(country, x, y)
        return float(lon[0]), float(lat[0])

    low_ll, high_ll = lonlat(stats["lowest_rc"]), lonlat(stats["highest_rc"])
    place_elev = {}
    for name, (lon, lat) in PLACES.items():
        row, col = grid.to_pixel(*terrain.project_lonlat(country, lon, lat))
        place_elev[name] = float(terrain.bilinear(elevation, row, col)[0])

    start = terrain.project_lonlat(country, *PLACES[PROFILE[0]])
    end = terrain.project_lonlat(country, *PLACES[PROFILE[1]])
    distance, section = terrain.profile(elevation, grid, (start[0][0], start[1][0]), (end[0][0], end[1][0]))
    t = distance / distance[-1]
    row, col = grid.to_pixel(start[0][0] + (end[0][0] - start[0][0]) * t, start[1][0] + (end[1][0] - start[1][0]) * t)
    inside = mask[np.clip(row.astype(int), 0, grid.height - 1), np.clip(col.astype(int), 0, grid.width - 1)]
    east = distance > distance[-1] * 0.7
    luangwa = distance[east][np.argmin(section[east])]
    rim = (distance > luangwa - 60) & (distance < luangwa)
    muchinga = distance[rim][np.argmax(section[rim])]
    valley_low, valley_rim = float(section[east].min()), float(section[rim].max())
    kabwe_x, kabwe_y = terrain.project_lonlat(country, *PLACES["Kabwe"])
    along = ((kabwe_x[0] - start[0][0]) * (end[0][0] - start[0][0]) +
             (kabwe_y[0] - start[1][0]) * (end[1][0] - start[1][0])) / (distance[-1] * 1000.0) / 1000.0
    marks = [(distance[0] + 18, PROFILE[0]), (along, "near Kabwe"), (muchinga, "Muchinga Escarpment"),
             (luangwa + 32, "Luangwa Valley"), (distance[-1] - 18, PROFILE[1])]
    plateau_median = float(np.median(section[inside & (distance < distance[-1] * 0.7)]))

    folder = out_dir / country_key
    figures = [
        terrain_plots.elevation_bands(BAND_EDGES, shares, folder / "figures" / "elevation_bands.png"),
        terrain_plots.elevation_profile(
            distance, section, inside, marks, f"A cross-section of {country.name}, {PROFILE[0]} to {PROFILE[1]}",
            f"Across {distance[-1]:,.0f} km the plateau holds near {plateau_median:,.0f} m, until the Luangwa "
            f"rift drops {valley_rim - valley_low:,.0f} m from the Muchinga Escarpment to the valley floor",
            folder / "figures" / "elevation_profile.png"),
    ]
    if render:
        poster = render_poster(country, boundary, grid, elevation, mask, stats, data_dir, refresh,
                               folder / "figures" / f"{country_key}_terrain_3d.png", size, samples)
        figures.insert(0, poster)

    plateau = shares[BAND_EDGES.index(1000):BAND_EDGES.index(1400)].sum()
    lines = [
        f"# The terrain of {country.name}",
        "",
        "Source: Terrain Tiles on AWS (Mapzen terrarium encoding; SRTM, GMTED2010 and ETOPO1), "
        f"reprojected to a {RESOLUTION} m Lambert azimuthal equal-area grid. Country outline from "
        "geoBoundaries (gbOpen, CC BY 4.0); rivers, lakes and the locator map from Natural Earth.",
        "",
        "## Key insights",
        "",
        f"- **{country.name} is a high plateau.** {stats['share_above_1000']:.0f}% of its "
        f"{stats['area_km2']:,.0f} km² lies above 1,000 m, and the median height is "
        f"{stats['median']:,.0f} m. {plateau:.0f}% of the land sits in the 1,000–1,400 m band alone.",
        f"- **Highest ground: {stats['max']:,.0f} m** in the Mafinga Hills on the Malawi border "
        f"({_dms(*high_ll)}). The surveyed summit is 2,339 m; the ~600 m grid "
        "smooths the peak.",
        f"- **Lowest ground: {stats['min']:,.0f} m** where the Luangwa joins the Zambezi "
        f"({_dms(*low_ll)}). Only {stats['share_below_600']:.0f}% of the country "
        "lies below 600 m, all of it in the Luangwa and middle Zambezi rift valleys.",
        f"- **The Luangwa rift** drops about {valley_rim - valley_low:,.0f} m on the "
        f"{PROFILE[0]}–{PROFILE[1]} cross-section, from {valley_rim:,.0f} m on the crest of the Muchinga "
        f"Escarpment down to {valley_low:,.0f} m on the valley floor, within about "
        f"{luangwa - muchinga:,.0f} km.",
        f"- **Lusaka sits at about {place_elev['Lusaka']:,.0f} m**, which helps explain why the capital is "
        "cooler than its latitude would suggest.",
        "",
        "## Area by elevation band",
        "",
        "| Elevation (m) | Share of land area |",
        "|---|---:|",
        *[f"| {lo:,}–{hi:,} | {s:.1f}% |" for lo, hi, s in zip(BAND_EDGES[:-1], BAND_EDGES[1:], shares)],
        "",
        "## Elevation of major towns",
        "",
        "| Town | Elevation (m) |",
        "|---|---:|",
        *[f"| {name} | {value:,.0f} |" for name, value in sorted(place_elev.items(), key=lambda kv: -kv[1])],
        "",
        "## Method",
        "",
        "- Terrarium tiles at zoom 8 (about 600 m per pixel at this latitude) are mosaicked and "
        "reprojected with bilinear resampling to an equal-area grid, so every cell covers the same ground "
        "area and area shares are exact.",
        "- Isolated spikes, pits and stripe artefacts in the source mosaic are replaced with the local "
        "median when they depart from it by more than four times the local median absolute deviation "
        "(1% of cells). Genuine escarpments have a large local spread and are kept.",
        f"- The 3D view averages the grid to {RESOLUTION * RENDER_FACTOR / 1000:.1f} km cells, exaggerates "
        f"heights {EXAGGERATION:.0f}×, and is path-traced on the GPU with "
        "[forge3d](https://github.com/milos-agathon/forge3d) using a low north-west sun. Rivers, lakes and "
        "labels are projected onto the render with the same camera model.",
        "",
        "## Limitations",
        "",
        "- SRTM is a surface model: dense forest canopy can add a few metres, and summits are smoothed by "
        "the grid spacing.",
        "- Town elevations are sampled at the town centre on the 600 m grid, so they are approximate.",
        "- Rivers and lakes come from Natural Earth at 1:10 million scale and are generalised.",
        "",
        "## Figures",
        "",
        *[f"![{fig.stem}](figures/{fig.name})" for fig in figures],
        "",
    ]
    summary = "\n".join(lines)
    (folder / "summary.md").write_text(summary, encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--country", choices=list(terrain.COUNTRIES), default="zambia")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--out-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--size", type=int, default=3200, help="poster width in pixels")
    parser.add_argument("--samples", type=int, default=64, help="path-traced samples per pixel")
    parser.add_argument("--no-render", action="store_true", help="skip the GPU render")
    parser.add_argument("--refresh", action="store_true",
                        help="re-download the data instead of using the cache")
    args = parser.parse_args(argv)
    print(analyse(args.country, args.data_dir, args.out_dir, args.refresh,
                  size=args.size, samples=args.samples, render=not args.no_render))


if __name__ == "__main__":
    main()
