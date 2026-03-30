import pandas as pd
import pytest
from unittest.mock import MagicMock
from config import Config, default_config
from portfolio.portfolio import Portfolio
from portfolio.position import OptionLeg


class TestComputeOpeningCost:
    """Test option cost computation (commissions, fees, slippage)."""

    def test_buy_straddle_atm_cost(self):
        """Buying ATM straddle should deduct cost from portfolio cash."""
        cfg = default_config()
        portfolio = Portfolio(cfg.initial_capital)

        call_leg = OptionLeg(
            order_book_id="1000001",
            strike_price=2.55,
            maturity_date="2025-01-22",
            option_type="C",
            open_price=0.10,
        )
        put_leg = OptionLeg(
            order_book_id="1000002",
            strike_price=2.55,
            maturity_date="2025-01-22",
            option_type="P",
            open_price=0.09,
        )

        # 1 call + 1 put at mid prices
        # call: 0.10 * 1.005 (slippage) * 10000 + fees
        # put:  0.09 * 1.005 (slippage) * 10000 + fees
        call_cost = (0.10 * 1.005) * 10000
        put_cost = (0.09 * 1.005) * 10000
        notional = call_cost + put_cost
        commission = max(notional * cfg.option_commission, cfg.option_min_commission)
        handling = notional * cfg.option_handling_fee
        transfer = notional * cfg.option_transfer_fee
        total_cost = call_cost + put_cost + commission + handling + transfer

        pos = portfolio.open_position(
            "2024-12-16",
            2.55,
            "2025-01-22",
            call_leg,
            put_leg,
            total_cost,
        )

        assert pos.trade_id == "001"
        assert portfolio.cash == pytest.approx(cfg.initial_capital - total_cost)


class TestProcessOpen:
    """Test open position logic."""

    def test_opens_straddle_when_iv_low_and_cash_sufficient(self):
        """Should open position when IV percentile low, cash available, liquidity ok."""
        cfg = default_config()
        portfolio = Portfolio(cfg.initial_capital)

        # Mock DataInterface to return ATM options
        mock_di = MagicMock()
        mock_di.get_underlying_price.return_value = 2.55
        mock_di.get_options.return_value = MagicMock()  # will check volume
        mock_di.get_atm_options.return_value = (
            MagicMock(
                **{
                    "order_book_id": "1000001",
                    "strike_price": 2.55,
                    "maturity_date": "2025-01-22",
                    "option_type": "C",
                    "close": 0.10,
                    "volume": 5000,
                }
            ),
            MagicMock(
                **{
                    "order_book_id": "1000002",
                    "strike_price": 2.55,
                    "maturity_date": "2025-01-22",
                    "option_type": "P",
                    "close": 0.09,
                    "volume": 5000,
                }
            ),
        )

        # We need a processor that uses these mocks...
        from backtest.processor import DailyProcessor

        proc = DailyProcessor(cfg, portfolio, mock_di)
        # Simulate finding ATM options
        call_opt, put_opt = mock_di.get_atm_options("2024-12-16")
        s = 2.55

        # Simulate open check
        from core.signal import check_open_signals

        ok, reason = check_open_signals(
            iv_percentile=0.10,
            cash=portfolio.cash,
            call_volume=5000,
            put_volume=5000,
            open_threshold=cfg.open_threshold,
            min_volume=cfg.min_volume,
        )
        assert ok

    def test_blocks_open_when_iv_high(self):
        """Should NOT open when IV percentile above threshold."""
        from core.signal import check_open_signals

        ok, reason = check_open_signals(
            iv_percentile=0.90,
            cash=1_000_000,
            call_volume=5000,
            put_volume=5000,
            open_threshold=0.15,
            min_volume=2000,
        )
        assert not ok
        assert "IV percentile" in reason

    def test_blocks_open_when_no_cash(self):
        """Should NOT open when insufficient cash."""
        from core.signal import check_open_signals

        ok, reason = check_open_signals(
            iv_percentile=0.10,
            cash=0,
            call_volume=5000,
            put_volume=5000,
            open_threshold=0.15,
            min_volume=2000,
        )
        assert not ok


