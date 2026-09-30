"""Analyse long-term surface temperature trends from NASA GISTEMP.

Usage:
    python -m climate_analysis.temperature_trends --dataset global
    python -m climate_analysis.temperature_trends --dataset north --refresh
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import data, plots, trends

RECENT_START = 1980
ROLLING_WINDOW = 30


def analyse(dataset: str, data_dir: Path, out_dir: Path, refresh: bool = False) -> str:
    """Run the full analysis, write figures and a summary, and return the summary."""
    _, region = data.DATASETS[dataset]
    table = data.load(dataset, data_dir, refresh)
    annual = data.annual_series(table)

    full = trends.linear_trend(annual)
    recent = trends.linear_trend(annual, start=RECENT_START)
    breakpoint_ = trends.find_breakpoint(annual)
    rolling = trends.rolling_trend(annual, ROLLING_WINDOW)
    smooth = trends.rolling_mean(annual, 10)
    warmest = trends.warmest_years(annual, 10)
    decades = trends.decade_means(annual)
    since_preindustrial = trends.change_since(annual)
    seasonal = {
        season: trends.linear_trend(table[season].dropna(), start=RECENT_START,
                                    end=annual.index[-1])
        for season in data.SEASONS
    }

    fig_dir = out_dir / dataset / "figures"
    figures = [
        plots.anomaly_bars(annual, smooth, region, fig_dir / "anomaly_timeseries.png"),
        plots.warming_stripes(annual, region, fig_dir / "warming_stripes.png"),
        plots.rolling_trend_plot(rolling, full, ROLLING_WINDOW, region,
                                 fig_dir / "warming_rate.png"),
        plots.seasonal_trends(seasonal, region, fig_dir / "seasonal_trends.png"),
    ]

    if breakpoint_.slope_before > 0:
        speedup = f"{breakpoint_.acceleration:.1f}× faster"
    else:
        speedup = "a switch from flat or cooling to sustained warming"
    recent_decade_count =sum(year >= annual.index[-1] - 9 for year in warmest.index)
    fastest_season = max(seasonal, key=lambda s: seasonal[s].slope_per_decade)
    decade_warming = decades.diff().dropna()

    lines = [
        f"# {region} temperature trends ({annual.index[0]}–{annual.index[-1]})",
        "",
        f"Source: NASA GISTEMP v4. Anomalies are relative to the {data.BASELINE} mean.",
        "",
        "## Key insights",
        "",
        f"- **{since_preindustrial:+.2f} °C**: the last 10 years were this much warmer "
        f"than 1880–1900, a common stand-in for pre-industrial levels.",
        f"- **Long-term rate:** {full.slope_per_decade:+.3f} ± {full.ci95_per_decade:.3f} °C "
        f"per decade since {full.start} (R² = {full.r_squared:.2f}, p = {full.p_value:.1e}).",
        f"- **Recent rate:** {recent.slope_per_decade:+.3f} ± {recent.ci95_per_decade:.3f} °C "
        f"per decade since {RECENT_START}, "
        f"{recent.slope_per_decade / full.slope_per_decade:.1f}× the long-term rate.",
        f"- **Acceleration:** the best-fit breakpoint is **{breakpoint_.year}**. The rate went "
        f"from {breakpoint_.slope_before:+.3f} to {breakpoint_.slope_after:+.3f} °C/decade "
        f"({speedup}). The two-segment fit cuts squared error by "
        f"{1 - breakpoint_.sse / breakpoint_.sse_single_line:.0%} compared with a single line.",
        f"- **Latest {ROLLING_WINDOW}-year rate:** {rolling.iloc[-1]:+.3f} °C/decade for "
        f"{rolling.index[-1] - ROLLING_WINDOW + 1}–{rolling.index[-1]}.",
        f"- **Record heat:** {recent_decade_count} of the 10 warmest years on record fall in "
        f"the last decade. The warmest year is {warmest.index[0]} ({warmest.iloc[0]:+.2f} °C).",
        f"- **Fastest-warming season since {RECENT_START}:** {fastest_season} "
        f"({seasonal[fastest_season].slope_per_decade:+.3f} °C/decade).",
        "",
        "## Ten warmest years",
        "",
        "| Rank | Year | Anomaly (°C) |",
        "|---:|---:|---:|",
        *[f"| {rank} | {year} | {value:+.2f} |"
          for rank, (year, value) in enumerate(warmest.items(), start=1)],
        "",
        "## Decade averages",
        "",
        "| Decade | Mean anomaly (°C) | Change from previous decade (°C) |",
        "|---|---:|---:|",
        *[f"| {decade}s | {mean:+.2f} | "
          f"{decade_warming.get(decade, float('nan')):+.2f} |".replace("+nan", "–")
          for decade, mean in decades.items()],
        "",
        "## Figures",
        "",
        *[f"![{fig.stem}](figures/{fig.name})" for fig in figures],
        "",
    ]
    summary = "\n".join(lines)
    (out_dir / dataset / "summary.md").write_text(summary, encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", choices=[*data.DATASETS, "all"], default="global")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--out-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--refresh", action="store_true",
                        help="re-download the latest data instead of using the cache")
    args = parser.parse_args(argv)

    datasets = list(data.DATASETS) if args.dataset == "all" else [args.dataset]
    for dataset in datasets:
        print(analyse(dataset, args.data_dir, args.out_dir, args.refresh))


if __name__ == "__main__":
    main()
