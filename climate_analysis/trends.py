"""Statistical trend analysis for annual temperature anomaly series.

All functions take a ``pd.Series`` indexed by year. Slopes are reported in
degrees Celsius per decade.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats


@dataclass(frozen=True)
class Trend:
    start: int
    end: int
    slope_per_decade: float
    ci95_per_decade: float
    p_value: float
    r_squared: float

    @property
    def total_change(self) -> float:
        """Warming implied by the trend line over the whole period."""
        return self.slope_per_decade * (self.end - self.start) / 10


@dataclass(frozen=True)
class Breakpoint:
    year: int
    slope_before: float
    slope_after: float
    sse: float
    sse_single_line: float

    @property
    def acceleration(self) -> float:
        """How many times faster warming is after the breakpoint."""
        return self.slope_after / self.slope_before


@dataclass(frozen=True)
class SenTrend:
    start: int
    end: int
    slope_per_decade: float
    ci95_low: float
    ci95_high: float
    p_value: float

    @property
    def significant(self) -> bool:
        return self.p_value < 0.05


def sen_trend(series: pd.Series) -> SenTrend:
    """Theil-Sen slope with a Mann-Kendall significance test.

    Both are rank-based, so they are robust to outliers and skewed data. That
    makes them the standard choice for trends in counts of extreme events.
    """
    s = series.dropna()
    x = s.index.to_numpy(float)
    y = s.to_numpy(float)
    slope, _, low, high = stats.theilslopes(y, x, alpha=0.95)
    p_value = stats.kendalltau(x, y).pvalue
    return SenTrend(start=int(x[0]), end=int(x[-1]), slope_per_decade=slope * 10,
                    ci95_low=low * 10, ci95_high=high * 10, p_value=float(p_value))


def linear_trend(series: pd.Series, start: int | None = None,
                 end: int | None = None) -> Trend:
    """Ordinary least-squares trend with a 95% confidence interval."""
    s = series.loc[start:end].dropna()
    if len(s) < 3:
        raise ValueError("Need at least 3 values to fit a trend")

    result = stats.linregress(s.index.to_numpy(float), s.to_numpy(float))
    t_crit = stats.t.ppf(0.975, len(s) - 2)
    return Trend(
        start=int(s.index[0]),
        end=int(s.index[-1]),
        slope_per_decade=result.slope * 10,
        ci95_per_decade=t_crit * result.stderr * 10,
        p_value=result.pvalue,
        r_squared=result.rvalue ** 2,
    )


def rolling_trend(series: pd.Series, window: int = 30) -> pd.Series:
    """Trend (per decade) of each ``window``-year period, indexed by end year."""
    s = series.dropna()
    x = s.index.to_numpy(float)
    y = s.to_numpy(float)
    slopes = {
        int(x[i + window - 1]): np.polyfit(x[i:i + window], y[i:i + window], 1)[0] * 10
        for i in range(len(s) - window + 1)
    }
    return pd.Series(slopes, name=f"{window}yr_trend")


def find_breakpoint(series: pd.Series, min_segment: int = 15) -> Breakpoint:
    """Find the year where the warming rate changes most, via a hinge fit.

    Fits the continuous piecewise-linear model
        y = a + b*x + c*max(0, x - year)
    for every candidate year and keeps the one with the lowest squared error.
    The slope is ``b`` before the breakpoint and ``b + c`` after it.
    """
    s = series.dropna()
    x = s.index.to_numpy(float)
    y = s.to_numpy(float)

    single = np.column_stack([np.ones_like(x), x])
    sse_single = float(np.linalg.lstsq(single, y, rcond=None)[1][0])

    best = None
    for year in x[min_segment:-min_segment]:
        design = np.column_stack([np.ones_like(x), x, np.maximum(0, x - year)])
        coef, residuals, *_ = np.linalg.lstsq(design, y, rcond=None)
        sse = float(residuals[0])
        if best is None or sse < best[0]:
            best = (sse, int(year), coef)

    if best is None:
        raise ValueError("Series too short for the requested min_segment")

    sse, year, (_, b, c) = best
    return Breakpoint(year=year, slope_before=b * 10, slope_after=(b + c) * 10,
                      sse=sse, sse_single_line=sse_single)


def rolling_mean(series: pd.Series, window: int = 10) -> pd.Series:
    """Centred rolling mean; ends with too few years are left as NaN."""
    return series.rolling(window, center=True, min_periods=window).mean()


def warmest_years(series: pd.Series, n: int = 10) -> pd.Series:
    return series.sort_values(ascending=False).head(n)


def decade_means(series: pd.Series) -> pd.Series:
    """Mean anomaly per complete decade (e.g. 1990 = 1990-1999)."""
    decades = (series.index // 10) * 10
    grouped = series.groupby(decades)
    return grouped.mean()[grouped.count() == 10]


def change_since(series: pd.Series, reference: tuple[int, int] = (1880, 1900),
                 recent_years: int = 10) -> float:
    """Warming of the most recent ``recent_years`` relative to a reference period.

    The default 1880-1900 reference is a common proxy for pre-industrial levels.
    """
    ref = series.loc[reference[0]:reference[1]].mean()
    return float(series.iloc[-recent_years:].mean() - ref)
