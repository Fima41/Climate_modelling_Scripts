import math

import numpy as np
import pytest

from climate_analysis import render3d, terrain, terrain_plots


def test_decode_terrarium_known_values():
    rgb = np.array([[[128, 0, 0], [128, 1, 128], [129, 44, 0]]], dtype=np.uint8)

    assert np.allclose(terrain.decode_terrarium(rgb), [[0.0, 1.5, 300.0]])


def test_tile_coordinates_and_range():
    assert terrain.lonlat_to_tile(0.0, 0.0, 1) == pytest.approx((1.0, 1.0))

    cols, rows = terrain.tile_range((-1.0, -1.0, 1.0, 1.0), zoom=2)

    assert list(cols) == [1, 2] and list(rows) == [1, 2]


def test_grid_pixel_round_trip():
    grid = terrain.Grid(west=1000.0, north=5000.0, resolution=100.0, width=10, height=8)

    row, col = grid.to_pixel(*grid.to_xy(2.5, 7.25))

    assert row == pytest.approx(2.5) and col == pytest.approx(7.25)
    assert grid.cell_km2 == pytest.approx(0.01)


def test_hypsometric_colours_hit_stops_and_clip():
    first, last = terrain.HYPSOMETRIC_STOPS[0], terrain.HYPSOMETRIC_STOPS[-1]
    colours = terrain.hypsometric_rgb(np.array([first[0], last[0], -500.0, 9000.0]))

    assert np.allclose(colours[0], terrain._hex_rgb(first[1]))
    assert np.allclose(colours[1], terrain._hex_rgb(last[1]))
    assert np.allclose(colours[2], colours[0]) and np.allclose(colours[3], colours[1])


def test_despike_removes_glitches_but_keeps_escarpments():
    flat = np.full((30, 30), 1000.0, dtype=np.float32)
    flat[10, 10] = 1400.0                      # isolated spike
    flat[20, 5:25] = 920.0                     # one-row stripe artefact
    flat[:, 25:] = 400.0                       # genuine 600 m escarpment

    cleaned = terrain.despike(flat)

    assert cleaned[10, 10] == pytest.approx(1000.0)
    assert np.allclose(cleaned[20, 8:22], 1000.0)
    assert np.allclose(cleaned[:, 26:], 400.0) and np.allclose(cleaned[:, :9], 1000.0)


def test_area_by_band_sums_to_100():
    elevation = np.array([[350, 650, 950], [1050, 1150, 1250]], dtype=float)
    mask = np.ones_like(elevation, dtype=bool)

    shares = terrain.area_by_band(elevation, mask, [300, 600, 900, 1000, 1100, 1200, 1300])

    assert shares.sum() == pytest.approx(100.0)
    assert np.allclose(shares, 100 / 6)


def test_elevation_stats_on_synthetic_grid():
    grid = terrain.Grid(0.0, 0.0, 1000.0, 3, 2)
    elevation = np.array([[500.0, 1500.0, 9999.0], [1100.0, 900.0, 1200.0]])
    mask = np.array([[True, True, False], [True, True, True]])

    stats = terrain.elevation_stats(elevation, mask, grid)

    assert stats["area_km2"] == pytest.approx(5.0)
    assert (stats["min"], stats["max"]) == (500.0, 1500.0)
    assert stats["lowest_rc"] == (0, 0) and stats["highest_rc"] == (0, 1)
    assert stats["share_above_1000"] == pytest.approx(60.0)


def test_bilinear_and_profile_on_a_ramp():
    grid = terrain.Grid(west=0.0, north=0.0, resolution=1000.0, width=50, height=20)
    elevation = np.tile(np.arange(50, dtype=float) * 10.0, (20, 1))  # rises 10 m per km eastward

    distance, section = terrain.profile(elevation, grid, (5_500.0, -10_000.0), (35_500.0, -10_000.0), samples=31)

    assert distance[-1] == pytest.approx(30.0)
    assert np.allclose(section, 50.0 + distance * 10.0)


def test_heights_to_units():
    units = render3d.heights_to_units(np.array([0.0, 1200.0]), resolution_m=1200.0, exaggeration=25.0)

    assert np.allclose(units, [0.0, 25.0])


@pytest.fixture
def camera():
    return render3d.Camera(shape=(101, 201), width=400, height=300, tilt_deg=45.0)


