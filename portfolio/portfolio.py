from .position import OptionLeg, Position


class Portfolio:
    def __init__(self, initial_capital: float = 1_000_000):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: dict[str, Position] = {}
        self._trade_id_counter = 0

    def _next_trade_id(self) -> str:
        self._trade_id_counter += 1
        return f"{self._trade_id_counter:03d}"

    def open_position(
        self,
        open_date: str,
        strike_price: float,
        maturity_date: str,
        call_leg: OptionLeg,
        put_leg: OptionLeg,
        total_cost: float,
    ) -> Position:
        trade_id = self._next_trade_id()
        self.cash -= total_cost
        pos = Position(
            trade_id=trade_id,
            open_date=open_date,
            strike_price=strike_price,
            maturity_date=maturity_date,
            call_leg=call_leg,
            put_leg=put_leg,
            open_cost=total_cost,
        )
        self.positions[trade_id] = pos
        return pos

    def close_position(
        self,
        trade_id: str,
        close_date: str,
        close_proceeds: float,
        underlying_close_price: float = None,
    ) -> float:
        pos = self.positions[trade_id]
        open_cost = pos.open_cost
        if underlying_close_price is not None and pos.hedge_records:
            hedge_pnl = 0.0
            for rec in pos.hedge_records:
                qty = rec["qty"]
                entry_price = rec["price"]
                # PnL = qty * (close_price - entry_price), then subtract transaction costs
                # For qty > 0 (buy): cost was added when opening
                # For qty < 0 (short sell): cost was subtracted when opening
                hedge_pnl += qty * (underlying_close_price - entry_price)
            hedge_pnl -= pos.hedge_cost
        else:
            hedge_pnl = 0.0
        pos.close_position(
            close_date, close_proceeds, hedge_pnl, underlying_close_price
        )
        self.cash += close_proceeds
        return pos.net_pnl

    def get_open_positions(self) -> list[Position]:
        return [p for p in self.positions.values() if not p.is_closed]

    def total_equity(self) -> float:
        open_cost_sum = sum(p.open_cost for p in self.get_open_positions())
        return self.cash + open_cost_sum

    def strike_has_position(self, strike_price: float) -> bool:
        return any(
            p.strike_price == strike_price and not p.is_closed
            for p in self.positions.values()
        )

    def has_open_position(self) -> bool:
        return any(not p.is_closed for p in self.positions.values())
