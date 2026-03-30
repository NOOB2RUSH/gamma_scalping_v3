import pytest
from core.signal import (
    calculate_option_price,
    calculate_greeks_for_option,
    calculate_position_greeks,
    check_open_signals,
    check_close_signals,
    should_hedge,
)


class TestCalculateOptionPrice:
    def test_mid_price(self):
        assert calculate_option_price(0.10, 0.12) == 0.11


class TestCalculateGreeksForOption:
    def test_returns_greeks_dict(self):
        greeks = calculate_greeks_for_option(
            s=100, k=100, t=0.5, r=0.025, sigma=0.2, option_type="C"
        )
        assert "delta" in greeks
        assert "gamma" in greeks
        assert "vega" in greeks
        assert "theta" in greeks


class TestCalculatePositionGreeks:
    def test_combines_call_and_put(self):
        call = {"delta": 0.5, "gamma": 0.02, "vega": 0.1, "theta": -0.05}
        put = {"delta": -0.5, "gamma": 0.02, "vega": 0.1, "theta": -0.05}
        pos = calculate_position_greeks(call, put, contract_multiplier=10000)
        assert pos["delta"] == 0.0
        assert pos["gamma"] == 400.0


class TestCheckOpenSignals:
    def test_high_iv_percentile_blocks_opening(self):
        ok, reason = check_open_signals(0.20, 100000, 5000, 5000, 0.15, 2000)
        assert not ok
        assert "IV percentile" in reason

    def test_no_cash_blocks_opening(self):
        ok, reason = check_open_signals(0.10, 0, 5000, 5000, 0.15, 2000)
        assert not ok
        assert "cash" in reason

    def test_low_volume_blocks_opening(self):
        ok, reason = check_open_signals(0.10, 100000, 100, 5000, 0.15, 2000)
        assert not ok
        assert "liquidity" in reason

    def test_all_conditions_met_opens_position(self):
        ok, reason = check_open_signals(0.10, 100000, 5000, 5000, 0.15, 2000)
        assert ok
        assert reason == "OK"


class TestCheckCloseSignals:
    def test_high_iv_closes_position(self):
        ok, reason = check_close_signals(0.90, 20, 5, 0.85, 5, 30)
        assert ok
        assert "IV percentile" in reason

    def test_near_expiry_closes_position(self):
        ok, reason = check_close_signals(0.50, 3, 5, 0.85, 5, 30)
        assert ok
        assert "expiry" in reason

    def test_max_holding_days_closes_position(self):
        ok, reason = check_close_signals(0.50, 20, 35, 0.85, 5, 30)
        assert ok
        assert "holding days" in reason

    def test_no_signal_keeps_position(self):
        ok, reason = check_close_signals(0.50, 20, 5, 0.85, 5, 30)
        assert not ok
        assert "No close signal" in reason


class TestShouldHedge:
    def test_small_delta_no_hedge(self):
        assert not should_hedge(0.03, 0.05)

    def test_large_delta_hedges(self):
        assert should_hedge(0.10, 0.05)

    def test_negative_large_delta_hedges(self):
        assert should_hedge(-0.10, 0.05)
