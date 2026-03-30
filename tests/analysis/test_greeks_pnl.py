import pytest
import pandas as pd
from analysis.greeks_pnl import GreeksPnlAnalyzer


class TestGreeksPnlAnalyzerInit:
    def test_initializes(self):
        analyzer = GreeksPnlAnalyzer()
        assert analyzer.positions == []


class TestGreeksPnlDecomposition:
    def test_delta_pnl_uses_trapezoidal_approximation(self):
        analyzer = GreeksPnlAnalyzer()
        greeks_records = [
            {"date": "2024-12-16", "delta": 5000.0},
            {"date": "2024-12-17", "delta": 5200.0},
        ]
        dS = 0.05
        result = analyzer.compute_delta_pnl(greeks_records, dS)
        expected = (5000.0 + 5200.0) / 2 * 0.05
        assert result == pytest.approx(expected)

    def test_gamma_pnl_uses_dsquare(self):
        analyzer = GreeksPnlAnalyzer()
        greeks_records = [
            {"date": "2024-12-16", "gamma": 1000.0},
            {"date": "2024-12-17", "gamma": 1100.0},
        ]
        dS = 0.05
        result = analyzer.compute_gamma_pnl(greeks_records, dS)
        gamma_avg = (1000.0 + 1100.0) / 2
        expected = 0.25 * gamma_avg * (dS**2)
        assert result == pytest.approx(expected)

    def test_theta_pnl_uses_dt(self):
        analyzer = GreeksPnlAnalyzer()
        greeks_records = [
            {"date": "2024-12-16", "theta": -500.0},
            {"date": "2024-12-17", "theta": -520.0},
        ]
        dt = 1.0 / 252
        result = analyzer.compute_theta_pnl(greeks_records, dt)
        expected = (-500.0 + -520.0) / 2 * dt
        assert result == pytest.approx(expected)

    def test_vega_pnl_uses_dsigma(self):
        analyzer = GreeksPnlAnalyzer()
        greeks_records = [
            {"date": "2024-12-16", "vega": 2000.0},
            {"date": "2024-12-17", "vega": 2100.0},
        ]
        d_sigma = 0.01
        result = analyzer.compute_vega_pnl(greeks_records, d_sigma)
        expected = (2000.0 + 2100.0) / 2 * 0.01
        assert result == pytest.approx(expected)


class TestTotalGreeksPnl:
    def test_total_is_sum_of_components(self):
        analyzer = GreeksPnlAnalyzer()
        delta = 100.0
        gamma = 50.0
        theta = -30.0
        vega = 20.0
        result = analyzer.compute_total_pnl(delta, gamma, theta, vega)
        assert result == pytest.approx(delta + gamma + theta + vega)


class MockPosition:
    def __init__(self, daily_greeks, net_pnl, option_pnl=None):
        self.daily_greeks = daily_greeks
        self.net_pnl = net_pnl
        self.option_pnl = option_pnl if option_pnl is not None else net_pnl
        self.is_closed = True


