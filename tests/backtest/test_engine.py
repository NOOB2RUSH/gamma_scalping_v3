import pytest
import os
from unittest.mock import MagicMock, patch
from config import Config, default_config
from portfolio.portfolio import Portfolio
from portfolio.position import OptionLeg


class TestBacktestEngineInit:
    """Test BacktestEngine initialization."""

    def test_engine_initializes_with_config_and_data_interface(self):
        """Engine should initialize with config and data interface."""
        from backtest.engine import BacktestEngine

        cfg = default_config()
        mock_di = MagicMock()
        mock_di.trading_dates = ["2024-12-16", "2024-12-17"]

        engine = BacktestEngine(cfg, mock_di)
        assert engine.config is cfg
        assert engine.data_interface is mock_di
        assert engine.portfolio is not None
        assert engine.portfolio.initial_capital == cfg.initial_capital

    def test_engine_has_empty_results_before_run(self):
        """Engine results should be empty dict before run()."""
        from backtest.engine import BacktestEngine

        cfg = default_config()
        mock_di = MagicMock()
        mock_di.trading_dates = ["2024-12-16"]

        engine = BacktestEngine(cfg, mock_di)
        assert engine.results == {}


class TestBacktestEngineRun:
    """Test BacktestEngine.run() behavior."""

    def test_run_processes_all_trading_dates(self):
        """Engine should iterate over all trading dates from data interface."""
        from backtest.engine import BacktestEngine

        cfg = default_config()
        mock_di = MagicMock()
        dates = ["2024-12-16", "2024-12-17", "2024-12-18"]
        mock_di.trading_dates = dates
        mock_di.get_underlying_price.return_value = 2.55
        mock_di.get_options.return_value = MagicMock(empty=True)
        mock_di.get_atm_options.return_value = (None, None)

        engine = BacktestEngine(cfg, mock_di)
        engine.run()

        assert len(engine.processed_dates) == 3

    def test_run_stops_early_with_no_dates(self):
        """Engine should handle empty trading dates gracefully."""
        from backtest.engine import BacktestEngine

        cfg = default_config()
        mock_di = MagicMock()
        mock_di.trading_dates = []

        engine = BacktestEngine(cfg, mock_di)
        engine.run()
        assert engine.processed_dates == []


