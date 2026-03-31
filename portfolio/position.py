from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OptionLeg:
    order_book_id: str
    strike_price: float
    maturity_date: str
    option_type: str
    open_price: float
    contract_multiplier: int = 10000


@dataclass
class Position:
    trade_id: str
    open_date: str
    strike_price: float
    maturity_date: str
    call_leg: OptionLeg
    put_leg: OptionLeg
    open_cost: float
    is_closed: bool = False
    close_date: Optional[str] = None
    close_proceeds: Optional[float] = None
    net_pnl: Optional[float] = None
    option_pnl: Optional[float] = None
    hedge_records: list = field(default_factory=list)
    daily_greeks: list = field(default_factory=list)
    net_hedge_qty: float = 0.0
    hedge_cost: float = 0.0  # Legacy: total costs (both open + close)
    hedge_opening_cost: float = 0.0  # Only opening costs to deduct at close
    hedge_pnl: float = 0.0

    def holding_days(self, current_date: str) -> int:
        open_d = int(self.open_date.replace("-", ""))
        current_d = int(current_date.replace("-", ""))
        return (current_d - open_d) if current_d > open_d else 0

    def add_hedge_record(self, date: str, qty: float, price: float, cost: float):
        self.hedge_records.append(
            {"date": date, "qty": qty, "price": price, "pnl": 0.0}
        )
        self.net_hedge_qty += qty
        # Track opening costs separately from closing costs
        # Opening costs will be deducted when position closes
        # Closing costs are deducted in realized_pnl via close_current_hedge()
        self.hedge_opening_cost += abs(cost)

    def close_current_hedge(
        self,
        exit_date: str,
        exit_price: float,
        etf_commission: float,
        etf_handling_fee: float,
        etf_min_commission: float,
        etf_slippage: float,
    ):
        """Close the most recent open hedge at exit_price, compute realized PnL.

        Note: entry_price already includes slippage from when the hedge was opened.
        Exit slippage should be applied because when selling, we receive bid (lower) not mid.
        """
        if not self.hedge_records:
            return
        # Find the last hedge without exit_date
        for rec in reversed(self.hedge_records):
            if rec.get("exit_date") is None:
                rec["exit_date"] = exit_date

                # Calculate realized PnL for this hedge
                qty = rec["qty"]
                entry_price = rec["price"]

                # Apply slippage to exit price (opposite direction of entry)
                # Entry: buy at s*(1+slippage) or sell at s*(1-slippage)
                # Exit: opposite direction - sell at s*(1-slippage) or buy at s*(1+slippage)
                if qty > 0:
                    # We bought hedge (long ETF), now selling - receive bid (lower)
                    exit_exec_price = exit_price * (1 - etf_slippage)
                else:
                    # We sold hedge (short ETF), now buying - pay ask (higher)
                    exit_exec_price = exit_price * (1 + etf_slippage)

                rec["exit_price"] = exit_exec_price

                pnl = qty * (exit_exec_price - entry_price)
                # Subtract transaction costs
                notional = abs(qty) * exit_exec_price
                commission = max(notional * etf_commission, etf_min_commission)
                handling = notional * etf_handling_fee
                pnl -= commission + handling

                rec["realized_pnl"] = pnl
                # NOTE: closing costs already deducted from realized_pnl above
                # Do NOT add to hedge_cost here to avoid double-deduction
                self.net_hedge_qty -= qty  # Remove this hedge's qty from net
                break

    def add_daily_greeks(
        self,
        date: str,
        delta: float,
        gamma: float,
        vega: float,
        theta: float,
        post_hedge_delta: Optional[float] = None,
    ):
        self.daily_greeks.append(
            {
                "date": date,
                "delta": delta,
                "gamma": gamma,
                "vega": vega,
                "theta": theta,
                "post_hedge_delta": post_hedge_delta,
            }
        )

    def update_last_daily_greeks_post_hedge(self, post_hedge_delta: float):
        """Update the last daily_greeks entry with post-hedge delta after hedging."""
        if self.daily_greeks:
            self.daily_greeks[-1]["post_hedge_delta"] = post_hedge_delta

    def close_position(
        self,
        close_date: str,
        close_proceeds: float,
        hedge_pnl: float = 0.0,
        underlying_close_price: float = 0.0,
    ):
        self.is_closed = True
        self.close_date = close_date
        self.close_proceeds = close_proceeds
        self.hedge_pnl = hedge_pnl
        self.option_pnl = close_proceeds - self.open_cost
        # net_pnl = option P&L only; hedge_pnl is tracked separately
        # Hedge daily cash flows are not recorded in portfolio.cash, so
        # including hedge_mtm in net_pnl would create a gap vs equity_change.
        # Hedge contribution is reported via hedge_pnl field separately.
        hedge = getattr(self, "hedge_pnl", 0)
        self.net_pnl = self.option_pnl + hedge

    def to_dict(self) -> dict:
        return {
            "trade_id": self.trade_id,
            "open_date": self.open_date,
            "strike_price": self.strike_price,
            "maturity_date": self.maturity_date,
            "call_leg": {
                "order_book_id": self.call_leg.order_book_id,
                "strike_price": self.call_leg.strike_price,
                "maturity_date": self.call_leg.maturity_date,
                "option_type": self.call_leg.option_type,
                "open_price": self.call_leg.open_price,
                "contract_multiplier": self.call_leg.contract_multiplier,
            },
            "put_leg": {
                "order_book_id": self.put_leg.order_book_id,
                "strike_price": self.put_leg.strike_price,
                "maturity_date": self.put_leg.maturity_date,
                "option_type": self.put_leg.option_type,
                "open_price": self.put_leg.open_price,
                "contract_multiplier": self.put_leg.contract_multiplier,
            },
            "open_cost": self.open_cost,
            "is_closed": self.is_closed,
            "close_date": self.close_date,
            "close_proceeds": self.close_proceeds,
            "net_pnl": self.net_pnl,
            "option_pnl": self.option_pnl,
            "hedge_records": self.hedge_records,
            "daily_greeks": self.daily_greeks,
            "net_hedge_qty": self.net_hedge_qty,
            "hedge_cost": self.hedge_cost,
            "hedge_pnl": self.hedge_pnl,
        }
