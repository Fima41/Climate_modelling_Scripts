"""Detect and analyse heatwaves, cold nights, heavy rain and dry spells.

Uses daily ERA5 reanalysis averaged over a district's grid cells.

Usage:
    python -m climate_analysis.extreme_events --district lusaka
    python -m climate_analysis.extreme_events --district lusaka --refresh
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from . import era5, extreme_plots, indices, trends

START = "1950-01-01"
END = "2026-06-30"
BASE = indices.BASE_PERIOD
RECENT = (1996, 2025)


def _period_mean(table: pd.DataFrame, column: str, period: tuple[int, int]) -> float:
    return float(table.loc[period[0]:period[1], column].mean())


def _trend_text(trend: trends.SenTrend, unit: str) -> str:
    verdict = "significant" if trend.significant else "not significant"
    return (f"{trend.slope_per_decade:+.1f} {unit} per decade "
            f"(95% CI {trend.ci95_low:+.1f} to {trend.ci95_high:+.1f}; "
            f"p = {trend.p_value:.2g}, {verdict})")


def analyse(district: str, data_dir: Path, out_dir: Path, refresh: bool = False) -> str:
    place = era5.DISTRICTS[district].name
    short_place = place.split(",")[0]
    daily = era5.load(district, START, END, data_dir, refresh)

    annual = indices.annual_temperature_indices(daily, BASE)
    seasons = indices.seasonal_rain_indices(daily.prcp, BASE)
    tx90 = indices.daily_percentile(daily.tmax, 90, BASE)
    events = indices.heatwaves(daily.tmax, tx90)
    heat_trends = {c: trends.sen_trend(annual[c]) for c in annual.columns}
    rain_trends = {c: trends.sen_trend(seasons[c])
                   for c in seasons.columns.drop("onset")}

    fig_dir = out_dir / district / "figures"
    figures = [
        extreme_plots.heatwave_days(annual, heat_trends["heatwave_days"], short_place,
                                    fig_dir / "heatwave_days.png"),
        extreme_plots.hot_days_cold_nights(annual, short_place, fig_dir / "hot_days_cold_nights.png"),
        extreme_plots.compound_event(daily, tx90, events, "2024-01-01", "2024-03-31",
                                     short_place, fig_dir / "compound_event_2024.png"),
        extreme_plots.rainy_seasons(seasons, short_place, fig_dir / "rainy_seasons.png"),
        extreme_plots.monthly_heatmap(indices.monthly_anomaly(daily.tmax, BASE).loc[:annual.index[-1]],
                                      short_place, fig_dir / "monthly_tmax_anomaly.png"),
    ]

    base_label = f"{BASE[0]}–{BASE[1]}"
    recent_label = f"{RECENT[0]}–{RECENT[1]}"
    hw_base = _period_mean(annual, "heatwave_days", BASE)
    hw_recent = _period_mean(annual, "heatwave_days", RECENT)
    wet_base = _period_mean(seasons, "very_wet_mm", BASE)
    wet_recent = _period_mean(seasons, "very_wet_mm", RECENT)
    hottest = annual.hot_days_pct.idxmax()
    longest = events.sort_values("length", ascending=False).head(5)
    driest = seasons.total_mm.nsmallest(5)

    def label(season: int) -> str:
        return indices.season_label(season)

    lines = [
        f"# Extreme weather in {place} ({annual.index[0]}–{annual.index[-1]})",
        "",
        "Source: ERA5 reanalysis (Copernicus Climate Change Service / ECMWF), daily values "
        "averaged over the grid cells covering the district. Retrieved via the Open-Meteo API. "
        f"Thresholds use the {base_label} base period.",
        "",
        "## Key insights",
        "",
        "### Heat",
        "",
        f"- **Heatwave days have increased by about {hw_recent / hw_base:.1f}×**, from "
        f"{hw_base:.0f} per year in {base_label} to {hw_recent:.0f} per year in {recent_label}. "
        f"Trend: {_trend_text(heat_trends['heatwave_days'], 'days')}.",
        f"- **Hot days** (above the 90th percentile) made up "
        f"{_period_mean(annual, 'hot_days_pct', RECENT):.0f}% of days in {recent_label}, compared with "
        f"about 10% in the baseline. In **{hottest}** the figure reached "
        f"**{annual.hot_days_pct[hottest]:.0f}%**, the highest on record.",
        f"- **Cold nights** fell from {_period_mean(annual, 'cold_nights_pct', BASE):.0f}% to "
        f"{_period_mean(annual, 'cold_nights_pct', RECENT):.0f}% of nights. "
        f"Trend: {_trend_text(heat_trends['cold_nights_pct'], 'percentage points')}.",
        f"- **The hottest day of the year** is warming: "
        f"{_trend_text(heat_trends['txx'], '°C')}.",
        f"- **The longest heatwave on record** lasted {longest.length.iloc[0]} days "
        f"({longest.start.iloc[0]:%d %b %Y} – {longest.end.iloc[0]:%d %b %Y}). Heatwaves are measured "
        "against the normal for the time of year, so a cool-season heatwave means unusually warm for "
        "that season rather than the hottest days of the year.",
        "",
        "### Rainfall",
        "",
        f"- **Season totals show no clear trend**: {_trend_text(rain_trends['total_mm'], 'mm')}. "
        f"The average is {_period_mean(seasons, 'total_mm', BASE):.0f} mm in {base_label} and "
        f"{_period_mean(seasons, 'total_mm', RECENT):.0f} mm in {recent_label}.",
        f"- **Rain from very wet days** rose from {wet_base:.0f} to {wet_recent:.0f} mm per season "
        f"({wet_recent / wet_base - 1:+.0%}). This hints at heavier downpours, but the trend is "
        f"{'significant' if rain_trends['very_wet_mm'].significant else 'not yet statistically significant'} "
        f"(p = {rain_trends['very_wet_mm'].p_value:.2g}).",
        f"- **Onset of the rains** averages day {_period_mean(seasons, 'onset_day', RECENT):.0f} "
        f"after 1 October (about {(pd.Timestamp(2000, 10, 1) + pd.Timedelta(days=round(_period_mean(seasons, 'onset_day', RECENT)))):%d %B}). "
        f"Trend: {_trend_text(rain_trends['onset_day'], 'days')}.",
        f"- **Driest seasons:** " + ", ".join(f"{label(s)} ({v:.0f} mm)" for s, v in driest.items()) + ".",
        "",
        "### 2023/24: heat and drought together",
        "",
        "- During the 2023/24 El Niño season, a mid-season dry spell ran from 8 to 24 February 2024. "
        "It overlapped a 24-day heatwave (3–26 February), one of the longest on record. Heat and drought "
        "at the same time during crop development is especially damaging for maize.",
        "",
        "## Longest heatwaves",
        "",
        "| Start | End | Days | Peak max temp (°C) |",
        "|---|---|---:|---:|",
        *[f"| {e.start:%d %b %Y} | {e.end:%d %b %Y} | {e.length} | {e.peak_tmax:.1f} |"
          for e in longest.itertuples()],
        "",
        "## Trend summary (Theil–Sen slope per decade, Mann–Kendall test)",
        "",
        "| Index | Trend per decade | 95% CI | p-value |",
        "|---|---:|---:|---:|",
        *[f"| {name} | {t.slope_per_decade:+.2f} | {t.ci95_low:+.2f} to {t.ci95_high:+.2f} | "
          f"{t.p_value:.2g} |" for name, t in {**heat_trends, **rain_trends}.items()],
        "",
        "## Limitations",
        "",
        "- ERA5 is a reanalysis: a model constrained by observations, at a resolution of about 28 km. "
        "It represents the district average, not any single point.",
        "- Reanalysis tends to produce too many light-rain days, so dry spells may be underestimated.",
        "- Fewer observations were assimilated before 1979 (the pre-satellite era), so early years are "
        "less certain.",
        "- Percentile thresholds are not bootstrapped for years inside the base period, a simplification "
        "of the ETCCDI method.",
        "",
        "## Figures",
        "",
        *[f"![{fig.stem}](figures/{fig.name})" for fig in figures],
        "",
    ]
    summary = "\n".join(lines)
    (out_dir / district / "summary.md").write_text(summary, encoding="utf-8")
    annual.round(2).to_csv(out_dir / district / "annual_heat_indices.csv")
    seasons.assign(onset=seasons.onset.dt.date).round(1).to_csv(out_dir / district / "seasonal_rain_indices.csv")
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--district", choices=list(era5.DISTRICTS), default="lusaka")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--out-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--refresh", action="store_true",
                        help="re-download the data instead of using the cache")
    args = parser.parse_args(argv)
    print(analyse(args.district, args.data_dir, args.out_dir, args.refresh))


if __name__ == "__main__":
    main()