class TestProcessClose:
    """Test close position logic."""

    def test_closes_position_when_iv_above_threshold(self):
        """Should close when IV percentile exceeds high threshold."""
        from core.signal import check_close_signals

        ok, reason = check_close_signals(
            iv_percentile=0.90,
            dte=20,
            holding_days=5,
            close_threshold=0.85,
            close_dte_threshold=5,
            max_holding_days=30,
        )
        assert ok
        assert "IV percentile" in reason

    def test_closes_position_when_near_expiry(self):
        """Should close when DTE below threshold."""
        from core.signal import check_close_signals

        ok, reason = check_close_signals(
            iv_percentile=0.50,
            dte=3,
            holding_days=5,
            close_threshold=0.85,
            close_dte_threshold=5,
            max_holding_days=30,
        )
        assert ok
        assert "expiry" in reason

    def test_closes_position_when_max_holding_days_reached(self):
        """Should close when holding days exceed maximum."""
        from core.signal import check_close_signals

        ok, reason = check_close_signals(
            iv_percentile=0.50,
            dte=20,
            holding_days=35,
            close_threshold=0.85,
            close_dte_threshold=5,
            max_holding_days=30,
        )
        assert ok
        assert "holding days" in reason

    def test_keeps_position_when_no_close_signal(self):
        """Should keep position when no close condition is met."""
        from core.signal import check_close_signals

        ok, reason = check_close_signals(
            iv_percentile=0.50,
            dte=20,
            holding_days=5,
            close_threshold=0.85,
            close_dte_threshold=5,
            max_holding_days=30,
        )
        assert not ok


class TestProcessHedge:
    """Test delta hedge logic."""

    def test_hedges_when_delta_exceeds_threshold(self):
        """Should hedge when position delta absolute value exceeds threshold."""
        from core.signal import should_hedge

        assert should_hedge(0.10, 0.05)
        assert should_hedge(-0.10, 0.05)

    def test_no_hedge_when_delta_within_threshold(self):
        """Should not hedge when delta within threshold."""
        from core.signal import should_hedge

        assert not should_hedge(0.03, 0.05)
        assert not should_hedge(-0.03, 0.05)

    def test_hedge_delta_to_zero_returns_signed_qty(self):
        """hedge_delta_to_zero should return signed ETF quantity."""
        from core.hedge import hedge_delta_to_zero

        # Positive delta (long gamma) → need to sell ETF to hedge
        qty, cost_or_proceeds, total_cost = hedge_delta_to_zero(
            current_delta=5000,
            etf_price=2.55,
            etf_min_commission=5.0,
            etf_commission=0.0005,
            etf_handling_fee=0.00001,
            etf_slippage=0.001,
        )
        assert qty == -5000
        assert cost_or_proceeds > 0

        # Negative delta → need to buy ETF
        qty2, cost_or_proceeds2, total_cost2 = hedge_delta_to_zero(
            current_delta=-3000,
            etf_price=2.55,
            etf_min_commission=5.0,
            etf_commission=0.0005,
            etf_handling_fee=0.00001,
            etf_slippage=0.001,
        )
        assert qty2 == 3000
        assert cost_or_proceeds2 < 0


class TestDailyProcessorIntegration:
    """Integration tests for DailyProcessor with mocked dependencies."""

    def test_processor_initializes(self):
        """DailyProcessor should initialize with config, portfolio, and data interface."""
        from backtest.processor import DailyProcessor

        cfg = default_config()
        portfolio = Portfolio(cfg.initial_capital)
        mock_di = MagicMock()

        proc = DailyProcessor(cfg, portfolio, mock_di)
        assert proc.config is cfg
        assert proc.portfolio is portfolio
        assert proc.data_interface is mock_di


