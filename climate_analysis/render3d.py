"""Path-traced 3D terrain rendering with forge3d.

forge3d (https://github.com/milos-agathon/forge3d) places a heightmap with
column c, row r and height h at world (c - (W-1)/2, h, r - (H-1)/2): y is up
and row 0 (north) lies towards -z. The camera here sits to the south, tilted
down towards the centre, so north stays at the top of the image. The same
pinhole projection is used to place labels, rivers and lakes on the render.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# forge3d measures sun azimuth 90 degrees anticlockwise of a compass bearing.
SUN_AZIMUTH_OFFSET = 90.0


@dataclass(frozen=True)
class Camera:
    shape: tuple[int, int]      # heightmap rows, cols
    width: int                  # image pixels
    height: int
    tilt_deg: float = 50.0      # angle of the view above the horizon
    distance: float = 6.0       # camera distance, in heightmap spans
    zoom: float = 0.5           # half the vertical field of view, in heightmap spans
    target_y: float = 0.0       # height of the look-at point
    target_z: float = 0.0       # shift the look-at point north (-) or south (+)

    @property
    def span(self) -> float:
        return float(max(self.shape) - 1)

    @property
    def origin(self) -> np.ndarray:
        tilt, d = math.radians(self.tilt_deg), self.distance * self.span
        return np.array([0.0, self.target_y + d * math.sin(tilt), self.target_z + d * math.cos(tilt)])

    @property
    def look_at(self) -> np.ndarray:
        return np.array([0.0, self.target_y, self.target_z])

    @property
    def up(self) -> np.ndarray:
        tilt = math.radians(self.tilt_deg)
        return np.array([0.0, math.cos(tilt), -math.sin(tilt)])

    @property
    def fov_y_deg(self) -> float:
        return math.degrees(2.0 * math.atan(self.zoom / self.distance))

    def as_forge3d(self) -> dict:
        return {
            "model": "off_axis",
            "origin": tuple(self.origin),
            "look_at": tuple(self.look_at),
            "up": tuple(self.up),
            "fov_y": self.fov_y_deg,
        }

    def world(self, row, col, height) -> np.ndarray:
        """Heightmap coordinates (cell centres at integer + 0.5) -> world points."""
        rows, cols = self.shape
        return np.stack([np.asarray(col, dtype=float) - 0.5 - (cols - 1) / 2,
                         np.asarray(height, dtype=float),
                         np.asarray(row, dtype=float) - 0.5 - (rows - 1) / 2], axis=-1)

    def project(self, points: np.ndarray) -> np.ndarray:
        """World points (..., 3) -> image pixel coordinates (..., 2), origin top-left."""
        forward = self.look_at - self.origin
        forward /= np.linalg.norm(forward)
        right = np.cross(forward, self.up)
        right /= np.linalg.norm(right)
        up = np.cross(right, forward)
        rel = np.asarray(points, dtype=float) - self.origin
        depth = rel @ forward
        half = math.tan(math.radians(self.fov_y_deg) / 2)
        aspect = self.width / self.height
        x = (rel @ right) / depth / (half * aspect)
        y = (rel @ up) / depth / half
        return np.stack([(x * 0.5 + 0.5) * self.width - 0.5, (0.5 - y * 0.5) * self.height - 0.5], axis=-1)


def ground_footprint(camera: Camera, plane_y: float = 0.0) -> np.ndarray:
    """World (x, z) where the rays through the four image corners hit y = plane_y."""
    forward = camera.look_at - camera.origin
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, camera.up)
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    half = math.tan(math.radians(camera.fov_y_deg) / 2)
    aspect = camera.width / camera.height
    corners = []
    for sx, sy in ((-1, 1), (1, 1), (1, -1), (-1, -1)):
        ray = forward + right * sx * half * aspect + up * sy * half
        t = (plane_y - camera.origin[1]) / ray[1]
        hit = camera.origin + t * ray
        corners.append((hit[0], hit[2]))
    return np.array(corners)


def pad_to_frame(heights: np.ndarray, valid: np.ndarray, albedo: np.ndarray, camera: Camera,
                 margin: int = 8):
    """Pad the heightmap with flat, empty ground so it fills the whole frame.

    Where the plate ends the renderer shows its sky, which would otherwise be
    hard to tell apart from terrain when cutting the country out. Padding is
    symmetric so the plate stays centred on the camera's world origin.
    """
    from dataclasses import replace

    rows, cols = heights.shape
    corners = ground_footprint(camera)
    pad_c = max(0, int(math.ceil(np.abs(corners[:, 0]).max() - (cols - 1) / 2)) + margin)
    pad_r = max(0, int(math.ceil(np.abs(corners[:, 1]).max() - (rows - 1) / 2)) + margin)
    widths = ((pad_r, pad_r), (pad_c, pad_c))
    heights = np.pad(heights, widths, constant_values=0.0)
    valid = np.pad(valid, widths, constant_values=False)
    albedo = np.pad(albedo, (*widths, (0, 0)), constant_values=0.0)
    # distance and zoom are in heightmap spans: rescale so the view is unchanged
    ratio = camera.span / float(max(heights.shape) - 1)
    padded = replace(camera, shape=heights.shape, distance=camera.distance * ratio, zoom=camera.zoom * ratio)
    return heights, valid, albedo, padded, (pad_r, pad_c)


def fit_camera(camera: Camera, points: np.ndarray, fill_x: float = 0.9, fill_y: float = 0.9,
               centre_y: float = 0.5, iterations: int = 6) -> Camera:
    """Zoom and shift the camera so the points span at most ``fill_x`` of the image
    width and ``fill_y`` of its height, with their vertical centre at ``centre_y``."""
    from dataclasses import replace

    for _ in range(iterations):
        xy = camera.project(points)
        span_x = (xy[:, 0].max() - xy[:, 0].min()) / camera.width
        span_y = (xy[:, 1].max() - xy[:, 1].min()) / camera.height
        scale = max(span_x / fill_x, span_y / fill_y)
        mid_y = (xy[:, 1].max() + xy[:, 1].min()) / 2 / camera.height
        # moving the target north (-z) moves the content down the frame
        shift = (centre_y - mid_y) * 2 * camera.zoom * camera.span / math.sin(math.radians(camera.tilt_deg))
        camera = replace(camera, zoom=camera.zoom * scale, target_z=camera.target_z - shift)
    return camera


def heights_to_units(elevation: np.ndarray, resolution_m: float, exaggeration: float) -> np.ndarray:
    """Metres -> heightmap units, where one unit is one grid cell horizontally."""
    return (np.asarray(elevation, dtype=np.float32) / resolution_m * exaggeration).astype(np.float32)


def wall_ring(valid: np.ndarray, colours: np.ndarray, shade: float = 0.8):
    """Colour a one-cell ring outside the country with a darker copy of its nearest edge.

    The renderer interpolates colour across the vertical walls at the country's
    edge, so the ring turns them into shaded slab sides instead of black ones.
    Returns (cells that are drawn, colours).
    """
    from scipy.ndimage import binary_dilation, distance_transform_edt

    ring = binary_dilation(valid, structure=np.ones((3, 3), dtype=bool)) & ~valid
    _, (rows, cols) = distance_transform_edt(~valid, return_indices=True)
    out = colours.copy()
    out[ring] = colours[rows[ring], cols[ring]] * shade
    return valid | ring, out


def grade(rgb: np.ndarray, exposure: float = 1.12, saturation: float = 1.18) -> np.ndarray:
    """Gentle exposure and saturation lift for the rendered terrain (uint8 in, uint8 out)."""
    image = rgb.astype(float) / 255.0
    luminance = image @ np.array([0.2126, 0.7152, 0.0722])
    image = luminance[..., None] + (image - luminance[..., None]) * saturation
    return (np.clip(image * exposure, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def coverage(rgb: np.ndarray, threshold: int = 3) -> np.ndarray:
    """Pixels showing terrain, given a render where off-country albedo is pure black."""
    return np.asarray(rgb)[..., :3].max(axis=-1) > threshold


def render(heights: np.ndarray, albedo_srgb: np.ndarray, valid: np.ndarray, camera: Camera,
           sun_bearing_deg: float = 315.0, sun_elevation_deg: float = 38.0,
           sun_intensity: float = 3.6, env_intensity: float = 0.5,
           samples: int = 64, tile: int = 1024) -> np.ndarray:
    """Path-trace the terrain; returns the RGB image (uint8).

    ``samples`` is the number of path-traced samples per pixel.
    ``albedo_srgb`` is the surface colour (0..1, sRGB) and ``valid`` marks the
    cells that belong to the country. Everything else is rendered pure black,
    which ``coverage`` uses to cut the country out of the frame.
    """
    from forge3d.path_tracing import render_terrain_poster

    # forge3d 1.40 drops the last frame of long runs on some GPUs and then fails its own
    # frame-count check, so keep runs at 16 frames and take more samples per frame.
    frames = min(samples, 16)
    spp = max(1, round(samples / frames))

    albedo = np.zeros((*heights.shape, 4), dtype=np.float32)
    albedo[..., :3] = np.where(valid[..., None], np.clip(albedo_srgb, 0, 1) ** 2.2, 0.0)
    albedo[..., 3] = 1.0
    result = render_terrain_poster(
        np.ascontiguousarray(heights, dtype=np.float32), camera.width, camera.height,
        camera.as_forge3d(), tile=tile, albedo_map=albedo, albedo_sampling="bilinear",
        sun_azimuth_deg=(sun_bearing_deg - SUN_AZIMUTH_OFFSET) % 360.0,
        sun_elevation_deg=sun_elevation_deg, sun_intensity=sun_intensity, env_intensity=env_intensity,
        min_frames=frames, max_frames=frames, variance_threshold=1e9, seed=7, spp=spp,
    )
    return np.asarray(result["rgba"], dtype=np.uint8)[..., :3]
