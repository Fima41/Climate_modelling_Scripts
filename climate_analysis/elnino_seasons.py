"""Map rainfall and temperature in Zambia's rainy season (October–March) during El Niño.

Uses ERA5 monthly means downloaded from the Copernicus Climate Data Store and
compares each El Niño season with the 1991–2020 normal. Anomalies are draped
over the 3D terrain of Zambia from analysis 3.

Usage:
    python -m climate_analysis.elnino_seasons
    python -m climate_analysis.elnino_seasons --grib data/era5_monthly_zambia.grib --samples 32
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from scipy.ndimage import distance_transform_edt

from . import era5_monthly as era5m
from . import elnino_plots, terrain, terrain_3d, terrain_plots
from .elnino_plots import season_label, signed

SOUTH_OF = -13.5           # latitude splitting "northern" and "southern" Zambia
HERO = 2023                # season mapped on its own large posters
PANEL = (659, 460)         # pixel size of each 3D panel
NUMBER_WORDS = {3: "Three", 4: "Four", 5: "Five", 6: "Six"}


def _fill_nan(field: np.ndarray) -> np.ndarray:
    """Fill gaps at the edge of the data grid with the nearest valid value."""
    missing = ~np.isfinite(field)
    if not missing.any():
        return field
    _, (rows, cols) = distance_transform_edt(missing, return_indices=True)
    return field[rows, cols]


def _ratio(values: np.ndarray, normal: np.ndarray, weights: np.ndarray) -> float:
    """Area-mean anomaly in %: ratio of area-mean rainfall to area-mean normal."""
    return float((era5m.area_mean(values, weights) / era5m.area_mean(normal, weights) - 1.0) * 100.0)


def analyse(grib: Path, data_dir: Path, out_dir: Path, samples: int = 64, render: bool = True) -> str:
    country = terrain.COUNTRIES["zambia"]
    data = era5m.load_grib(grib)
    seasons = era5m.seasonal(data)
    rain_normal, temp_normal = era5m.climatology(seasons)
    el_nino = [y for y in era5m.EL_NINO if y in seasons.years]
    missing = sorted(set(era5m.EL_NINO) - set(el_nino))
    if missing:
        print(f"Skipping El Niño seasons not fully in the file: {[season_label(y) for y in missing]}")

    boundary, grid, elevation, mask = terrain_3d.load(country, data_dir, refresh=False)
    weights = era5m.cell_weights(data, country, boundary)
    lat = data.lat[:, None]
    regions = {"Zambia": weights, "north": weights * (lat >= SOUTH_OF), "south": weights * (lat < SOUTH_OF)}

    # Season statistics: every season, by region.
    table = {}
    for i, year in enumerate(seasons.years):
        table[int(year)] = {
            **{f"rain_{k}": _ratio(seasons.rain[i], rain_normal, w) for k, w in regions.items()},
            **{f"temp_{k}": float(era5m.area_mean(seasons.temp[i] - temp_normal, w)) for k, w in regions.items()},
            "rain_mm": float(era5m.area_mean(seasons.rain[i], weights)),
        }
    normal_mm = {k: float(era5m.area_mean(rain_normal, w)) for k, w in regions.items()}
    normal_temp = float(era5m.area_mean(temp_normal, weights))
    years = np.array(sorted(table))
    south = np.array([table[y]["rain_south"] for y in years])
    temps = np.array([table[y]["temp_Zambia"] for y in years])
    south_rank = {int(y): int(r) for y, r in zip(years, np.argsort(np.argsort(south)) + 1)}
    temp_rank = {int(y): int(r) for y, r in zip(years, np.argsort(np.argsort(-temps)) + 1)}

    # Month-by-month Zambia-average anomalies.
    monthly_rain = era5m.area_mean(data.precip, weights) * data.time.days_in_month.values
    monthly_temp = era5m.area_mean(data.t2m, weights)
    m_rain, m_temp = era5m.monthly_anomalies(data.time, monthly_rain, monthly_temp)
    season_of = era5m.season_of(data.time)
    order = [10, 11, 12, 1, 2, 3]

    def months_of(year, values):
        return [float(values[(season_of == year) & (data.time.month == m)][0]) for m in order]

    heat_rain = np.array([months_of(y, m_rain) for y in el_nino])
    heat_temp = np.array([months_of(y, m_temp) for y in el_nino])

    folder = out_dir / "elnino"
    figures = []
    if render:
        figures.append(render_poster(data, seasons, rain_normal, temp_normal, el_nino, table, south_rank,
                                     temp_rank, country, grid, elevation, mask, folder, samples))
        if HERO in table:
            k = el_nino.index(HERO)
            figures += render_hero(HERO, data, seasons, rain_normal, temp_normal, table, south_rank, temp_rank,
                                   normal_mm, heat_rain[k], heat_temp[k], weights, boundary, country, grid,
                                   elevation, mask, data_dir, folder, samples)
    figures.append(elnino_plots.monthly_heatmaps(
        heat_rain, heat_temp, el_nino, np.array([table[y]["rain_mm"] - normal_mm["Zambia"] for y in el_nino]),
        np.array([table[y]["temp_Zambia"] for y in el_nino]), folder / "figures" / "monthly_anomalies.png"))
    figures.append(elnino_plots.southern_rainfall_record(
        years, south, {y: era5m.EL_NINO[y] for y in el_nino}, folder / "figures" / "southern_rainfall_record.png"))

    n = len(years)
    record = f"{season_label(int(years[0]))} and {season_label(int(years[1]))}–{season_label(int(years[-1]))}"
    drier_south = sum(table[y]["rain_south"] < 0 for y in el_nino)
    worst = min(el_nino, key=lambda y: table[y]["rain_south"])
    hottest = max(el_nino, key=lambda y: table[y]["temp_Zambia"])
    nino_mean_s = np.mean([table[y]["rain_south"] for y in el_nino])
    nino_mean_n = np.mean([table[y]["rain_north"] for y in el_nino])
    feb = order.index(2)
    feb_share = {y: heat_rain[k, feb] / (table[y]["rain_mm"] - normal_mm["Zambia"]) * 100
                 for k, y in enumerate(el_nino) if table[y]["rain_mm"] < normal_mm["Zambia"] - 100}
    driest_five = [int(y) for y in years[np.argsort(south)[:5]]]
    not_nino = [y for y in driest_five if y not in el_nino]
    lines = [
        "# El Niño and Zambia's rainy season (October–March)",
        "",
        "Source: ERA5 monthly averaged reanalysis (Copernicus Climate Change Service / ECMWF) on a 0.25° grid "
        "(about 28 km), compared with the 1991–2020 normal (the 30 seasons from 1991/92 to 2020/21). "
        "Zambia averages weight each grid cell by the share of it inside the country and by its area. "
        f"Southern Zambia means south of {abs(SOUTH_OF)}° S. The record covers {n} complete seasons: {record}.",
        "",
        "## Key insights",
        "",
        f"- **El Niño mainly dries the south.** {drier_south} of the {len(el_nino)} El Niño seasons were drier "
        f"than normal in southern Zambia, by {abs(nino_mean_s):.0f}% on average. The north averaged "
        f"{signed(nino_mean_n, unit='%')}, so the El Niño signal shows up mainly in the south.",
        f"- **{season_label(worst)} was the driest season on record in the south**: "
        f"{signed(table[worst]['rain_south'], unit='%')} against normal, ranked {south_rank[worst]} of {n}. "
        f"Zambia as a whole received {table[worst]['rain_mm']:,.0f} mm against a normal "
        f"{normal_mm['Zambia']:,.0f} mm ({signed(table[worst]['rain_Zambia'], unit='%')}).",
        "- **The deficit concentrates in February**, the month maize needs most for grain filling. "
        "In the seasons that fell more than 100 mm short, February alone was "
        + " and ".join(f"{abs(heat_rain[el_nino.index(y), feb]):.0f} mm below normal in {season_label(y)} "
                       f"({share:.0f}% of the shortfall)" for y, share in feb_share.items())
        + ". The February 2024 dry spell also stands out in the Lusaka analysis (analysis 2)."
        if feb_share else "",
        f"- **{season_label(hottest)} was also the hottest**: {table[hottest]['temp_Zambia']:+.2f} °C above "
        f"normal across Zambia, ranked {temp_rank[hottest]} of {n}. Heat and drought together raise crop "
        "water stress beyond what the rainfall deficit alone suggests.",
        f"- **Not every El Niño brings drought.** In 1997/98, one of the strongest El Niños on record, the north "
        f"was {table[1997]['rain_north']:+.0f}% wetter than normal and Zambia overall {table[1997]['rain_Zambia']:+.0f}%. "
        "El Niño shifts the odds towards a dry south; it does not guarantee one."
        if 1997 in table else "",
        f"- **Drought also comes without El Niño.** Of the five driest southern seasons on record "
        f"({', '.join(season_label(y) for y in driest_five)}), {len(not_nino)} were not El Niño seasons: "
        f"{', '.join(season_label(y) for y in not_nino)}." if not_nino else "",
        "- **Recent El Niños are warmer.** The two most recent seasons, 2015/16 and 2023/24, were the warmest of "
        f"the five ({table[2015]['temp_Zambia']:+.2f} and {table[2023]['temp_Zambia']:+.2f} °C), while the earlier "
        "three were within about 0.25 °C of normal, consistent with the long-term warming trend in analysis 1."
        if {2015, 2023} <= set(table) else "",
        "",
        "## El Niño seasons",
        "",
        "| Season | Peak ONI | Rain, Zambia | Rain, north | Rain, south | South rank (1 = driest) | "
        "Temperature | Temp rank (1 = hottest) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        *[f"| {season_label(y)} | +{era5m.EL_NINO[y]:.1f} | {signed(table[y]['rain_Zambia'], unit='%')} | "
          f"{signed(table[y]['rain_north'], unit='%')} | {signed(table[y]['rain_south'], unit='%')} | "
          f"{south_rank[y]} of {n} | "
          f"{table[y]['temp_Zambia']:+.2f} °C | {temp_rank[y]} of {n} |" for y in el_nino],
        "",
        f"Normal October–March rainfall is {normal_mm['Zambia']:,.0f} mm for Zambia ({normal_mm['north']:,.0f} mm "
        f"in the north, {normal_mm['south']:,.0f} mm in the south), and the normal mean temperature is "
        f"{normal_temp:.1f} °C.",
        "",
        "## Month by month (Zambia average, difference from the monthly normal)",
        "",
        "| Season | " + " | ".join(["Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]) + " |",
        "|---|" + "---:|" * 6,
        *[f"| {season_label(y)} rain | " + " | ".join(signed(v, 0, " mm") for v in heat_rain[k]) + " |"
          for k, y in enumerate(el_nino)],
        *[f"| {season_label(y)} temp | " + " | ".join(signed(v, 1, " °C") for v in heat_temp[k]) + " |"
          for k, y in enumerate(el_nino)],
        "",
        "## Method",
        "",
        "- Season rainfall is the sum of the six monthly totals (mean daily rate × days in month). Season "
        "temperature is the day-weighted mean of the monthly means.",
        "- Rainfall anomalies are the season total as a percentage of the 1991–2020 mean; temperature anomalies "
        "are differences in °C. Area averages are taken before the ratio, so dry regions do not dominate.",
        "- For the maps, the 0.25° anomalies are resampled bilinearly onto the 600 m terrain grid, grouped into "
        "classes and draped over the 3D terrain (25× vertical exaggeration), path-traced with forge3d.",
        "- El Niño seasons and peak Oceanic Niño Index values follow NOAA's Climate Prediction Center.",
        "",
        "## Limitations",
        "",
        "- ERA5 is a reanalysis; its rainfall comes from the forecast model and is less reliable than its "
        "temperature. Satellite–gauge products such as CHIRPS (planned for analysis 4) are better for rainfall "
        "totals.",
        "- The 0.25° grid smooths local rainfall; the maps show regional patterns, not individual farms.",
        "- The 1991–2020 normal includes three of the El Niño seasons, as standard WMO normals do.",
        "- Seasons 1983/84 to 1989/90 are not in the download, so ranks cover the available record only.",
        "- El Niño is one of several drivers of Zambian rainfall (others include the Indian Ocean Dipole), "
        "so five events show tendencies, not certainties.",
        "",
        "## Figures",
        "",
        *[f"![{fig.stem}](figures/{fig.name})" for fig in figures],
        "",
    ]
    summary = "\n".join(line for line in lines if line is not None)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "summary.md").write_text(summary.replace("\n\n\n", "\n\n"), encoding="utf-8")
    return summary


def render_poster(data, seasons, rain_normal, temp_normal, el_nino, table, south_rank, temp_rank,
                  country, grid, elevation, mask, folder: Path, samples: int) -> Path:
    scene = terrain_3d.TerrainScene(country, grid, elevation, mask, *PANEL, factor=4, tilt_deg=52.0,
                                    fill_x=0.94, fill_y=0.94, centre_y=0.5)
    lusaka = scene.project(np.array([28.2833]), np.array([-15.4167]))[0]
    rows = [
        dict(name="Rainfall", unit="October–March total,\n% of the 1991–2020\nnormal",
             edges=elnino_plots.RAIN_EDGES, colours=elnino_plots.RAIN_COLOURS, legend_title="% of normal",
             tick_format=lambda v: f"{v:+.0f}%", captions=[]),
        dict(name="Temperature", unit="October–March mean,\n°C above or below\nthe 1991–2020 normal",
             edges=elnino_plots.TEMP_EDGES, colours=elnino_plots.TEMP_COLOURS, legend_title="°C vs normal",
             tick_format=lambda v: f"{v:+.2f}".rstrip("0").rstrip("."), captions=[]),
    ]
    panels, lusaka_xy = {}, {}
    for j, year in enumerate(el_nino):
        i = seasons.index(year)
        rain_pct = (seasons.rain[i] / rain_normal - 1.0) * 100.0
        temp_c = seasons.temp[i] - temp_normal
        for r, (field, row) in enumerate([(rain_pct, rows[0]), (temp_c, rows[1])]):
            on_grid = _fill_nan(era5m.to_grid(field, data, country, grid))
            colours = elnino_plots.classify(on_grid, row["edges"], row["colours"])
            panels[(r, j)] = scene.render(colours, samples)
            lusaka_xy[(r, j)] = lusaka
        rows[0]["captions"].append(f"South {signed(table[year]['rain_south'], unit='%')}  ·  "
                                   f"north {signed(table[year]['rain_north'], unit='%')}")
        rows[1]["captions"].append(f"Zambia {table[year]['temp_Zambia']:+.2f} °C")

    columns = [dict(title=season_label(y), subtitle=f"Peak ONI +{era5m.EL_NINO[y]:.1f}") for y in el_nino]
    worst = min(el_nino, key=lambda y: table[y]["rain_south"])
    header = dict(
        kicker="El Niño and Zambia's rainy season",
        title=f"{NUMBER_WORDS.get(len(el_nino), len(el_nino))} El Niño seasons, October to March",
        subtitle=("Rainfall and temperature compared with the 1991–2020 normal, draped over Zambia's terrain. "
                  "El Niño mostly dries the south;\n"
                  f"{season_label(worst)} was the driest season on record there "
                  f"({signed(table[worst]['rain_south'], unit='%')}) and also the hottest ({table[worst]['temp_Zambia']:+.2f} °C)."),
        notes=(f"North and south split at {abs(SOUTH_OF)}° S  ·  ONI = Oceanic Niño Index  ·  "
               "Vertical exaggeration 25×  ·  Path-traced on the GPU with forge3d"),
    )
    return elnino_plots.seasons_poster(panels, columns, rows, header, folder / "figures" / "elnino_seasons_3d.png",
                                       lusaka_xy)


def render_hero(year, data, seasons, rain_normal, temp_normal, table, south_rank, temp_rank, normal_mm,
                months_rain, months_temp, weights, boundary, country, grid, elevation, mask, data_dir,
                folder: Path, samples: int) -> list[Path]:
    """Two large posters for one season: rainfall and temperature anomalies on the 3D terrain."""
    i, n = seasons.index(year), len(seasons.years)
    label = season_label(year)
    rain_pct = (seasons.rain[i] / rain_normal - 1.0) * 100.0
    temp_c = seasons.temp[i] - temp_normal
    names = ["October", "November", "December", "January", "February", "March"]
    dry_month, hot_month = int(np.argmin(months_rain)), int(np.argmax(months_temp))
    above_1c = float((weights * (temp_c > 1.0)).sum() / weights.sum() * 100)
    everywhere_warmer = bool(temp_c[weights > 0].min() > 0)

    width, height = terrain_plots.map_size(3200)
    scene = terrain_3d.TerrainScene(country, grid, elevation, mask, width, height)
    lines, rings, africa, labels = terrain_3d.map_layers(
        scene, data_dir, label_kinds={"capital", "city", "water", "waterpoint", "country"})
    credit = elnino_plots.DATA_CREDIT
    notes = (f"October–March {label} compared with the 1991–2020 normal  ·  ERA5 at 0.25° (about 28 km), "
             f"resampled onto the terrain  ·  " + terrain_3d.poster_notes())
    t = table[year]
    posters = [
        (rain_pct, "rainfall", elnino_plots.RAIN_FINE_EDGES, elnino_plots.RAIN_FINE_COLOURS,
         terrain_plots.PosterText(
             kicker=f"El Niño {label}  ·  the rainy season, October to March",
             title=f"The {label} drought",
             subtitle=(f"Rainfall compared with the 1991–2020 normal. The strong El Niño left southern\n"
                       f"Zambia with only {100 + t['rain_south']:.0f}% of its usual rain, the driest season on record."),
             callouts=[
                 (signed(t["rain_south"], unit="%"),
                  f"rainfall in southern Zambia,\nthe driest of {n} seasons"),
                 (signed(months_rain[dry_month], 0, " mm"),
                  f"{names[dry_month]} rainfall across Zambia,\nwhen maize fills its grain"
                  if names[dry_month] in ("January", "February") else f"{names[dry_month]} rainfall across Zambia"),
                 (f"{t['rain_mm']:,.0f} mm",
                  f"fell across Zambia, against\na normal {normal_mm['Zambia']:,.0f} mm"),
             ],
             legend=dict(edges=elnino_plots.RAIN_FINE_EDGES, colours=elnino_plots.RAIN_FINE_COLOURS,
                         labels=[signed(v, unit="%") for v in elnino_plots.RAIN_FINE_EDGES],
                         title="Rainfall, % above or below normal"),
             notes=notes, credit=credit, title_size=40, subtitle_x=0.44)),
        (temp_c, "temperature", elnino_plots.HEAT_EDGES, elnino_plots.HEAT_COLOURS,
         terrain_plots.PosterText(
             kicker=f"El Niño {label}  ·  the rainy season, October to March",
             title=f"The {label} heat",
             subtitle=("Mean temperature compared with the 1991–2020 normal. "
                       + ("Every part of Zambia\nwas warmer than normal"
                          if everywhere_warmer else "Most of Zambia\nwas warmer than normal")
                       + f", making it the hottest rainy season on record."
                       if temp_rank[year] == 1 else f", ranked {temp_rank[year]} of {n}."),
             callouts=[
                 (signed(t["temp_Zambia"], 2, " °C"),
                  f"warmer than normal across\nZambia, the hottest of {n} seasons"
                  if temp_rank[year] == 1 else f"warmer than normal across\nZambia, ranked {temp_rank[year]} of {n}"),
                 (signed(months_temp[hot_month], 1, " °C"),
                  f"in {names[hot_month]}, the month furthest\nabove its normal"),
                 (f"{above_1c:.0f}%", "of the country was more than\n1 °C warmer than normal"),
             ],
             legend=dict(edges=elnino_plots.HEAT_EDGES, colours=elnino_plots.HEAT_COLOURS,
                         labels=[f"+{v:g}" for v in elnino_plots.HEAT_EDGES],
                         title="Temperature, °C above normal"),
             notes=notes, credit=credit, title_size=40, subtitle_x=0.44)),
    ]
    paths = []
    for field, name, edges, colours, text in posters:
        on_grid = _fill_nan(era5m.to_grid(field, data, country, grid))
        rgb, alpha = scene.render(elnino_plots.classify(on_grid, edges, colours), samples)
        path = folder / "figures" / f"elnino_{year}_{str(year + 1)[-2:]}_{name}_3d.png"
        paths.append(terrain_plots.terrain_poster(rgb, alpha, scene.project, lines, rings, labels, text,
                                                  africa, boundary, path))
    return paths


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--grib", type=Path, default=Path("data") / "era5_monthly_zambia.grib",
                        help="ERA5 monthly means GRIB from the Copernicus Climate Data Store")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--out-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--samples", type=int, default=64, help="path-traced samples per pixel")
    parser.add_argument("--no-render", action="store_true", help="skip the GPU renders")
    args = parser.parse_args(argv)
    print(analyse(args.grib, args.data_dir, args.out_dir, samples=args.samples, render=not args.no_render))


if __name__ == "__main__":
    main()
