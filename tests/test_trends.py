import numpy as np
import pandas as pd
import pytest

from climate_analysis import trends


def make_series(values, start=1900):
    return pd.Series(values, index=range(start, start + len(values)), dtype=float)


def test_linear_trend_recovers_known_slope():
    years = np.arange(1900, 2000)
    series = make_series(0.02 * (years - 1900))  # 0.2 °C per decade

    result = trends.linear_trend(series)

    assert result.slope_per_decade == pytest.approx(0.2)
    assert result.r_squared == pytest.approx(1.0)
    assert result.total_change == pytest.approx(0.2 * 9.9)


def test_linear_trend_respects_period():
    series = make_series([0.0] * 50 + list(np.arange(50) * 0.01))

    assert trends.linear_trend(series, end=1949).slope_per_decade == pytest.approx(0)
    assert trends.linear_trend(series, start=1950).slope_per_decade == pytest.approx(0.1)


def test_linear_trend_rejects_short_series():
    with pytest.raises(ValueError):
        trends.linear_trend(make_series([1.0, 2.0]))


def test_find_breakpoint_locates_hinge():
    years = np.arange(1900, 2020)
    values = np.where(years < 1970, 0.0, 0.03 * (years - 1970))
    series = make_series(values)

    result = trends.find_breakpoint(series)

    assert result.year == 1970
    assert result.slope_before == pytest.approx(0, abs=1e-9)
    assert result.slope_after == pytest.approx(0.3)
    assert result.sse < result.sse_single_line


def test_rolling_trend_is_indexed_by_end_year():
    series = make_series(np.arange(40) * 0.01)

    result = trends.rolling_trend(series, window=30)

    assert result.index[0] == 1929
    assert result.index[-1] == 1939
    assert np.allclose(result, 0.1)


def test_decade_means_drops_incomplete_decades():
    series = make_series(np.ones(25), start=1990)  # 1990-2014

    result = trends.decade_means(series)

    assert list(result.index) == [1990, 2000]


def test_change_since_reference_period():
    series = make_series([0.0] * 21 + [1.0] * 10, start=1880)

    assert trends.change_since(series) == pytest.approx(1.0)
