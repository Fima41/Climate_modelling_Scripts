from climate_analysis import data

SAMPLE = """Land-Ocean: Global Means
Year,Jan,Feb,Mar,Apr,May,Jun,Jul,Aug,Sep,Oct,Nov,Dec,J-D,D-N,DJF,MAM,JJA,SON
1880,-.19,-.26,-.10,-.17,-.11,-.22,-.19,-.11,-.15,-.24,-.23,-.18,-.18,***,***,-.13,-.17,-.21
1881,-.20,-.15,.03,.05,.05,-.19,.00,-.04,-.16,-.22,-.19,-.08,-.09,-.10,-.18,.04,-.08,-.19
2026,1.09,1.25,1.32,1.17,1.13,1.18,1.25,1.40,***,***,***,***,***,***,1.13,1.21,1.28,***
"""


def test_parse_gistemp_handles_title_and_missing_values():
    df = data.parse_gistemp(SAMPLE)

    assert list(df.index) == [1880, 1881, 2026]
    assert df.loc[1880, "Jan"] == -0.19
    assert df[["D-N", "DJF"]].loc[1880].isna().all()


def test_annual_series_drops_incomplete_years():
    annual = data.annual_series(data.parse_gistemp(SAMPLE))

    assert list(annual.index) == [1880, 1881]
    assert annual.loc[1881] == -0.09
