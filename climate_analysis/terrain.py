"""Download and prepare public terrain data for a country.

Elevation comes from the Terrain Tiles open dataset on AWS (Mapzen "terrarium"
encoding), a global mosaic built from SRTM, GMTED2010 and ETOPO1. Country
borders come from geoBoundaries, and rivers, lakes and the locator map from
Natural Earth. Everything is reprojected to a Lambert azimuthal equal-area
grid centred on the country, so every cell covers the same ground area and
area shares are exact.
"""

from __future__ import annotations

import io
import json
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import requests
from PIL import Image

TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
GEOBOUNDARIES_API = "https://www.geoboundaries.org/api/current/gbOpen/{iso}/ADM0/"
NATURAL_EARTH_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
                     "master/geojson/{name}.geojson")
WEB_MERCATOR_HALF = 20037508.342789244
TILE_PIXELS = 256


@dataclass(frozen=True)
class Country:
    name: str
    iso: str
    bbox: tuple[float, float, float, float]  # west, south, east, north (degrees)
    centre: tuple[float, float]               # lon, lat of the projection centre

    @property
    def crs(self) -> str:
        lon, lat = self.centre
        return f"+proj=laea +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m +no_defs"


COUNTRIES = {
    "zambia": Country("Zambia", "ZMB", bbox=(21.9, -18.15, 33.8, -8.15), centre=(27.85, -13.15)),
}


@dataclass(frozen=True)
class Grid:
    """A north-up raster grid in projected metres."""

    west: float
    north: float
    resolution: float
    width: int
    height: int

    @property
    def transform(self):
        from rasterio.transform import from_origin

        return from_origin(self.west, self.north, self.resolution, self.resolution)

    @property
    def cell_km2(self) -> float:
        return (self.resolution / 1000.0) ** 2

    def to_pixel(self, x, y) -> tuple[np.ndarray, np.ndarray]:
        """Projected metres -> fractional (row, col), cell centres at integer + 0.5."""
        col = (np.asarray(x, dtype=float) - self.west) / self.resolution
        row = (self.north - np.asarray(y, dtype=float)) / self.resolution
        return row, col

    def to_xy(self, row, col) -> tuple[np.ndarray, np.ndarray]:
        x = self.west + np.asarray(col, dtype=float) * self.resolution
        y = self.north - np.asarray(row, dtype=float) * self.resolution
        return x, y


# ---------------------------------------------------------------- elevation tiles

def decode_terrarium(rgb: np.ndarray) -> np.ndarray:
    """Terrarium PNG pixels -> elevation in metres: R*256 + G + B/256 - 32768."""
    rgb = np.asarray(rgb, dtype=np.float32)
    return rgb[..., 0] * 256.0 + rgb[..., 1] + rgb[..., 2] / 256.0 - 32768.0


