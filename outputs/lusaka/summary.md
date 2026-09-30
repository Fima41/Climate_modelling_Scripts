# Extreme weather in Lusaka District, Zambia (1950–2025)

Source: ERA5 reanalysis (Copernicus Climate Change Service / ECMWF), daily values averaged over the grid cells covering the district. Retrieved via the Open-Meteo API. Thresholds use the 1961–1990 base period.

## Key insights

### Heat

- **Heatwave days have increased by about 2.5×**, from 17 per year in 1961–1990 to 44 per year in 1996–2025. Trend: +4.4 days per decade (95% CI +2.5 to +6.6; p = 1.5e-05, significant).
- **Hot days** (above the 90th percentile) made up 19% of days in 1996–2025, compared with about 10% in the baseline. In **2024** the figure reached **51%**, the highest on record.
- **Cold nights** fell from 10% to 6% of nights. Trend: -0.5 percentage points per decade (95% CI -0.9 to -0.1; p = 0.0073, significant).
- **The hottest day of the year** is warming: +0.2 °C per decade (95% CI +0.1 to +0.3; p = 0.0046, significant).
- **The longest heatwave on record** lasted 28 days (04 Jul 2024 – 31 Jul 2024). Heatwaves are measured against the normal for the time of year, so a cool-season heatwave means unusually warm for that season rather than the hottest days of the year.

### Rainfall

- **Season totals show no clear trend**: -9.9 mm per decade (95% CI -34.9 to +12.6; p = 0.33, not significant). The average is 943 mm in 1961–1990 and 945 mm in 1996–2025.
- **Rain from very wet days** rose from 152 to 186 mm per season (+22%). This hints at heavier downpours, but the trend is not yet statistically significant (p = 0.3).
- **Onset of the rains** averages day 52 after 1 October (about 22 November). Trend: +0.4 days per decade (95% CI -1.1 to +1.8; p = 0.62, not significant).
- **Driest seasons:** 1953/54 (516 mm), 1950/51 (538 mm), 1994/95 (608 mm), 1972/73 (609 mm), 1986/87 (634 mm).

### 2023/24: heat and drought together

- During the 2023/24 El Niño season, a mid-season dry spell ran from 8 to 24 February 2024. It overlapped a 24-day heatwave (3–26 February), one of the longest on record. Heat and drought at the same time during crop development is especially damaging for maize.

## Longest heatwaves

| Start | End | Days | Peak max temp (°C) |
|---|---|---:|---:|
| 04 Jul 2024 | 31 Jul 2024 | 28 | 29.5 |
| 03 Feb 2024 | 26 Feb 2024 | 24 | 33.8 |
| 19 Feb 1954 | 09 Mar 1954 | 19 | 32.4 |
| 30 May 2023 | 17 Jun 2023 | 19 | 28.1 |
| 06 Dec 1951 | 22 Dec 1951 | 17 | 33.1 |

## Trend summary (Theil–Sen slope per decade, Mann–Kendall test)

| Index | Trend per decade | 95% CI | p-value |
|---|---:|---:|---:|
| hot_days_pct | +1.83 | +1.26 to +2.56 | 1.3e-06 |
| cold_nights_pct | -0.50 | -0.86 to -0.14 | 0.0073 |
| heatwave_events | +0.93 | +0.53 to +1.43 | 5.6e-06 |
| heatwave_days | +4.38 | +2.50 to +6.55 | 1.5e-05 |
| longest_heatwave | +0.65 | +0.20 to +1.09 | 0.0016 |
| txx | +0.18 | +0.06 to +0.29 | 0.0046 |
| tnn | -0.03 | -0.14 to +0.09 | 0.66 |
| total_mm | -9.93 | -34.89 to +12.61 | 0.33 |
| wet_days | -1.67 | -3.60 to +0.53 | 0.13 |
| rx1day_mm | +0.92 | -0.22 to +2.07 | 0.11 |
| rx5day_mm | +1.31 | -0.75 to +3.71 | 0.22 |
| heavy_days | +0.00 | -0.18 to +0.43 | 0.49 |
| very_wet_mm | +4.55 | -4.69 to +14.75 | 0.3 |
| longest_dry_spell | +0.00 | -0.28 to +0.62 | 0.52 |
| onset_day | +0.38 | -1.13 to +1.82 | 0.62 |

## Limitations

- ERA5 is a reanalysis: a model constrained by observations, at a resolution of about 28 km. It represents the district average, not any single point.
- Reanalysis tends to produce too many light-rain days, so dry spells may be underestimated.
- Fewer observations were assimilated before 1979 (the pre-satellite era), so early years are less certain.
- Percentile thresholds are not bootstrapped for years inside the base period, a simplification of the ETCCDI method.

## Figures

![heatwave_days](figures/heatwave_days.png)
![hot_days_cold_nights](figures/hot_days_cold_nights.png)
![compound_event_2024](figures/compound_event_2024.png)
![rainy_seasons](figures/rainy_seasons.png)
![monthly_tmax_anomaly](figures/monthly_tmax_anomaly.png)