def test_camera_projects_target_to_centre_and_keeps_north_up(camera):
    centre = camera.project(camera.look_at[None, :])[0]
    north = camera.project(camera.world(10.5, 100.5, 0.0)[None, :])[0]
    east = camera.project(camera.world(50.5, 190.5, 0.0)[None, :])[0]

    assert centre == pytest.approx((199.5, 149.5))
    assert north[1] < centre[1]
    assert east[0] > centre[0]


def test_camera_matches_forge3d_convention():
    # Pixel positions measured on a forge3d render of marked cells (see render3d docstring).
    tilt_from_vertical = math.radians(50)
    cam = render3d.Camera(shape=(101, 201), width=400, height=300, tilt_deg=40.0, distance=6.0, zoom=0.4)
    points = cam.world(np.array([10.5, 80.5, 50.5]), np.array([20.5, 40.5, 150.5]), np.zeros(3))

    xy = cam.project(points)

    assert cam.fov_y_deg == pytest.approx(math.degrees(2 * math.atan(0.4 / 6.0)))
    assert math.radians(90 - cam.tilt_deg) == pytest.approx(tilt_from_vertical)
    assert np.allclose(xy, [[53.3, 102.4], [84.9, 186.6], [292.0, 149.5]], atol=2.0)


def test_fit_camera_fills_requested_fraction(camera):
    points = camera.world(np.array([0.5, 0.5, 100.5, 100.5]), np.array([0.5, 200.5, 0.5, 200.5]), np.zeros(4))

    fitted = render3d.fit_camera(camera, points, fill_x=0.8, fill_y=0.8, centre_y=0.5)
    xy = fitted.project(points)

    span_x = (xy[:, 0].max() - xy[:, 0].min()) / camera.width
    span_y = (xy[:, 1].max() - xy[:, 1].min()) / camera.height
    assert max(span_x / 0.8, span_y / 0.8) == pytest.approx(1.0, abs=0.01)
    assert (xy[:, 1].max() + xy[:, 1].min()) / 2 / camera.height == pytest.approx(0.5, abs=0.01)


def test_ground_footprint_projects_back_to_image_corners(camera):
    corners = render3d.ground_footprint(camera)
    points = np.column_stack([corners[:, 0], np.zeros(4), corners[:, 1]])

    xy = camera.project(points)

    assert np.allclose(xy, [[-0.5, -0.5], [399.5, -0.5], [399.5, 299.5], [-0.5, 299.5]], atol=1e-6)


def test_pad_to_frame_keeps_the_view(camera):
    heights = np.zeros(camera.shape, dtype=np.float32)
    valid = np.ones(camera.shape, dtype=bool)
    albedo = np.ones((*camera.shape, 3))
    point = camera.world(50.5, 100.5, 3.0)

    padded_h, padded_v, _, padded_cam, (pr, pc) = render3d.pad_to_frame(heights, valid, albedo, camera)

    moved = padded_cam.world(50.5 + pr, 100.5 + pc, 3.0)
    assert np.allclose(padded_cam.project(moved[None])[0], camera.project(point[None])[0], atol=1e-6)
    assert np.abs(render3d.ground_footprint(padded_cam)[:, 0]).max() <= (padded_h.shape[1] - 1) / 2
    assert padded_v.sum() == valid.sum()


def test_wall_ring_shades_nearest_edge_colour():
    valid = np.zeros((5, 5), dtype=bool)
    valid[2, 2] = True
    colours = np.zeros((5, 5, 3))
    colours[2, 2] = (0.8, 0.6, 0.4)

    drawn, out = render3d.wall_ring(valid, colours, shade=0.5)

    assert drawn.sum() == 9
    assert np.allclose(out[1, 2], (0.4, 0.3, 0.2))
    assert np.allclose(out[0, 0], 0.0)


def test_grade_keeps_black_and_lifts_grey():
    rgb = np.array([[[0, 0, 0], [100, 100, 100]]], dtype=np.uint8)

    graded = render3d.grade(rgb, exposure=1.2, saturation=1.5)

    assert graded[0, 0].tolist() == [0, 0, 0]
    assert graded[0, 1].tolist() == [120, 120, 120]


def test_premultiplied_alpha_interior_edge_and_empty():
    rgb = np.zeros((9, 9, 3), dtype=np.uint8)
    rgb[2:7, 2:7] = 200
    rgb[2:7, 7] = 100                          # half-covered edge column

    alpha = terrain_plots.premultiplied_alpha(rgb, render3d.coverage(rgb))

    assert alpha[4, 4] == 1.0
    assert alpha[4, 7] == pytest.approx(0.5)
    assert alpha[0, 0] == 0.0