class TestBacktestResults:
    """Test that run() produces expected result structure."""

    def test_results_contains_trade_log(self):
        """Results should contain a list of completed trades after run()."""
        from backtest.engine import BacktestEngine

        cfg = default_config()
        mock_di = MagicMock()
        mock_di.trading_dates = ["2024-12-16", "2024-12-17"]
        mock_di.get_underlying_price.return_value = 2.55
        mock_di.get_options.return_value = MagicMock(empty=True)
        mock_di.get_atm_options.return_value = (None, None)

        engine = BacktestEngine(cfg, mock_di)
        engine.run()

        assert "trades" in engine.results
        assert isinstance(engine.results["trades"], list)

    def test_results_contains_equity_curve(self):
        """Results should contain equity curve after run()."""
        from backtest.engine import BacktestEngine

        cfg = default_config()
        mock_di = MagicMock()
        mock_di.trading_dates = ["2024-12-16"]
        mock_di.get_underlying_price.return_value = 2.55
        mock_di.get_options.return_value = MagicMock(empty=True)
        mock_di.get_atm_options.return_value = (None, None)

        engine = BacktestEngine(cfg, mock_di)
        engine.run()

        assert "equity_curve" in engine.results
        assert isinstance(engine.results["equity_curve"], list)

    def test_results_contains_config_dict(self):
        """Results should contain config dict after run()."""
        from backtest.engine import BacktestEngine

        cfg = default_config()
        mock_di = MagicMock()
        mock_di.trading_dates = ["2024-12-16"]
        mock_di.get_underlying_price.return_value = 2.55
        mock_di.get_options.return_value = MagicMock(empty=True)
        mock_di.get_atm_options.return_value = (None, None)

        engine = BacktestEngine(cfg, mock_di)
        engine.run()

        assert "config" in engine.results
        assert engine.results["config"]["initial_capital"] == cfg.initial_capital

    def test_equity_curve_entries_have_required_fields(self):
        """Each equity curve entry should have date, equity, daily_pnl, cumulative_pnl."""
        from backtest.engine import BacktestEngine

        cfg = default_config()
        mock_di = MagicMock()
        mock_di.trading_dates = ["2024-12-16", "2024-12-17"]
        mock_di.get_underlying_price.return_value = 2.55
        mock_di.get_options.return_value = MagicMock(empty=True)
        mock_di.get_atm_options.return_value = (None, None)

        engine = BacktestEngine(cfg, mock_di)
        engine.run()

        for entry in engine.results["equity_curve"]:
            assert "date" in entry
            assert "equity" in entry
            assert "daily_pnl" in entry
            assert "cumulative_pnl" in entry

    def test_daily_pnl_is_difference_of_equity(self):
        """daily_pnl for day N should equal equity_N - equity_(N-1)."""
        from backtest.engine import BacktestEngine

        cfg = default_config()
        mock_di = MagicMock()
        dates = ["2024-12-16", "2024-12-17", "2024-12-18"]
        mock_di.trading_dates = dates
        mock_di.get_underlying_price.return_value = 2.55
        mock_di.get_options.return_value = MagicMock(empty=True)
        mock_di.get_atm_options.return_value = (None, None)

        engine = BacktestEngine(cfg, mock_di)
        engine.run()

        curve = engine.results["equity_curve"]
        # First day has 0 daily_pnl (no previous day)
        assert curve[0]["daily_pnl"] == 0.0
        # Second day: equity_1 - equity_0
        expected_daily_pnl = curve[1]["equity"] - curve[0]["equity"]
        assert abs(curve[1]["daily_pnl"] - expected_daily_pnl) < 0.01

    def test_run_calls_processor_process_day_each_date(self):
        """Engine should call processor.process_day() for each trading date."""
        from backtest.engine import BacktestEngine

        cfg = default_config()
        mock_di = MagicMock()
        dates = ["2024-12-16", "2024-12-17"]
        mock_di.trading_dates = dates
        mock_di.get_underlying_price.return_value = 2.55
        mock_di.get_options.return_value = MagicMock(empty=True)
        mock_di.get_atm_options.return_value = (None, None)

        engine = BacktestEngine(cfg, mock_di)
        with patch.object(
            engine.processor, "process_day", return_value={"daily_pnl": 0.0}
        ) as mock_process:
            engine.run()
            assert mock_process.call_count == len(dates)

    def test_processor_process_day_returns_day_result(self):
        """process_day should be called and return a day_result dict."""
        from backtest.engine import BacktestEngine

        cfg = default_config()
        mock_di = MagicMock()
        dates = ["2024-12-16"]
        mock_di.trading_dates = dates
        mock_di.get_underlying_price.return_value = 2.55
        mock_di.get_options.return_value = MagicMock(empty=True)
        mock_di.get_atm_options.return_value = (None, None)

        engine = BacktestEngine(cfg, mock_di)
        # Mock process_day to return a day_result
        engine.processor.process_day = MagicMock(return_value={"daily_pnl": 100.0})

        engine.run()

        call_args = engine.processor.process_day.call_args
        assert call_args is not None
        assert call_args[0][0] == "2024-12-16"

    def test_open_positions_force_closed_at_end(self):
        """Open positions should be force-closed at end of backtest."""
        from backtest.engine import BacktestEngine

        cfg = default_config()
        mock_di = MagicMock()
        dates = ["2024-12-16", "2024-12-17"]
        mock_di.trading_dates = dates
        mock_di.get_underlying_price.return_value = 2.55
        mock_di.get_options.return_value = MagicMock(empty=True)
        mock_di.get_atm_options.return_value = (None, None)

        engine = BacktestEngine(cfg, mock_di)

        # Create an open position in the portfolio
        call_leg = OptionLeg(
            order_book_id="100001",
            strike_price=2.55,
            maturity_date="2024-12-25",
            option_type="C",
            open_price=0.1,
            contract_multiplier=10000,
        )
        put_leg = OptionLeg(
            order_book_id="100002",
            strike_price=2.55,
            maturity_date="2024-12-25",
            option_type="P",
            open_price=0.1,
            contract_multiplier=10000,
        )
        engine.portfolio.open_position(
            open_date="2024-12-16",
            strike_price=2.55,
            maturity_date="2024-12-25",
            call_leg=call_leg,
            put_leg=put_leg,
            total_cost=2000.0,
        )

        engine.run()

        # After run, all positions should be closed
        open_positions = engine.portfolio.get_open_positions()
        assert len(open_positions) == 0

    def test_summary_and_equity_stats_computed(self):
        """Results should contain summary and equity_stats after run()."""
        from backtest.engine import BacktestEngine

        cfg = default_config()
        mock_di = MagicMock()
        mock_di.trading_dates = ["2024-12-16"]
        mock_di.get_underlying_price.return_value = 2.55
        mock_di.get_options.return_value = MagicMock(empty=True)
        mock_di.get_atm_options.return_value = (None, None)

        engine = BacktestEngine(cfg, mock_di)
        engine.run()

        assert "summary" in engine.results
        assert "equity_stats" in engine.results

    def test_write_methods_are_called(self):
        """_write_trade_files, _write_summary, _write_equity_curve, _write_daily_logs should be called."""
        from backtest.engine import BacktestEngine

        cfg = default_config()
        mock_di = MagicMock()
        mock_di.trading_dates = ["2024-12-16"]
        mock_di.get_underlying_price.return_value = 2.55
        mock_di.get_options.return_value = MagicMock(empty=True)
        mock_di.get_atm_options.return_value = (None, None)

        engine = BacktestEngine(cfg, mock_di)

        with (
            patch.object(engine, "_write_trade_files") as mock_trades,
            patch.object(engine, "_write_summary") as mock_summary,
            patch.object(engine, "_write_equity_curve") as mock_ec,
            patch.object(engine, "_write_daily_logs") as mock_logs,
        ):
            engine.run()

            mock_trades.assert_called_once()
            mock_summary.assert_called_once()
            mock_ec.assert_called_once()
            mock_logs.assert_called_once()

    def test_results_dir_created_with_timestamp(self):
        """Results directory should be created as results/{timestamp}/."""
        from backtest.engine import BacktestEngine

        cfg = default_config()
        mock_di = MagicMock()
        mock_di.trading_dates = ["2024-12-16"]
        mock_di.get_underlying_price.return_value = 2.55
        mock_di.get_options.return_value = MagicMock(empty=True)
        mock_di.get_atm_options.return_value = (None, None)

        engine = BacktestEngine(cfg, mock_di)

        with (
            patch.object(engine, "_write_trade_files"),
            patch.object(engine, "_write_summary"),
            patch.object(engine, "_write_equity_curve"),
            patch.object(engine, "_write_daily_logs"),
        ):
            engine.run()

        # results dir should be set on engine
        assert hasattr(engine, "results_dir")
        assert engine.results_dir.startswith("results/")

    def test_cumulative_pnl_relative_to_initial_capital(self):
        """cumulative_pnl should be equity - initial_capital."""
        from backtest.engine import BacktestEngine

        cfg = default_config()
        cfg.initial_capital = 1_000_000.0
        mock_di = MagicMock()
        mock_di.trading_dates = ["2024-12-16"]
        mock_di.get_underlying_price.return_value = 2.55
        mock_di.get_options.return_value = MagicMock(empty=True)
        mock_di.get_atm_options.return_value = (None, None)

        engine = BacktestEngine(cfg, mock_di)
        engine.run()

        entry = engine.results["equity_curve"][0]
        expected_cumulative = entry["equity"] - cfg.initial_capital
        assert abs(entry["cumulative_pnl"] - expected_cumulative) < 0.01
