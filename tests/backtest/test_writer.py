import os
import tempfile
import shutil
from pathlib import Path

import pytest

from backtest.writer import ResultWriter


class TestResultWriter:
    """Test ResultWriter output functionality."""

    @pytest.fixture
    def temp_results_dir(self):
        """Create a temporary results directory."""
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        shutil.rmtree(tmpdir)

    @pytest.fixture
    def writer(self, temp_results_dir):
        return ResultWriter(temp_results_dir)

    def test_write_config_creates_yaml_file(self, writer, temp_results_dir):
        """Config dict is written to config.yaml."""
        config_dict = {
            "initial_capital": 1000000,
            "open_threshold": 0.15,
            "lookback_days": 120,
        }
        writer.write_config(config_dict)

        config_path = Path(temp_results_dir) / "config.yaml"
        assert config_path.exists()
        content = config_path.read_text()
        assert "initial_capital: 1000000" in content
        assert "open_threshold: 0.15" in content

    def test_write_trade_creates_trades_subdir_and_csv(self, writer, temp_results_dir):
        """Trade dict is written to trades/trade_XXX.csv."""
        position_dict = {
            "trade_id": "001",
            "open_date": "2024-12-16",
            "close_date": "2025-01-15",
            "strike_price": 2.65,
            "maturity_date": "2025-01-22",
            "open_cost": 5000.0,
            "close_proceeds": 6500.0,
            "net_pnl": 1500.0,
            "is_closed": True,
            "net_hedge_qty": 0,
            "hedge_records": [],
            "daily_greeks": [
                {
                    "date": "2024-12-16",
                    "delta": 0.5,
                    "gamma": 1000.0,
                    "vega": 500.0,
                    "theta": -100.0,
                },
            ],
        }
        writer.write_trade(position_dict)

        trade_path = Path(temp_results_dir) / "trades" / "trade_001.csv"
        assert trade_path.exists()
        content = trade_path.read_text()
        assert "trade_id,open_date,close_date" in content
        assert "001,2024-12-16,2025-01-15" in content
        assert "net_pnl,is_closed" in content

    def test_write_summary_creates_summary_csv(self, writer, temp_results_dir):
        """Summary dict is written to summary.csv."""
        summary = {
            "total_trades": 10,
            "winning_trades": 6,
            "losing_trades": 4,
            "total_premium_net": 5000.0,
            "total_hedge_pnl": -200.0,
            "total_realized_pnl": 4800.0,
            "win_rate": 0.6,
            "avg_win": 1000.0,
            "avg_loss": -500.0,
        }
        writer.write_summary(summary)

        summary_path = Path(temp_results_dir) / "summary.csv"
        assert summary_path.exists()
        content = summary_path.read_text()
        assert "total_trades,winning_trades,losing_trades" in content
        assert "10,6,4" in content
        assert "total_realized_pnl,win_rate,avg_win,avg_loss" in content

    def test_write_equity_curve_creates_equity_curve_csv(
        self, writer, temp_results_dir
    ):
        """Equity curve list is written to equity_curve.csv."""
        equity_curve = [
            {
                "date": "2024-12-16",
                "equity": 1000000.0,
                "daily_pnl": 0.0,
                "cumulative_pnl": 0.0,
            },
            {
                "date": "2024-12-17",
                "equity": 1000500.0,
                "daily_pnl": 500.0,
                "cumulative_pnl": 500.0,
            },
        ]
        writer.write_equity_curve(equity_curve)

        eq_path = Path(temp_results_dir) / "equity_curve.csv"
        assert eq_path.exists()
        content = eq_path.read_text()
        assert "date,equity,daily_pnl,cumulative_pnl" in content
        assert "2024-12-16,1000000.0,0.0,0.0" in content
        assert "2024-12-17,1000500.0,500.0,500.0" in content

    def test_write_performance_csv_creates_performance_csv(
        self, writer, temp_results_dir
    ):
        """Performance data is written to performance.csv."""
        equity_curve = [
            {
                "date": "2024-12-16",
                "equity": 1000000.0,
                "daily_pnl": 0.0,
                "cumulative_pnl": 0.0,
            },
            {
                "date": "2024-12-17",
                "equity": 1000500.0,
                "daily_pnl": 500.0,
                "cumulative_pnl": 500.0,
            },
        ]
        writer.write_performance_csv(equity_curve)

        perf_path = Path(temp_results_dir) / "performance.csv"
        assert perf_path.exists()
        content = perf_path.read_text()
        assert "date,delta_pnl,gamma_pnl,theta_pnl,vega_pnl" in content

    def test_write_daily_debug_log_creates_logs_subdir_and_log(
        self, writer, temp_results_dir
    ):
        """Debug lines are appended to logs/daily_debug.log."""
        date = "2024-12-20"
        debug_lines = [
            "=== 2024-12-20 ===",
            "[ATM Candidates]",
            "Strike=2.650, Type=C, IV=0.1823, Percentile=12.5%",
            "",
            "[IV Percentile by Tenor]",
            "7d:  8.2% (Open threshold: 15%)",
            "30d: 12.5% <-- Target tenor",
            "",
            "[Positions]",
            "trade_id=001, strike=2.650, delta=0.23, gamma=1234.5, vega=567.8, theta=-89.2",
            "Action: No hedge needed (|delta|=0.23 < 0.05)",
        ]
        writer.write_daily_debug_log(date, debug_lines)

        log_path = Path(temp_results_dir) / "logs" / "daily_debug.log"
        assert log_path.exists()
        content = log_path.read_text()
        assert "=== 2024-12-20 ===" in content
        assert "Strike=2.650, Type=C, IV=0.1823, Percentile=12.5%" in content
        assert "trade_id=001, strike=2.650, delta=0.23" in content

    def test_multiple_trades_create_separate_files(self, writer, temp_results_dir):
        """Multiple trades are written to separate files."""
        for i in range(1, 4):
            position_dict = {
                "trade_id": f"{i:03d}",
                "open_date": "2024-12-16",
                "close_date": "2025-01-15",
                "strike_price": 2.65,
                "maturity_date": "2025-01-22",
                "open_cost": 5000.0,
                "close_proceeds": 6500.0,
                "net_pnl": 1500.0,
                "is_closed": True,
                "net_hedge_qty": 0,
                "hedge_records": [],
                "daily_greeks": [],
            }
            writer.write_trade(position_dict)

        trades_dir = Path(temp_results_dir) / "trades"
        assert (trades_dir / "trade_001.csv").exists()
        assert (trades_dir / "trade_002.csv").exists()
        assert (trades_dir / "trade_003.csv").exists()