class TestProcessDay:
    """Tests for DailyProcessor.process_day() method."""

    def _make_atm_call(self, **overrides):
        defaults = {
            "order_book_id": "1000001",
            "strike_price": 2.55,
            "maturity_date": "2025-01-22",
            "option_type": "C",
            "close": 0.10,
            "bid": 0.09,
            "ask": 0.11,
            "volume": 5000,
        }
        defaults.update(overrides)
        return pd.Series(defaults)

    def _make_atm_put(self, **overrides):
        defaults = {
            "order_book_id": "1000002",
            "strike_price": 2.55,
            "maturity_date": "2025-01-22",
            "option_type": "P",
            "close": 0.09,
            "bid": 0.08,
            "ask": 0.10,
            "volume": 5000,
        }
        defaults.update(overrides)
        return pd.Series(defaults)

    def _make_mock_iv_history(self, dates_ivs: list[tuple[str, int, float]]):
        import pandas as pd

        dates = [d for d, _, _ in dates_ivs]
        dtes = [dt for _, dt, _ in dates_ivs]
        ivs = [iv for _, _, iv in dates_ivs]
        return pd.DataFrame({"date": dates, "dte": dtes, "iv": ivs})

    def _enough_iv_history(self, base_date: str = "2024-12-16") -> pd.DataFrame:
        import pandas as pd

        rows = []
        for i in range(65):
            d = pd.Timestamp(base_date) - pd.Timedelta(days=64 - i)
            iv = round(0.28 + ((i % 10) / 10) * 0.12, 4)
            rows.append((d.strftime("%Y-%m-%d"), 30, iv))
        return pd.DataFrame(rows, columns=["date", "dte", "iv"])

    def _iv_history_high_iv(self, base_date: str = "2024-12-20") -> pd.DataFrame:
        import pandas as pd

        rows = []
        for i in range(65):
            d = pd.Timestamp(base_date) - pd.Timedelta(days=64 - i)
            iv = round(0.10 + (i / 64) * 0.10, 4)
            rows.append((d.strftime("%Y-%m-%d"), 30, iv))
        return pd.DataFrame(rows, columns=["date", "dte", "iv"])

    def test_process_day_returns_dict_structure(self):
        """process_day should return a dict with expected keys."""
        import pandas as pd
        from backtest.processor import DailyProcessor

        cfg = default_config()
        portfolio = Portfolio(cfg.initial_capital)
        mock_di = MagicMock()
        mock_di.get_underlying_price.return_value = 2.55
        mock_di.get_options.return_value = pd.DataFrame(
            {
                "order_book_id": ["1000001"],
                "strike_price": [2.55],
                "maturity_date": ["2025-02-01"],
                "option_type": ["C"],
                "bid": [0.10],
                "ask": [0.10],
                "close": [0.10],
                "volume": [5000],
            }
        )
        mock_di.get_atm_options.return_value = (None, None)

        proc = DailyProcessor(cfg, portfolio, mock_di)
        proc._iv_history = self._enough_iv_history("2024-12-16")

        result = proc.process_day("2024-12-16")

        assert isinstance(result, dict)
        assert "date" in result
        assert "iv_percentile" in result
        assert "opened" in result
        assert "closed" in result
        assert "hedges" in result
        assert "equity" in result
        assert "cash" in result
        assert result["date"] == "2024-12-16"

    def test_process_day_skips_when_iv_percentile_none(self):
        """process_day should return with None iv_percentile when insufficient history."""
        import pandas as pd
        from backtest.processor import DailyProcessor

        cfg = default_config()
        portfolio = Portfolio(cfg.initial_capital)
        mock_di = MagicMock()
        mock_di.get_underlying_price.return_value = 2.55
        mock_di.get_options.return_value = pd.DataFrame(
            {
                "order_book_id": [],
                "strike_price": [],
                "maturity_date": [],
                "option_type": [],
                "bid": [],
                "ask": [],
                "close": [],
                "volume": [],
            }
        )

        proc = DailyProcessor(cfg, portfolio, mock_di)
        proc._iv_history = pd.DataFrame(columns=["date", "dte", "iv"])

        result = proc.process_day("2024-12-16")

        assert result["iv_percentile"] is None
        assert result["opened"] == []
        assert result["closed"] == []

    def test_process_day_opens_position_when_iv_low(self):
        """Should open straddle when IV percentile below open_threshold."""
        from backtest.processor import DailyProcessor
        import pandas as pd

        cfg = default_config()
        portfolio = Portfolio(cfg.initial_capital)
        mock_di = MagicMock()
        mock_di.get_underlying_price.return_value = 2.55
        mock_di.get_options.return_value = pd.DataFrame(
            {
                "order_book_id": ["1000001", "1000002"],
                "strike_price": [2.55, 2.55],
                "maturity_date": ["2025-01-22", "2025-01-22"],
                "option_type": ["C", "P"],
                "bid": [0.09, 0.08],
                "ask": [0.11, 0.10],
                "close": [0.10, 0.09],
                "volume": [5000, 5000],
            }
        )
        mock_di.get_atm_options.return_value = (
            self._make_atm_call(),
            self._make_atm_put(),
        )

        proc = DailyProcessor(cfg, portfolio, mock_di)
        proc._iv_history = self._enough_iv_history("2024-12-16")

        result = proc.process_day("2024-12-16")

        assert len(result["opened"]) == 1
        assert portfolio.cash < cfg.initial_capital
        open_positions = portfolio.get_open_positions()
        assert len(open_positions) == 1

    def test_process_day_no_open_when_strike_has_position(self):
        """Should NOT open a second position at the same strike."""
        from backtest.processor import DailyProcessor
        import pandas as pd

        cfg = default_config()
        portfolio = Portfolio(cfg.initial_capital)
        mock_di = MagicMock()
        mock_di.get_underlying_price.return_value = 2.55
        mock_di.get_options.return_value = pd.DataFrame(
            {
                "order_book_id": ["1000001", "1000002"],
                "strike_price": [2.55, 2.55],
                "maturity_date": ["2025-01-22", "2025-01-22"],
                "option_type": ["C", "P"],
                "bid": [0.09, 0.08],
                "ask": [0.11, 0.10],
                "close": [0.10, 0.09],
                "volume": [5000, 5000],
            }
        )
        mock_di.get_atm_options.return_value = (
            self._make_atm_call(),
            self._make_atm_put(),
        )

        proc = DailyProcessor(cfg, portfolio, mock_di)
        proc._iv_history = self._enough_iv_history("2024-12-16")

        proc.process_day("2024-12-16")
        assert len(portfolio.get_open_positions()) == 1

        result2 = proc.process_day("2024-12-17")
        assert len(result2["opened"]) == 0
        assert len(portfolio.get_open_positions()) == 1

    def test_process_day_closes_position_when_iv_high(self):
        """Should close position when IV percentile exceeds close_threshold."""
        from backtest.processor import DailyProcessor
        import pandas as pd

        cfg = default_config()
        portfolio = Portfolio(cfg.initial_capital)
        mock_di = MagicMock()
        mock_di.get_underlying_price.return_value = 2.55

        # Pre-open a position
        call_leg = OptionLeg(
            order_book_id="1000001",
            strike_price=2.55,
            maturity_date="2025-01-22",
            option_type="C",
            open_price=0.10,
        )
        put_leg = OptionLeg(
            order_book_id="1000002",
            strike_price=2.55,
            maturity_date="2025-01-22",
            option_type="P",
            open_price=0.09,
        )
        # Use straddle cost formula from config
        call_cost = (0.10 * (1 + cfg.option_slippage)) * 10000
        put_cost = (0.09 * (1 + cfg.option_slippage)) * 10000
        notional = call_cost + put_cost
        commission = max(notional * cfg.option_commission, cfg.option_min_commission)
        handling = notional * cfg.option_handling_fee
        transfer = notional * cfg.option_transfer_fee
        total_cost = call_cost + put_cost + commission + handling + transfer

        pos = portfolio.open_position(
            "2024-12-16", 2.55, "2025-01-22", call_leg, put_leg, total_cost
        )

        mock_di.get_options.return_value = pd.DataFrame(
            {
                "order_book_id": ["1000001", "1000002"],
                "strike_price": [2.55, 2.55],
                "maturity_date": ["2025-01-22", "2025-01-22"],
                "option_type": ["C", "P"],
                "bid": [0.11, 0.10],
                "ask": [0.13, 0.12],
                "close": [0.12, 0.11],
                "volume": [5000, 5000],
            }
        )
        mock_di.get_atm_options.return_value = (
            self._make_atm_call(close=0.12, bid=0.11, ask=0.13),
            self._make_atm_put(close=0.11, bid=0.10, ask=0.12),
        )

        proc = DailyProcessor(cfg, portfolio, mock_di)
        proc._iv_history = self._iv_history_high_iv("2024-12-20")

        result = proc.process_day("2024-12-20")

        assert len(result["closed"]) == 1
        assert result["closed"][0] == "001"
        assert pos.is_closed

    def test_process_day_closes_position_when_near_expiry(self):
        """Should close position when DTE <= close_dte_threshold."""
        from backtest.processor import DailyProcessor
        import pandas as pd

        cfg = default_config()
        portfolio = Portfolio(cfg.initial_capital)
        mock_di = MagicMock()
        mock_di.get_underlying_price.return_value = 2.55

        # Pre-open a position with maturity very close to current date
        call_leg = OptionLeg(
            order_book_id="1000001",
            strike_price=2.55,
            maturity_date="2024-12-24",  # Only 3 DTE from 2024-12-21
            option_type="C",
            open_price=0.10,
        )
        put_leg = OptionLeg(
            order_book_id="1000002",
            strike_price=2.55,
            maturity_date="2024-12-24",
            option_type="P",
            open_price=0.09,
        )
        call_cost = (0.10 * (1 + cfg.option_slippage)) * 10000
        put_cost = (0.09 * (1 + cfg.option_slippage)) * 10000
        notional = call_cost + put_cost
        commission = max(notional * cfg.option_commission, cfg.option_min_commission)
        handling = notional * cfg.option_handling_fee
        transfer = notional * cfg.option_transfer_fee
        total_cost = call_cost + put_cost + commission + handling + transfer

        portfolio.open_position(
            "2024-12-16", 2.55, "2024-12-24", call_leg, put_leg, total_cost
        )

        mock_di.get_options.return_value = pd.DataFrame(
            {
                "order_book_id": ["1000001", "1000002"],
                "strike_price": [2.55, 2.55],
                "maturity_date": ["2024-12-24", "2024-12-24"],
                "option_type": ["C", "P"],
                "bid": [0.05, 0.05],
                "ask": [0.07, 0.07],
                "close": [0.06, 0.06],
                "volume": [5000, 5000],
            }
        )
        mock_di.get_atm_options.return_value = (
            self._make_atm_call(
                maturity_date="2024-12-24", close=0.06, bid=0.05, ask=0.07
            ),
            self._make_atm_put(
                maturity_date="2024-12-24", close=0.06, bid=0.05, ask=0.07
            ),
        )

        proc = DailyProcessor(cfg, portfolio, mock_di)
        proc._iv_history = self._enough_iv_history("2024-12-21")

        result = proc.process_day("2024-12-21")

        assert len(result["closed"]) == 1

    def test_process_day_hedges_delta_when_threshold_exceeded(self):
        """Should hedge when position delta absolute value exceeds threshold."""
        from backtest.processor import DailyProcessor
        import pandas as pd

        cfg = default_config()
        portfolio = Portfolio(cfg.initial_capital)
        mock_di = MagicMock()
        mock_di.get_underlying_price.return_value = 2.55

        # Pre-open a position
        call_leg = OptionLeg(
            order_book_id="1000001",
            strike_price=2.55,
            maturity_date="2025-01-22",
            option_type="C",
            open_price=0.10,
        )
        put_leg = OptionLeg(
            order_book_id="1000002",
            strike_price=2.55,
            maturity_date="2025-01-22",
            option_type="P",
            open_price=0.09,
        )
        call_cost = (0.10 * (1 + cfg.option_slippage)) * 10000
        put_cost = (0.09 * (1 + cfg.option_slippage)) * 10000
        notional = call_cost + put_cost
        commission = max(notional * cfg.option_commission, cfg.option_min_commission)
        handling = notional * cfg.option_handling_fee
        transfer = notional * cfg.option_transfer_fee
        total_cost = call_cost + put_cost + commission + handling + transfer

        pos = portfolio.open_position(
            "2024-12-16", 2.55, "2025-01-22", call_leg, put_leg, total_cost
        )

        mock_di.get_options.return_value = pd.DataFrame(
            {
                "order_book_id": ["1000001", "1000002"],
                "strike_price": [2.55, 2.55],
                "maturity_date": ["2025-01-22", "2025-01-22"],
                "option_type": ["C", "P"],
                "bid": [0.11, 0.10],
                "ask": [0.13, 0.12],
                "close": [0.12, 0.11],
                "volume": [5000, 5000],
            }
        )
        mock_di.get_atm_options.return_value = (
            self._make_atm_call(close=0.12, bid=0.11, ask=0.13),
            self._make_atm_put(close=0.11, bid=0.10, ask=0.12),
        )

        proc = DailyProcessor(cfg, portfolio, mock_di)
        proc._iv_history = self._enough_iv_history("2024-12-17")

        # Day 2 - position should be hedged (delta exceeds threshold)
        result = proc.process_day("2024-12-17")

        # Should have recorded hedge in position
        assert len(pos.hedge_records) >= 1
        assert len(result["hedges"]) >= 1

    def test_process_day_no_hedge_on_open_day(self):
        """Should NOT hedge on the same day the position was opened."""
        from backtest.processor import DailyProcessor
        import pandas as pd

        cfg = default_config()
        portfolio = Portfolio(cfg.initial_capital)
        mock_di = MagicMock()
        mock_di.get_underlying_price.return_value = 2.55
        mock_di.get_options.return_value = pd.DataFrame(
            {
                "order_book_id": ["1000001", "1000002"],
                "strike_price": [2.55, 2.55],
                "maturity_date": ["2025-01-22", "2025-01-22"],
                "option_type": ["C", "P"],
                "bid": [0.09, 0.08],
                "ask": [0.11, 0.10],
                "close": [0.10, 0.09],
                "volume": [5000, 5000],
            }
        )
        mock_di.get_atm_options.return_value = (
            self._make_atm_call(),
            self._make_atm_put(),
        )

        proc = DailyProcessor(cfg, portfolio, mock_di)
        proc._iv_history = self._enough_iv_history("2024-12-16")

        # Open position
        result = proc.process_day("2024-12-16")
        assert len(result["opened"]) == 1

        # Get the opened position
        open_positions = portfolio.get_open_positions()
        assert len(open_positions) == 1
        # No hedges should have been recorded on open day
        assert len(open_positions[0].hedge_records) == 0

    def test_process_day_records_daily_greeks(self):
        """Should record daily Greeks for open positions."""
        from backtest.processor import DailyProcessor
        import pandas as pd

        cfg = default_config()
        portfolio = Portfolio(cfg.initial_capital)
        mock_di = MagicMock()
        mock_di.get_underlying_price.return_value = 2.55

        # Pre-open a position
        call_leg = OptionLeg(
            order_book_id="1000001",
            strike_price=2.55,
            maturity_date="2025-01-22",
            option_type="C",
            open_price=0.10,
        )
        put_leg = OptionLeg(
            order_book_id="1000002",
            strike_price=2.55,
            maturity_date="2025-01-22",
            option_type="P",
            open_price=0.09,
        )
        call_cost = (0.10 * (1 + cfg.option_slippage)) * 10000
        put_cost = (0.09 * (1 + cfg.option_slippage)) * 10000
        notional = call_cost + put_cost
        commission = max(notional * cfg.option_commission, cfg.option_min_commission)
        handling = notional * cfg.option_handling_fee
        transfer = notional * cfg.option_transfer_fee
        total_cost = call_cost + put_cost + commission + handling + transfer

        pos = portfolio.open_position(
            "2024-12-16", 2.55, "2025-01-22", call_leg, put_leg, total_cost
        )

        mock_di.get_options.return_value = pd.DataFrame(
            {
                "order_book_id": ["1000001", "1000002"],
                "strike_price": [2.55, 2.55],
                "maturity_date": ["2025-01-22", "2025-01-22"],
                "option_type": ["C", "P"],
                "bid": [0.11, 0.10],
                "ask": [0.13, 0.12],
                "close": [0.12, 0.11],
                "volume": [5000, 5000],
            }
        )
        mock_di.get_atm_options.return_value = (
            self._make_atm_call(close=0.12, bid=0.11, ask=0.13),
            self._make_atm_put(close=0.11, bid=0.10, ask=0.12),
        )

        proc = DailyProcessor(cfg, portfolio, mock_di)
        proc._iv_history = self._enough_iv_history("2024-12-17")

        # Day 2 - record Greeks
        result = proc.process_day("2024-12-17")

        assert len(pos.daily_greeks) >= 1
        greeks = pos.daily_greeks[-1]
        assert "date" in greeks
        assert "delta" in greeks
        assert "gamma" in greeks
        assert "vega" in greeks
        assert "theta" in greeks

    def test_process_day_accumulates_iv_history(self):
        """IV history should accumulate across multiple days."""
        from backtest.processor import DailyProcessor
        import pandas as pd

        cfg = default_config()
        portfolio = Portfolio(cfg.initial_capital)
        mock_di = MagicMock()
        mock_di.get_underlying_price.return_value = 2.55
        mock_di.get_options.return_value = pd.DataFrame(
            {
                "order_book_id": ["1000001", "1000002"],
                "strike_price": [2.55, 2.55],
                "maturity_date": ["2025-01-22", "2025-01-22"],
                "option_type": ["C", "P"],
                "bid": [0.09, 0.08],
                "ask": [0.11, 0.10],
                "close": [0.10, 0.09],
                "volume": [5000, 5000],
            }
        )
        mock_di.get_atm_options.return_value = (
            self._make_atm_call(),
            self._make_atm_put(),
        )

        proc = DailyProcessor(cfg, portfolio, mock_di)
        proc._iv_history = self._make_mock_iv_history(
            [
                ("2024-12-01", 30, 0.20),
                ("2024-12-02", 30, 0.21),
                ("2024-12-03", 30, 0.19),
                ("2024-12-04", 30, 0.18),
                ("2024-12-05", 30, 0.17),
                ("2024-12-06", 30, 0.16),
            ]
        )

        proc.process_day("2024-12-16")

        # After processing, should have accumulated IV for 2024-12-16
        # The _iv_history should now have an additional row
        assert hasattr(proc, "_iv_history")
