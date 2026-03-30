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

        hedge_pnl = 0.0

        for rec in pos.hedge_records:
            if rec.get("realized_pnl") is not None:
                # Use pre-computed realized PnL from close_current_hedge()
                # (transaction costs already deducted in realized_pnl)
                hedge_pnl += rec["realized_pnl"]
            elif rec.get("exit_date") is not None and rec.get("exit_price") is not None:
                # Fallback: hedge was closed but realized_pnl not set
                qty = rec["qty"]
                entry_price = rec["price"]
                exit_price = rec["exit_price"]
                hedge_pnl += qty * (exit_price - entry_price)
            elif underlying_close_price is not None:
                # Final close: close any open hedge at position close price
                # No slippage (entry has it baked in), but deduct transaction costs
                qty = rec["qty"]
                entry_price = rec["price"]
                pnl = qty * (underlying_close_price - entry_price)
                # Deduct transaction costs for this close
                notional = abs(qty) * underlying_close_price
                commission = max(notional * 0.0005, 5.0)  # default values
                handling = notional * 0.0001
                pnl -= commission + handling
                hedge_pnl += pnl
                pos.hedge_cost += commission + handling
            # else: hedge still open but no underlying_close_price (shouldn't happen)

        # Subtract only hedge OPENING costs (closing costs already deducted in realized_pnl)
        if pos.hedge_records:
            hedge_pnl -= pos.hedge_opening_cost

        # Reset net_hedge_qty since all hedges should be closed now
        pos.net_hedge_qty = 0.0

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
