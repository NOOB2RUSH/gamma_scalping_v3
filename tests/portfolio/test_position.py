import pytest
from datetime import datetime, timedelta
from portfolio.position import Position, OptionLeg


class TestOptionLeg:
    def test_option_leg_default_multiplier(self):
        leg = OptionLeg("1000001", 2.55, "2025-01-22", "C", 0.1)
        assert leg.contract_multiplier == 10000


class TestPositionInit:
    def test_position_created_with_open_cost(self):
        call = OptionLeg("1000001", 2.55, "2025-01-22", "C", 0.1)
        put = OptionLeg("1000002", 2.55, "2025-01-22", "P", 0.09)
        pos = Position(
            trade_id="001",
            open_date="2024-12-16",
            strike_price=2.55,
            maturity_date="2025-01-22",
            call_leg=call,
            put_leg=put,
            open_cost=1900.0,
        )
        assert pos.trade_id == "001"
        assert not pos.is_closed
        assert pos.open_cost == 1900.0
        assert len(pos.hedge_records) == 0
        assert len(pos.daily_greeks) == 0


class TestHoldingDays:
    def test_holding_days_calculation(self):
        call = OptionLeg("1000001", 2.55, "2025-01-22", "C", 0.1)
        put = OptionLeg("1000002", 2.55, "2025-01-22", "P", 0.09)
        pos = Position(
            trade_id="001",
            open_date="2024-12-16",
            strike_price=2.55,
            maturity_date="2025-01-22",
            call_leg=call,
            put_leg=put,
            open_cost=1900.0,
        )
        days = pos.holding_days("2024-12-26")
        assert days == 10


class TestAddHedgeRecord:
    def test_hedge_record_accumulates_net_qty(self):
        call = OptionLeg("1000001", 2.55, "2025-01-22", "C", 0.1)
        put = OptionLeg("1000002", 2.55, "2025-01-22", "P", 0.09)
        pos = Position(
            trade_id="001",
            open_date="2024-12-16",
            strike_price=2.55,
            maturity_date="2025-01-22",
            call_leg=call,
            put_leg=put,
            open_cost=1900.0,
        )
        pos.add_hedge_record("2024-12-17", -4000, 2.55, 0)
        pos.add_hedge_record("2024-12-18", 1000, 2.56, 0)
        assert pos.net_hedge_qty == -3000
        assert len(pos.hedge_records) == 2


class TestAddDailyGreeks:
    def test_daily_greeks_accumulates(self):
        call = OptionLeg("1000001", 2.55, "2025-01-22", "C", 0.1)
        put = OptionLeg("1000002", 2.55, "2025-01-22", "P", 0.09)
        pos = Position(
            trade_id="001",
            open_date="2024-12-16",
            strike_price=2.55,
            maturity_date="2025-01-22",
            call_leg=call,
            put_leg=put,
            open_cost=1900.0,
        )
        pos.add_daily_greeks("2024-12-16", 0.5, 100, 50, -10)
        pos.add_daily_greeks("2024-12-17", 0.6, 110, 55, -12)
        assert len(pos.daily_greeks) == 2
        assert pos.daily_greeks[0]["delta"] == 0.5
        assert pos.daily_greeks[1]["gamma"] == 110


class TestClosePosition:
    def test_close_position_sets_flags(self):
        call = OptionLeg("1000001", 2.55, "2025-01-22", "C", 0.1)
        put = OptionLeg("1000002", 2.55, "2025-01-22", "P", 0.09)
        pos = Position(
            trade_id="001",
            open_date="2024-12-16",
            strike_price=2.55,
            maturity_date="2025-01-22",
            call_leg=call,
            put_leg=put,
            open_cost=1900.0,
        )
        pos.close_position("2024-12-20", 2000.0, 0.0, 100.0)
        assert pos.is_closed
        assert pos.close_date == "2024-12-20"
        assert pos.close_proceeds == 2000.0
        assert pos.net_pnl == 100.0
        assert pos.option_pnl == 100.0


class TestToDict:
    def test_to_dict_contains_all_fields(self):
        call = OptionLeg("1000001", 2.55, "2025-01-22", "C", 0.1)
        put = OptionLeg("1000002", 2.55, "2025-01-22", "P", 0.09)
        pos = Position(
            trade_id="001",
            open_date="2024-12-16",
            strike_price=2.55,
            maturity_date="2025-01-22",
            call_leg=call,
            put_leg=put,
            open_cost=1900.0,
        )
        d = pos.to_dict()
        assert d["trade_id"] == "001"
        assert d["open_cost"] == 1900.0
        assert not d["is_closed"]
