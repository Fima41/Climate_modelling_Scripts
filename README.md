# Climate Modelling Scripts

Python tools that turn public climate datasets into clear, quantified insights.
Each analysis downloads real observational data, runs reproducible statistics, and
produces publication-style figures along with a plain-English summary.

![Global warming stripes](outputs/global/figures/warming_stripes.png)

## Analyses

| # | Analysis | Data | Status |
|---|---|---|---|
| 1 | [Temperature trends](#1-temperature-trends) | NASA GISTEMP v4 | ✅ Done |
| 2 | Extreme weather events (heatwaves, heavy rain) | NOAA GHCN-Daily | Planned |
| 3 | Drought analysis (SPI) | CHIRPS | Planned |
| 4 | CMIP6 future projections | CMIP6 | Planned |

---

## 1. Temperature trends

**Question:** How much has the planet warmed, and is the warming speeding up?

### Key findings (global, 1880–2025)

- The last decade was **+1.24 °C** warmer than 1880–1900, a common stand-in for pre-industrial levels.
- Warming since 1980 runs at **+0.21 °C per decade**, 2.5× the long-term rate of +0.08 °C per decade.
- Piecewise regression places the **acceleration point in 1975**. After it, warming is 5.6× faster than before.
- The latest 30-year warming rate (**+0.25 °C/decade**) is the highest in the record.
- **9 of the 10 warmest years** have all happened in the last decade. 2024 is the warmest year on record.
- The Northern Hemisphere is warming about **2.6× faster** than the Southern Hemisphere since 1980
  (+0.30 vs +0.12 °C/decade), because land warms faster than ocean.

Full reports with tables: [Global](outputs/global/summary.md) ·
[Northern Hemisphere](outputs/north/summary.md) · [Southern Hemisphere](outputs/south/summary.md)

![Global temperature anomaly](outputs/global/figures/anomaly_timeseries.png)
![Warming rate](outputs/global/figures/warming_rate.png)
![Seasonal trends](outputs/global/figures/seasonal_trends.png)

### Methods

| Step | Method |
|---|---|
| Annual anomalies | GISTEMP January–December means, relative to 1951–1980. Incomplete years are dropped. |
| Trend | Ordinary least-squares regression with 95% confidence interval (t-distribution) |
| Acceleration | Continuous piecewise (hinge) regression. The breakpoint year is chosen by grid search to minimise squared error. |
| Warming rate over time | Linear trend of each trailing 30-year window |
| Smoothing | Centred 10-year rolling mean |
| Seasonal trends | OLS on the DJF / MAM / JJA / SON means since 1980 |

---

## Getting started

```bash
git clone https://github.com/Fima41/Climate_modelling_Scripts.git
cd Climate_modelling_Scripts
pip install -r requirements.txt

# Run the analysis (downloads data automatically on the first run)
python -m climate_analysis.temperature_trends --dataset global
python -m climate_analysis.temperature_trends --dataset all --refresh   # all regions, latest data

# Run the tests
python -m pytest
```

Options: `--dataset {global,north,south,all}`, `--refresh` (re-download), `--data-dir`, `--out-dir`.

## Project structure

```
climate_analysis/
├── data.py                 # Download and parse NASA GISTEMP tables
├── trends.py               # Trend, breakpoint, rolling-rate statistics
├── plots.py                # Figure styling and chart functions
└── temperature_trends.py   # Command-line entry point and insights report
tests/                      # Unit tests on synthetic data with known answers
outputs/<region>/           # Generated figures and summary.md
```

## Data source

GISTEMP Team, 2026: *GISS Surface Temperature Analysis (GISTEMP), version 4.*
NASA Goddard Institute for Space Studies. https://data.giss.nasa.gov/gistemp/

## License

MIT
