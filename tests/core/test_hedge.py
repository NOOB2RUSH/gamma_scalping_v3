import pytest
from core.hedge import hedge_delta_to_zero, calculate_hedge_pnl


class TestHedgeDeltaToZero:
    def test_zero_delta_returns_zero(self):
        qty, pnl, cost = hedge_delta_to_zero(0, 2.55, 5.0, 0.0005, 0.00001, 0.001)
        assert qty == 0
        assert pnl == 0.0
        assert cost == 0.0

    def test_positive_delta_shorts_etf(self):
        qty, cost_or_proceeds, cost = hedge_delta_to_zero(
            5000, 2.55, 5.0, 0.0005, 0.00001, 0.001
        )
        assert qty == -5000
        assert cost_or_proceeds > 0

    def test_negative_delta_buys_etf(self):
        qty, cost_or_proceeds, cost = hedge_delta_to_zero(
            -5000, 2.55, 5.0, 0.0005, 0.00001, 0.001
        )
        assert qty == 5000
        assert cost_or_proceeds < 0


class TestCalculateHedgePnl:
    def test_zero_qty_returns_zero(self):
        assert calculate_hedge_pnl(0, 2.55, 2.55, 0.0005, 0.00001, 0.0005, 5.0) == 0.0

    def test_profitable_short_pnl(self):
        pnl = calculate_hedge_pnl(-1000, 2.55, 2.50, 0.0005, 0.00001, 0.0005, 5.0)
        assert pnl > 0

    def test_profitable_long_pnl(self):
        pnl = calculate_hedge_pnl(1000, 2.50, 2.55, 0.0005, 0.00001, 0.0005, 5.0)
        assert pnl > 0

    def test_loss_on_wrong_direction(self):
        pnl = calculate_hedge_pnl(-1000, 2.50, 2.55, 0.0005, 0.00001, 0.0005, 5.0)
        assert pnl < 0
