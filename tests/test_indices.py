import numpy as np
import pandas as pd
import pytest

from climate_analysis import era5, indices, trends


def daily(values, start="2000-01-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="D"),
                     dtype=float)


def test_leap_day_of_year_aligns_march_first():
    idx = pd.DatetimeIndex(["2001-03-01", "2004-03-01", "2004-02-29", "2001-12-31"])
    assert list(indices.leap_day_of_year(idx)) == [61, 61, 60, 366]


def test_spells_finds_runs_and_filters_short_ones():
    mask = daily([0, 1, 1, 1, 0, 1, 0, 1, 1]).astype(bool)

    result = indices.spells(mask, min_length=2)

    assert list(result.length) == [3, 2]
    assert result.start.iloc[0] == pd.Timestamp("2000-01-02")
    assert result.end.iloc[1] == pd.Timestamp("2000-01-09")


def test_daily_percentile_of_constant_series():
    series = daily(np.full(365 * 4, 25.0), start="1961-01-01")

    thresholds = indices.daily_percentile(series, 90, base=(1961, 1964))

    assert len(thresholds) == 366
    assert np.allclose(thresholds, 25.0)


def test_heatwaves_need_three_consecutive_hot_days():
    tmax = daily([20, 30, 30, 20, 30, 30, 30, 31, 20])
    threshold = pd.Series(25.0, index=range(1, 367))

    events = indices.heatwaves(tmax, threshold, min_length=3)

    assert len(events) == 1
    assert events.length.iloc[0] == 4
    assert events.peak_tmax.iloc[0] == 31


def test_rain_onset_skips_false_start():
    rain = daily(np.zeros(365), start="2000-07-01")
    rain[pd.Timestamp("2000-10-10")] = 25   # false start: followed by 30 dry days
    rain[pd.Timestamp("2000-11-20")] = 25   # true onset: regular rain afterwards
    rain[pd.date_range("2000-11-22", "2001-03-31", freq="3D")] = 5

    assert indices.rain_onset(rain) == pd.Timestamp("2000-11-20")


def test_season_year_labels_july_to_june():
    idx = pd.DatetimeIndex(["2023-06-30", "2023-07-01", "2024-03-15"])
    assert list(indices.season_year(idx)) == [2022, 2023, 2023]
    assert indices.season_label(2023) == "2023/24"


def test_sen_trend_recovers_slope_and_ignores_outlier():
    years = np.arange(1950, 2020)
    values = 0.5 * (years - 1950)
    values[10] = 500  # a single wild outlier
    series = pd.Series(values, index=years)

    result = trends.sen_trend(series)

    assert result.slope_per_decade == pytest.approx(5.0)
    assert result.significant


def test_district_cells_cover_lusaka():
    cells = era5.DISTRICTS["lusaka"].cells()
    assert cells == [(-15.5, 28.25), (-15.5, 28.5), (-15.25, 28.25), (-15.25, 28.5)]
