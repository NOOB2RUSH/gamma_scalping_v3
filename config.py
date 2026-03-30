from dataclasses import dataclass, fields


@dataclass
class Config:
    initial_capital: float = 100_000
    lookback_days: int = 110
    target_tenor: int = 30
    open_threshold: float = 0.15
    close_threshold: float = 0.75
    close_dte_threshold: int = 5
    max_holding_days: int = 5
    delta_hedge_threshold: float = 0.40
    moneyness_range: tuple[float, float] = (0.95, 1.05)
    min_dte: int = 4
    min_option_price: float = 0.001
    min_volume: int = 2000
    risk_free_rate: float = 0.025
    option_commission: float = 0.0003
    option_min_commission: float = 5.0
    option_handling_fee: float = 0.00001
    option_transfer_fee: float = 0.00001
    option_slippage: float = 0.005
    etf_commission: float = 0.0005
    etf_min_commission: float = 5.0
    etf_handling_fee: float = 0.00001
    etf_stamp_tax: float = 0.0005
    etf_slippage: float = 0.001

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


def default_config() -> Config:
    return Config()
