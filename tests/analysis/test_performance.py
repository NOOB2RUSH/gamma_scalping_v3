import pytest
import pandas as pd
from analysis.performance import PerformanceAnalyzer


class TestPerformanceAnalyzerInit:
    def test_initializes_with_empty_trades(self):
        analyzer = PerformanceAnalyzer()
        assert analyzer.trades == []
        assert analyzer.equity_curve == []


class TestSummaryStats:
    def test_total_trades_counts_completed_positions(self):
        analyzer = PerformanceAnalyzer()
        analyzer.trades = [
            {"trade_id": "001", "is_closed": True, "net_pnl": 100.0},
            {"trade_id": "002", "is_closed": False, "net_pnl": 0.0},
            {"trade_id": "003", "is_closed": True, "net_pnl": -50.0},
        ]
        result = analyzer.compute_summary()
        assert result["total_trades"] == 2

    def test_win_count_and_loss_count(self):
        analyzer = PerformanceAnalyzer()
        analyzer.trades = [
            {"trade_id": "001", "is_closed": True, "net_pnl": 100.0},
            {"trade_id": "002", "is_closed": True, "net_pnl": -30.0},
            {"trade_id": "003", "is_closed": True, "net_pnl": 200.0},
            {"trade_id": "004", "is_closed": True, "net_pnl": -10.0},
        ]
        result = analyzer.compute_summary()
        assert result["winning_trades"] == 2
        assert result["losing_trades"] == 2

    def test_win_rate(self):
        analyzer = PerformanceAnalyzer()
        analyzer.trades = [
            {"trade_id": "001", "is_closed": True, "net_pnl": 100.0},
            {"trade_id": "002", "is_closed": True, "net_pnl": -30.0},
        ]
        result = analyzer.compute_summary()
        assert result["win_rate"] == 0.5

    def test_total_premium_net(self):
        analyzer = PerformanceAnalyzer()
        analyzer.trades = [
            {
                "trade_id": "001",
                "is_closed": True,
                "open_cost": 1900.0,
                "close_proceeds": 2000.0,
                "net_pnl": 100.0,
            },
            {
                "trade_id": "002",
                "is_closed": True,
                "open_cost": 2000.0,
                "close_proceeds": 1800.0,
                "net_pnl": -200.0,
            },
        ]
        result = analyzer.compute_summary()
        assert result["total_premium_net"] == pytest.approx(100.0 + (-200.0))

    def test_total_hedge_pnl(self):
        analyzer = PerformanceAnalyzer()
        analyzer.trades = [
            {
                "trade_id": "001",
                "is_closed": True,
                "net_pnl": 100.0,
                "hedge_pnl": 100.0,
                "hedge_records": [
                    {"date": "2024-12-17", "qty": -4000, "price": 2.55, "pnl": 150.0},
                    {"date": "2024-12-18", "qty": 4000, "price": 2.54, "pnl": -50.0},
                ],
            },
        ]
        result = analyzer.compute_summary()
        assert result["total_hedge_pnl"] == pytest.approx(150.0 + (-50.0))

    def test_total_realized_pnl(self):
        analyzer = PerformanceAnalyzer()
        analyzer.trades = [
            {"trade_id": "001", "is_closed": True, "net_pnl": 100.0},
            {"trade_id": "002", "is_closed": True, "net_pnl": -40.0},
        ]
        result = analyzer.compute_summary()
        assert result["total_realized_pnl"] == pytest.approx(60.0)

    def test_avg_win_and_avg_loss(self):
        analyzer = PerformanceAnalyzer()
        analyzer.trades = [
            {"trade_id": "001", "is_closed": True, "net_pnl": 100.0},
            {"trade_id": "002", "is_closed": True, "net_pnl": 200.0},
            {"trade_id": "003", "is_closed": True, "net_pnl": -30.0},
            {"trade_id": "004", "is_closed": True, "net_pnl": -70.0},
        ]
        result = analyzer.compute_summary()
        assert result["avg_win"] == pytest.approx(150.0)
        assert result["avg_loss"] == pytest.approx(-50.0)


class TestEquityCurve:
    def test_equity_curve_has_date_and_equity_columns(self):
        analyzer = PerformanceAnalyzer()
        analyzer.equity_curve = [
            {"date": "2024-12-16", "equity": 1_000_000.0, "daily_pnl": 0.0},
            {"date": "2024-12-17", "equity": 1_000_100.0, "daily_pnl": 100.0},
        ]
        result = analyzer.compute_equity_curve_stats()
        assert "start_equity" in result
        assert "end_equity" in result
        assert "total_return_pct" in result

    def test_total_return_pct(self):
        analyzer = PerformanceAnalyzer()
        analyzer.equity_curve = [
            {"date": "2024-12-16", "equity": 1_000_000.0, "daily_pnl": 0.0},
            {"date": "2024-12-17", "equity": 1_010_000.0, "daily_pnl": 10_000.0},
        ]
        result = analyzer.compute_equity_curve_stats()
        assert result["total_return_pct"] == pytest.approx(0.01)
