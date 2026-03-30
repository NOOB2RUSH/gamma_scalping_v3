import pytest
import pandas as pd
import numpy as np
from core.vol_cone import (
    dte_to_tenor_bucket,
    compute_iv_percentile,
    build_vol_cone,
    current_iv_percentile,
    TENOR_BUCKETS,
    PERCENTILES,
    MIN_LOOKBACK_DAYS,
)


class TestDteToTenorBucket:
    def test_7_day_bucket(self):
        assert dte_to_tenor_bucket(7) == 7

    def test_14_day_bucket(self):
        assert dte_to_tenor_bucket(14) == 14

    def test_30_day_bucket(self):
        assert dte_to_tenor_bucket(30) == 30

    def test_out_of_range(self):
        assert dte_to_tenor_bucket(1) is None
        assert dte_to_tenor_bucket(200) is None


class TestComputeIvPercentile:
    def test_iv_in_middle_returns_50(self):
        historical = [0.10, 0.15, 0.20, 0.25, 0.30]
        pct = compute_iv_percentile(0.20, historical)
        assert 0.4 < pct < 0.6

    def test_low_iv_returns_low_percentile(self):
        historical = [0.10, 0.15, 0.20, 0.25, 0.30]
        pct = compute_iv_percentile(0.10, historical)
        assert pct == 0.1

    def test_high_iv_returns_high_percentile(self):
        historical = [0.10, 0.15, 0.20, 0.25, 0.30]
        pct = compute_iv_percentile(0.30, historical)
        assert pct == 0.9

    def test_empty_history_returns_50(self):
        pct = compute_iv_percentile(0.20, [])
        assert pct == 0.5


class TestBuildVolCone:
    def test_cone_structure(self):
        dates = pd.date_range("2024-06-01", periods=130, freq="B")
        data = []
        for d in dates:
            for tenor in [7, 14, 30, 60, 90]:
                dte = tenor
                data.append(
                    {
                        "date": d.strftime("%Y-%m-%d"),
                        "dte": dte,
                        "iv": 0.15 + np.random.uniform(-0.03, 0.03),
                        "strike_price": 2.55,
                        "option_type": "C",
                    }
                )
        df = pd.DataFrame(data)
        cone = build_vol_cone("2024-12-16", df, lookback_days=120)
        assert 7 in cone
        assert 30 in cone
        assert 90 in cone
        assert 90 in cone[30]
        assert 50 in cone[30]

    def test_missing_data_returns_empty(self):
        df = pd.DataFrame({"date": [], "dte": [], "iv": []})
        cone = build_vol_cone("2024-12-16", df)
        assert cone == {}

    def test_returns_empty_when_history_under_60_days(self):
        dates = pd.date_range("2024-12-01", periods=MIN_LOOKBACK_DAYS - 1, freq="B")
        data = []
        for d in dates:
            for tenor in [30]:
                data.append(
                    {
                        "date": d.strftime("%Y-%m-%d"),
                        "dte": tenor,
                        "iv": 0.15,
                        "strike_price": 2.55,
                        "option_type": "C",
                    }
                )
        df = pd.DataFrame(data)
        cone = build_vol_cone("2024-12-16", df, lookback_days=120)
        assert cone == {}


class TestCurrentIvPercentile:
    def test_percentile_computed(self):
        dates = pd.date_range("2024-06-01", periods=130, freq="B")
        data = []
        for d in dates:
            for tenor in [7, 14, 30, 60, 90]:
                dte = tenor + 5
                data.append(
                    {
                        "date": d.strftime("%Y-%m-%d"),
                        "dte": dte,
                        "iv": 0.15 + np.random.uniform(-0.03, 0.03),
                        "strike_price": 2.55,
                        "option_type": "C",
                    }
                )
        df = pd.DataFrame(data)
        pct = current_iv_percentile(
            0.15, "2024-12-16", df, target_tenor=30, lookback_days=120
        )
        assert pct is not None
        assert 0.0 <= pct <= 1.0

    def test_returns_none_when_history_under_60_days(self):
        dates = pd.date_range("2024-12-01", periods=MIN_LOOKBACK_DAYS - 1, freq="B")
        data = []
        for d in dates:
            for tenor in [60]:
                data.append(
                    {
                        "date": d.strftime("%Y-%m-%d"),
                        "dte": tenor + 5,
                        "iv": 0.15,
                        "strike_price": 2.55,
                        "option_type": "C",
                    }
                )
        df = pd.DataFrame(data)
        pct = current_iv_percentile(
            0.15, "2024-12-16", df, target_tenor=30, lookback_days=120
        )
        assert pct is None
