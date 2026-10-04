import numpy as np
import pandas as pd
import pytest

from climate_analysis import elnino_plots, era5_monthly


def monthly(start="1990-01-01", end="2022-12-01", precip=None, t2m=None):
    time = pd.date_range(start, end, freq="MS")
    shape = (len(time), 2, 3)
    return era5_monthly.Monthly(
        time=time, lat=np.array([-10.0, -10.25]), lon=np.array([25.0, 25.25, 25.5]),
        t2m=np.full(shape, 20.0, dtype=np.float32) if t2m is None else t2m,
        precip=np.full(shape, 5.0, dtype=np.float32) if precip is None else precip,
    )


def test_season_of_assigns_october_to_march_to_the_start_year():
    time = pd.DatetimeIndex(["1997-09-01", "1997-10-01", "1997-12-01", "1998-01-01", "1998-03-01"])

    assert list(era5_monthly.season_of(time)) == [1996, 1997, 1997, 1997, 1997]


def test_seasonal_totals_weight_by_days_and_skip_incomplete_seasons():
    data = monthly()

    seasons = era5_monthly.seasonal(data)

    # Oct 1990 - Mar 2022 complete; Oct-Dec 1989 and Oct-Dec 2022 are incomplete.
    assert seasons.years[0] == 1990 and seasons.years[-1] == 2021
    days_1997 = 31 + 30 + 31 + 31 + 28 + 31
    assert seasons.rain[seasons.index(1997)][0, 0] == pytest.approx(5.0 * days_1997)
    assert seasons.temp[seasons.index(1997)][0, 0] == pytest.approx(20.0)


def test_climatology_requires_the_full_baseline():
    seasons = era5_monthly.seasonal(monthly())
    rain, temp = era5_monthly.climatology(seasons)
    assert rain[0, 0] == pytest.approx(5.0 * 182, rel=0.01) and temp[0, 0] == pytest.approx(20.0)

    short = era5_monthly.seasonal(monthly(start="1995-01-01"))
    with pytest.raises(ValueError, match="30 complete seasons"):
        era5_monthly.climatology(short)


def test_monthly_anomalies_against_calendar_month_normals():
    time = pd.date_range("1990-01-01", "2022-12-01", freq="MS")
    rain = np.where(time.month == 2, 100.0, 50.0)
    temp = np.full(len(time), 22.0)
    rain[(time.year == 2016) & (time.month == 2)] = 40.0
    temp[(time.year == 2016) & (time.month == 2)] = 24.0

    rain_anom, temp_anom = era5_monthly.monthly_anomalies(time, rain, temp)

    feb_2016 = np.flatnonzero((time.year == 2016) & (time.month == 2))[0]
    assert rain_anom[feb_2016] == pytest.approx(40.0 - (29 * 100 + 40) / 30)
    assert temp_anom[feb_2016] == pytest.approx(24.0 - (29 * 22 + 24) / 30)
    assert rain_anom[(time.year == 2016) & (time.month == 3)] == pytest.approx(0.0)


def test_area_mean_ignores_nan_and_respects_weights():
    field = np.array([[1.0, 3.0], [np.nan, 10.0]])
    weights = np.array([[1.0, 1.0], [5.0, 0.0]])

    assert era5_monthly.area_mean(field, weights) == pytest.approx(2.0)


def test_classify_uses_stepped_classes():
    colours = elnino_plots.classify(np.array([-80.0, 0.0, 12.0, 99.0]), elnino_plots.RAIN_EDGES,
                                    elnino_plots.RAIN_COLOURS)

    expected = [elnino_plots.RAIN_COLOURS[i] for i in (0, 4, 5, 8)]
    assert np.allclose(colours, [elnino_plots.terrain._hex_rgb(c) for c in expected])


def test_signed_formatting_never_shows_negative_zero():
    assert elnino_plots.signed(-0.3, unit="%") == "0%"
    assert elnino_plots.signed(-44.4, unit="%") == "-44%"
    assert elnino_plots.signed(1.454, 2, " °C") == "+1.45 °C"
    assert elnino_plots.season_label(2023) == "2023/24"