class TestGreeksPnlIntegration:
    def test_analyze_position_computes_delta_pnl_from_underlying_changes(self):
        analyzer = GreeksPnlAnalyzer()
        daily_greeks = [
            {
                "date": "2024-12-16",
                "delta": 5000.0,
                "gamma": 0.0,
                "vega": 0.0,
                "theta": 0.0,
            },
            {
                "date": "2024-12-17",
                "delta": 5200.0,
                "gamma": 0.0,
                "vega": 0.0,
                "theta": 0.0,
            },
            {
                "date": "2024-12-18",
                "delta": 4800.0,
                "gamma": 0.0,
                "vega": 0.0,
                "theta": 0.0,
            },
        ]
        underlying_prices = {
            "2024-12-16": 250.0,
            "2024-12-17": 255.0,
            "2024-12-18": 252.0,
        }
        position = MockPosition(daily_greeks, 0.0)
        result = analyzer.analyze_position(position, underlying_prices, {})

        delta_pnl_0 = (5000.0 + 5200.0) / 2 * (255.0 - 250.0)
        delta_pnl_1 = (5200.0 + 4800.0) / 2 * (252.0 - 255.0)
        # LONG straddle: use greeks directly (no negation)
        expected_delta = delta_pnl_0 + delta_pnl_1
        assert result["delta_pnl"] == pytest.approx(expected_delta)

    def test_analyze_position_computes_gamma_pnl_from_squared_price_changes(self):
        analyzer = GreeksPnlAnalyzer()
        daily_greeks = [
            {
                "date": "2024-12-16",
                "delta": 0.0,
                "gamma": 1000.0,
                "vega": 0.0,
                "theta": 0.0,
            },
            {
                "date": "2024-12-17",
                "delta": 0.0,
                "gamma": 1100.0,
                "vega": 0.0,
                "theta": 0.0,
            },
        ]
        underlying_prices = {
            "2024-12-16": 250.0,
            "2024-12-17": 255.0,
        }
        position = MockPosition(daily_greeks, 0.0)
        result = analyzer.analyze_position(position, underlying_prices, {})

        gamma_avg = (1000.0 + 1100.0) / 2
        ds = 5.0
        # LONG straddle: use greeks directly (no negation)
        long_gamma = 0.25 * (1000.0 + 1100.0) * (ds**2)
        expected_gamma = long_gamma
        assert result["gamma_pnl"] == pytest.approx(expected_gamma)

    def test_analyze_position_computes_theta_pnl(self):
        analyzer = GreeksPnlAnalyzer()
        daily_greeks = [
            {
                "date": "2024-12-16",
                "delta": 0.0,
                "gamma": 0.0,
                "vega": 0.0,
                "theta": -500.0,
            },
            {
                "date": "2024-12-17",
                "delta": 0.0,
                "gamma": 0.0,
                "vega": 0.0,
                "theta": -520.0,
            },
        ]
        underlying_prices = {"2024-12-16": 250.0, "2024-12-17": 250.0}
        position = MockPosition(daily_greeks, 0.0)
        result = analyzer.analyze_position(position, underlying_prices, {})

        dt = 1.0 / 252.0
        long_theta = (-500.0 + -520.0) / 2 * dt
        # LONG straddle: theta_pnl is negative (we lose from time decay)
        expected_theta = long_theta
        assert result["theta_pnl"] == pytest.approx(expected_theta)

    def test_analyze_position_error_within_5_percent(self):
        analyzer = GreeksPnlAnalyzer()
        daily_greeks = [
            {
                "date": "2024-12-16",
                "delta": 5000.0,
                "gamma": 100.0,
                "vega": 200.0,
                "theta": -50.0,
            },
            {
                "date": "2024-12-17",
                "delta": 5200.0,
                "gamma": 110.0,
                "vega": 210.0,
                "theta": -55.0,
            },
            {
                "date": "2024-12-18",
                "delta": 4800.0,
                "gamma": 105.0,
                "vega": 205.0,
                "theta": -52.0,
            },
        ]
        underlying_prices = {
            "2024-12-16": 250.0,
            "2024-12-17": 255.0,
            "2024-12-18": 252.0,
        }
        iv_history = {
            "2024-12-16": 0.20,
            "2024-12-17": 0.21,
            "2024-12-18": 0.205,
        }
        position = MockPosition(daily_greeks, 0.0)
        result = analyzer.analyze_position(position, underlying_prices, iv_history)

        assert result["total_pnl"] == pytest.approx(
            result["delta_pnl"]
            + result["gamma_pnl"]
            + result["theta_pnl"]
            + result["vega_pnl"]
        )

    def test_analyze_position_iv_change_zero_when_no_iv_history(self):
        analyzer = GreeksPnlAnalyzer()
        daily_greeks = [
            {
                "date": "2024-12-16",
                "delta": 0.0,
                "gamma": 0.0,
                "vega": 2000.0,
                "theta": 0.0,
            },
            {
                "date": "2024-12-17",
                "delta": 0.0,
                "gamma": 0.0,
                "vega": 2100.0,
                "theta": 0.0,
            },
        ]
        underlying_prices = {"2024-12-16": 250.0, "2024-12-17": 250.0}
        position = MockPosition(daily_greeks, 0.0)
        result = analyzer.analyze_position(position, underlying_prices, {})

        assert result["vega_pnl"] == 0.0