def lonlat_to_tile(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    """Fractional slippy-map tile coordinates of a point."""
    n = 2**zoom
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def tile_range(bbox: tuple[float, float, float, float], zoom: int) -> tuple[range, range]:
    """Tile columns and rows that cover a west/south/east/north box."""
    west, south, east, north = bbox
    x0, y0 = lonlat_to_tile(west, north, zoom)
    x1, y1 = lonlat_to_tile(east, south, zoom)
    return range(int(x0), int(x1) + 1), range(int(y0), int(y1) + 1)


def _fetch(url: str, path: Path, refresh: bool) -> Path:
    if path.exists() and not refresh:
        return path
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return path


def download_elevation(country: Country, zoom: int = 8, data_dir: Path | str = "data",
                       refresh: bool = False):
    """Mosaic terrarium tiles over the country; returns (elevation, Web Mercator transform)."""
    from rasterio.transform import from_origin

    cols, rows = tile_range(country.bbox, zoom)
    folder = Path(data_dir) / "terrain_tiles" / str(zoom)
    jobs = [(x, y) for y in rows for x in cols]

    def get(job):
        x, y = job
        return _fetch(TILE_URL.format(z=zoom, x=x, y=y), folder / f"{x}_{y}.png", refresh)

    with ThreadPoolExecutor(max_workers=8) as pool:
        paths = list(pool.map(get, jobs))

    mosaic = np.empty((len(rows) * TILE_PIXELS, len(cols) * TILE_PIXELS), dtype=np.float32)
    for (x, y), path in zip(jobs, paths):
        r, c = (y - rows.start) * TILE_PIXELS, (x - cols.start) * TILE_PIXELS
        rgb = np.asarray(Image.open(io.BytesIO(path.read_bytes())).convert("RGB"))
        mosaic[r:r + TILE_PIXELS, c:c + TILE_PIXELS] = decode_terrarium(rgb)

    tile_m = 2 * WEB_MERCATOR_HALF / 2**zoom
    transform = from_origin(-WEB_MERCATOR_HALF + cols.start * tile_m,
                            WEB_MERCATOR_HALF - rows.start * tile_m,
                            tile_m / TILE_PIXELS, tile_m / TILE_PIXELS)
    return mosaic, transform


# ---------------------------------------------------------------- vector layers

def download_boundary(country: Country, data_dir: Path | str = "data", refresh: bool = False) -> dict:
    """Country outline (GeoJSON geometry, lon/lat) from geoBoundaries gbOpen."""
    path = Path(data_dir) / f"geoboundaries_{country.iso}_adm0.geojson"
    if not path.exists() or refresh:
        meta = requests.get(GEOBOUNDARIES_API.format(iso=country.iso), timeout=60).json()
        _fetch(meta["gjDownloadURL"], path, refresh=True)
    return json.loads(path.read_text(encoding="utf-8"))["features"][0]["geometry"]


def download_natural_earth(name: str, data_dir: Path | str = "data", refresh: bool = False) -> list[dict]:
    """Features of one Natural Earth GeoJSON layer, e.g. ``ne_10m_lakes``."""
    path = _fetch(NATURAL_EARTH_URL.format(name=name), Path(data_dir) / "natural_earth" / f"{name}.geojson",
                  refresh)
    return json.loads(path.read_text(encoding="utf-8"))["features"]


def geometry_bbox(geometry: dict) -> tuple[float, float, float, float] | None:
    coords = np.asarray([xy[:2] for xy in _iter_coords(geometry["coordinates"])], dtype=float)
    if coords.size == 0:
        return None
    return coords[:, 0].min(), coords[:, 1].min(), coords[:, 0].max(), coords[:, 1].max()


def _iter_coords(coords):
    if coords and isinstance(coords[0], (int, float)):
        yield coords
    else:
        for item in coords:
            yield from _iter_coords(item)


def features_in_bbox(features: list[dict], bbox: tuple[float, float, float, float]) -> list[dict]:
    west, south, east, north = bbox
    kept = []
    for feature in features:
        box = geometry_bbox(feature["geometry"]) if feature.get("geometry") else None
        if box is None:
            continue
        fw, fs, fe, fn = box
        if fe >= west and fw <= east and fn >= south and fs <= north:
            kept.append(feature)
    return kept


# ---------------------------------------------------------------- projected grid

def equal_area_grid(country: Country, boundary: dict, resolution: float, margin: float = 20_000) -> Grid:
    """Grid covering the projected country outline plus a margin."""
    from rasterio.warp import transform_geom

    projected = transform_geom("EPSG:4326", country.crs, boundary)
    west, south, east, north = geometry_bbox(projected)
    west, north = west - margin, north + margin
    width = int(math.ceil((east + margin - west) / resolution))
    height = int(math.ceil((north - (south - margin)) / resolution))
    return Grid(west, north, resolution, width, height)


def reproject_elevation(mosaic: np.ndarray, src_transform, country: Country, grid: Grid) -> np.ndarray:
    from rasterio.warp import Resampling, reproject

    out = np.zeros((grid.height, grid.width), dtype=np.float32)
    reproject(mosaic, out, src_transform=src_transform, src_crs="EPSG:3857",
              dst_transform=grid.transform, dst_crs=country.crs, resampling=Resampling.bilinear)
    return out


def rasterize_mask(geometry: dict, country: Country, grid: Grid) -> np.ndarray:
    from rasterio.features import rasterize
    from rasterio.warp import transform_geom

    projected = transform_geom("EPSG:4326", country.crs, geometry)
    return rasterize([(projected, 1)], out_shape=(grid.height, grid.width),
                     transform=grid.transform, fill=0, dtype="uint8").astype(bool)


def project_lonlat(country: Country, lon, lat) -> tuple[np.ndarray, np.ndarray]:
    from rasterio.warp import transform

    x, y = transform("EPSG:4326", country.crs, list(np.atleast_1d(lon)), list(np.atleast_1d(lat)))
    return np.asarray(x), np.asarray(y)


def unproject(country: Country, x, y) -> tuple[np.ndarray, np.ndarray]:
    from rasterio.warp import transform

    lon, lat = transform(country.crs, "EPSG:4326", list(np.atleast_1d(x)), list(np.atleast_1d(y)))
    return np.asarray(lon), np.asarray(lat)


def despike(elevation: np.ndarray, size: int = 5, floor: float = 40.0, k: float = 4.0) -> np.ndarray:
    """Replace isolated spikes, pits and stripe artefacts with the local median.

    A cell is an artefact when it departs from the median of its neighbourhood
    by more than ``max(floor, k * local MAD)``. The local median absolute
    deviation is large on genuine escarpments, so real relief is kept, while
    one- to three-cell glitches on flat ground are removed.
    """
    from scipy.ndimage import median_filter

    median = median_filter(elevation, size=size, mode="nearest")
    deviation = np.abs(elevation - median)
    spread = median_filter(deviation, size=size + 2, mode="nearest")
    artefact = deviation > np.maximum(floor, k * spread)
    return np.where(artefact, median, elevation).astype(np.float32)


def block_mean(array: np.ndarray, factor: int) -> np.ndarray:
    """Downsample by averaging factor x factor blocks (edges trimmed)."""
    h, w = (array.shape[0] // factor) * factor, (array.shape[1] // factor) * factor
    trimmed = array[:h, :w]
    return trimmed.reshape(h // factor, factor, w // factor, factor, *array.shape[2:]).mean(axis=(1, 3))


# ---------------------------------------------------------------- colour and statistics

# Hypsometric tints tuned for a low-relief plateau: greens in the rift valleys,
# straw and tan across the 1,000-1,400 m plateau, warm browns on the escarpments.
HYPSOMETRIC_STOPS = (
    (300, "#1f5a46"),
    (550, "#3f7a52"),
    (800, "#7d9c5e"),
    (1000, "#b5b578"),
    (1150, "#d9cc94"),
    (1300, "#e6cf9e"),
    (1450, "#d4a877"),
    (1650, "#b5835c"),
    (1900, "#8f6450"),
    (2300, "#f1ebe3"),
)


def _hex_rgb(value: str) -> tuple[float, float, float]:
    return tuple(int(value[i:i + 2], 16) / 255.0 for i in (1, 3, 5))


def hypsometric_rgb(elevation: np.ndarray, stops=HYPSOMETRIC_STOPS) -> np.ndarray:
    """Elevation (m) -> sRGB colour in 0..1, linear interpolation between stops."""
    heights = np.array([h for h, _ in stops], dtype=float)
    colours = np.array([_hex_rgb(c) for _, c in stops])
    elevation = np.asarray(elevation, dtype=float)
    return np.stack([np.interp(elevation, heights, colours[:, i]) for i in range(3)], axis=-1)


def elevation_stats(elevation: np.ndarray, mask: np.ndarray, grid: Grid) -> dict:
    values = elevation[mask]
    rows, cols = np.nonzero(mask)
    low, high = np.argmin(values), np.argmax(values)
    return {
        "area_km2": float(mask.sum() * grid.cell_km2),
        "min": float(values[low]),
        "max": float(values[high]),
        "mean": float(values.mean()),
        "median": float(np.median(values)),
        "lowest_rc": (int(rows[low]), int(cols[low])),
        "highest_rc": (int(rows[high]), int(cols[high])),
        "share_above_1000": float((values >= 1000).mean() * 100),
        "share_above_1200": float((values >= 1200).mean() * 100),
        "share_below_600": float((values < 600).mean() * 100),
    }


def area_by_band(elevation: np.ndarray, mask: np.ndarray, edges) -> np.ndarray:
    """Percentage of the masked area falling in each [edges[i], edges[i+1]) band."""
    values = elevation[mask]
    counts, _ = np.histogram(values, bins=np.asarray(edges, dtype=float))
    return counts / values.size * 100.0


def bilinear(array: np.ndarray, row, col) -> np.ndarray:
    """Sample at fractional (row, col) with cell centres at integer + 0.5."""
    r = np.clip(np.asarray(row, dtype=float) - 0.5, 0, array.shape[0] - 1.001)
    c = np.clip(np.asarray(col, dtype=float) - 0.5, 0, array.shape[1] - 1.001)
    r0, c0 = np.floor(r).astype(int), np.floor(c).astype(int)
    fr, fc = r - r0, c - c0
    top = array[r0, c0] * (1 - fc) + array[r0, c0 + 1] * fc
    bottom = array[r0 + 1, c0] * (1 - fc) + array[r0 + 1, c0 + 1] * fc
    return top * (1 - fr) + bottom * fr


def profile(elevation: np.ndarray, grid: Grid, start_xy, end_xy, samples: int = 600):
    """Straight-line elevation profile; returns (distance_km, elevation_m)."""
    t = np.linspace(0.0, 1.0, samples)
    x = start_xy[0] + (end_xy[0] - start_xy[0]) * t
    y = start_xy[1] + (end_xy[1] - start_xy[1]) * t
    row, col = grid.to_pixel(x, y)
    distance = np.hypot(x - x[0], y - y[0]) / 1000.0
    return distance, bilinear(elevation, row, col)
