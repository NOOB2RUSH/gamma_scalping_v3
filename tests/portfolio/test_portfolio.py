import pytest
from portfolio.portfolio import Portfolio
from portfolio.position import OptionLeg


class TestPortfolioInit:
    def test_initial_capital(self):
        p = Portfolio(500_000)
        assert p.initial_capital == 500_000
        assert p.cash == 500_000

    def test_default_capital(self):
        p = Portfolio()
        assert p.cash == 1_000_000


class TestOpenPosition:
    def test_opening_position_reduces_cash(self):
        p = Portfolio(1_000_000)
        call = OptionLeg("1000001", 2.55, "2025-01-22", "C", 0.1)
        put = OptionLeg("1000002", 2.55, "2025-01-22", "P", 0.09)
        pos = p.open_position("2024-12-16", 2.55, "2025-01-22", call, put, 1900.0)
        assert p.cash == 1_000_000 - 1900.0
        assert pos.trade_id == "001"
        assert pos.open_cost == 1900.0

    def test_trade_id_increments(self):
        p = Portfolio()
        call = OptionLeg("1000001", 2.55, "2025-01-22", "C", 0.1)
        put = OptionLeg("1000002", 2.55, "2025-01-22", "P", 0.09)
        p.open_position("2024-12-16", 2.55, "2025-01-22", call, put, 1900.0)
        p.open_position("2024-12-17", 2.55, "2025-01-22", call, put, 1900.0)
        assert list(p.positions.keys()) == ["001", "002"]


class TestClosePosition:
    def test_closing_position_returns_proceeds(self):
        p = Portfolio(1_000_000)
        call = OptionLeg("1000001", 2.55, "2025-01-22", "C", 0.1)
        put = OptionLeg("1000002", 2.55, "2025-01-22", "P", 0.09)
        pos = p.open_position("2024-12-16", 2.55, "2025-01-22", call, put, 1900.0)
        net_pnl = p.close_position(pos.trade_id, "2024-12-20", 2000.0)
        assert net_pnl == 100.0
        assert p.cash == 1_000_000 - 1900.0 + 2000.0

    def test_close_position_separates_hedge_pnl(self):
        """net_pnl = option_pnl only; hedge_pnl tracked separately.

        Hedge daily cash flows are not recorded in portfolio.cash,
        so including hedge_mtm in net_pnl would cause total_realized_pnl
        to diverge from equity_change (which only tracks actual cash).
        Hedge contribution is available via pos.hedge_pnl field.

        When close_current_hedge() is used, realized_pnl is computed
        and used in close_position() instead of MTM to final close price.
        """
        p = Portfolio(1_000_000)
        call = OptionLeg("1000001", 2.55, "2025-01-22", "C", 0.1)
        put = OptionLeg("1000002", 2.55, "2025-01-22", "P", 0.09)
        pos = p.open_position("2024-12-16", 2.55, "2025-01-22", call, put, 1900.0)

        # Scenario 1: close_current_hedge() sets realized_pnl
        pos.add_hedge_record("2024-12-17", -4000, 2.55, 0.0)
        # Simulate closing hedge via close_current_hedge at price 2.58
        pos.close_current_hedge(
            exit_date="2024-12-18",
            exit_price=2.58,
            etf_commission=0.0003,
            etf_handling_fee=0.0001,
            etf_min_commission=1.0,
            etf_slippage=0.001,
        )
        # realized_pnl should be set
        assert pos.hedge_records[0].get("realized_pnl") is not None
        assert pos.hedge_records[0]["exit_date"] == "2024-12-18"
        # exit_price now includes slippage applied (for short hedge qty<0, exit price is higher due to buying)
        assert pos.hedge_records[0]["exit_price"] == pytest.approx(2.58258, abs=1e-5)

        # Scenario 2: close_position uses realized_pnl from close_current_hedge
        underlying_close_price = 2.60
        net_pnl = p.close_position(
            pos.trade_id, "2024-12-20", 2000.0, underlying_close_price
        )
        # net_pnl = option_pnl only (close_proceeds - open_cost)
        assert net_pnl == pytest.approx(100.0, abs=1e-6)
        # hedge_pnl comes from realized_pnl, not MTM to underlying_close_price
        assert pos.hedge_pnl == pytest.approx(
            pos.hedge_records[0]["realized_pnl"], abs=1e-6
        )


class TestGetOpenPositions:
    def test_returns_only_open_positions(self):
        p = Portfolio()
        call = OptionLeg("1000001", 2.55, "2025-01-22", "C", 0.1)
        put = OptionLeg("1000002", 2.55, "2025-01-22", "P", 0.09)
        pos1 = p.open_position("2024-12-16", 2.55, "2025-01-22", call, put, 1900.0)
        p.open_position("2024-12-17", 2.55, "2025-01-22", call, put, 1900.0)
        p.close_position(pos1.trade_id, "2024-12-18", 2000.0)
        open_pos = p.get_open_positions()
        assert len(open_pos) == 1


class TestTotalEquity:
    def test_equity_with_open_position(self):
        p = Portfolio(1_000_000)
        call = OptionLeg("1000001", 2.55, "2025-01-22", "C", 0.1)
        put = OptionLeg("1000002", 2.55, "2025-01-22", "P", 0.09)
        p.open_position("2024-12-16", 2.55, "2025-01-22", call, put, 1900.0)
        equity = p.total_equity()
        assert equity == 1_000_000


class TestStrikeHasPosition:
    def test_true_when_open_position_at_strike(self):
        p = Portfolio()
        call = OptionLeg("1000001", 2.55, "2025-01-22", "C", 0.1)
        put = OptionLeg("1000002", 2.55, "2025-01-22", "P", 0.09)
        p.open_position("2024-12-16", 2.55, "2025-01-22", call, put, 1900.0)
        assert p.strike_has_position(2.55)

    def test_false_when_no_position_at_strike(self):
        p = Portfolio()
        call = OptionLeg("1000001", 2.55, "2025-01-22", "C", 0.1)
        put = OptionLeg("1000002", 2.55, "2025-01-22", "P", 0.09)
        p.open_position("2024-12-16", 2.55, "2025-01-22", call, put, 1900.0)
        assert not p.strike_has_position(2.60)