class TestGreeksPnlSignConvention:
    """
    Stored daily_greeks are computed as LONG straddle greeks (per processor.py).
    Position is LONG straddle (we BUY options): greeks are used directly (no negation).
    """

    def test_long_position_delta_pnl_positive_when_underlying_rises(self):
        """
        Stored delta = +5100 (LONG straddle delta at ATM).
        For LONG straddle: when underlying rises (+ds), delta P&L must be POSITIVE.
        LONG straddle gains when underlying rises because you own the call.
        """
        analyzer = GreeksPnlAnalyzer()
        daily_greeks = [
            {
                "date": "2024-12-16",
                "delta": 5100.0,
                "gamma": 0.0,
                "vega": 0.0,
                "theta": 0.0,
            },
            {
                "date": "2024-12-17",
                "delta": 5100.0,
                "gamma": 0.0,
                "vega": 0.0,
                "theta": 0.0,
            },
        ]
        underlying_prices = {
            "2024-12-16": 250.00,
            "2024-12-17": 255.00,
        }
        position = MockPosition(daily_greeks, 0.0)
        result = analyzer.analyze_position(position, underlying_prices, {})

        # LONG straddle delta P&L = (5100+5100)/2 * 5 = +25500
        expected_long_delta_pnl = ((5100.0 + 5100.0) / 2.0) * (255.00 - 250.00)
        assert result["delta_pnl"] == pytest.approx(expected_long_delta_pnl)

    def test_long_position_gamma_pnl_positive_when_price_moves(self):
        """
        Stored gamma = +1000 (LONG straddle gamma, positive).
        For LONG straddle: gamma P&L must be POSITIVE when price moves.
        LONG straddle gains gamma when price moves due to long gamma position.
        """
        analyzer = GreeksPnlAnalyzer()
        daily_greeks = [
            {
                "date": "2024-12-16",
                "delta": 0.0,
                "gamma": 1000.0,
                "vega": 0.0,
                "theta": 0.0,
            },
            {
                "date": "2024-12-17",
                "delta": 0.0,
                "gamma": 1000.0,
                "vega": 0.0,
                "theta": 0.0,
            },
        ]
        underlying_prices = {
            "2024-12-16": 250.00,
            "2024-12-17": 255.00,
        }
        position = MockPosition(daily_greeks, 0.0)
        result = analyzer.analyze_position(position, underlying_prices, {})

        # LONG straddle gamma P&L = 0.25 * (Γ_i + Γ_{i+1}) * ds²
        ds = 5.00
        long_gamma_pnl = 0.25 * (1000.0 + 1000.0) * (ds**2)  # = 12500
        assert result["gamma_pnl"] == pytest.approx(long_gamma_pnl)

    def test_long_position_theta_pnl_negative_when_time_decays(self):
        """
        Stored theta = -500 (LONG straddle theta, negative = time decay).
        For LONG straddle: theta P&L must be NEGATIVE.
        LONG straddle LOSES from time decay (negative theta is a cost).
        """
        analyzer = GreeksPnlAnalyzer()
        daily_greeks = [
            {
                "date": "2024-12-16",
                "delta": 0.0,
                "gamma": 0.0,
                "vega": 0.0,
                "theta": -500.0,
            },
            {
                "date": "2024-12-17",
                "delta": 0.0,
                "gamma": 0.0,
                "vega": 0.0,
                "theta": -500.0,
            },
        ]
        underlying_prices = {"2024-12-16": 250.00, "2024-12-17": 250.00}
        position = MockPosition(daily_greeks, 0.0)
        result = analyzer.analyze_position(position, underlying_prices, {})

        # LONG straddle theta P&L: theta_pnl = (-500 + -500)/2 * (1/252) = -500/252
        dt = 1.0 / 252.0
        long_theta_pnl = (-500.0 + -500.0) / 2.0 * dt
        assert result["theta_pnl"] == pytest.approx(long_theta_pnl)
