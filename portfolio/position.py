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
    hedge_cost: float = 0.0
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
        self.hedge_cost += abs(cost)

    def add_daily_greeks(
        self, date: str, delta: float, gamma: float, vega: float, theta: float
    ):
        self.daily_greeks.append(
            {
                "date": date,
                "delta": delta,
                "gamma": gamma,
                "vega": vega,
                "theta": theta,
            }
        )

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
        self.net_pnl = self.option_pnl

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
