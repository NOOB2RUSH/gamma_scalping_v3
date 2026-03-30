from typing import Optional
import pandas as pd
from .base import DataSourceBase


class DataInterface:
    def __init__(self, data_source: DataSourceBase):
        self._ds = data_source

    def get_etf_price(self, trade_date: str) -> pd.DataFrame:
        return self._ds.get_etf_price(trade_date)

    def get_options_chain(self, trade_date: str) -> pd.DataFrame:
        return self._ds.get_options_chain(trade_date)

    def get_date_range(self) -> tuple[str, str]:
        return self._ds.get_date_range()

    @property
    def date_range(self) -> tuple[str, str]:
        return self.get_date_range()

    @property
    def trading_dates(self) -> list[str]:
        return self._ds.get_trading_dates()

    def get_etf_close(self, trade_date: str) -> float:
        df = self.get_etf_price(trade_date)
        return float(df["close"].iloc[0])

    def get_options(self, trade_date: str) -> pd.DataFrame:
        return self.get_options_chain(trade_date)

    def get_spot_price(self, trade_date: str) -> float:
        df = self.get_etf_price(trade_date)
        if df.empty or "close" not in df.columns:
            raise FileNotFoundError(f"ETF price data not available for {trade_date}")
        return float(df["close"].iloc[0])

    def get_option_price(self, trade_date: str, order_book_id: str) -> float:
        df = self.get_options_chain(trade_date)
        row = df[df["order_book_id"] == order_book_id]
        if row.empty:
            raise ValueError(f"Option {order_book_id} not found")
        return float((row["bid"].iloc[0] + row["ask"].iloc[0]) / 2)

    def get_atm_options(self, trade_date: str, **kwargs):
        df = self.get_options_chain(trade_date)
        spot = self.get_spot_price(trade_date)
        df_call = df[df["option_type"] == "C"].copy()
        df_put = df[df["option_type"] == "P"].copy()
        if df_call.empty or df_put.empty:
            return None, None

        moneyness_range = kwargs.get("moneyness_range")
        min_volume = kwargs.get("min_volume", 0)
        min_dte = kwargs.get("min_dte", 0)

        if moneyness_range is not None:
            lo, hi = moneyness_range
            df_call = df_call[
                (df_call["strike_price"] / spot >= lo)
                & (df_call["strike_price"] / spot <= hi)
            ]
            df_put = df_put[
                (df_put["strike_price"] / spot >= lo)
                & (df_put["strike_price"] / spot <= hi)
            ]

        if min_volume > 0:
            df_call = df_call[df_call["volume"] >= min_volume]
            df_put = df_put[df_put["volume"] >= min_volume]

        if min_dte > 0:
            from datetime import datetime

            trade_dt = datetime.strptime(trade_date, "%Y-%m-%d")
            df_call = df_call[
                df_call["maturity_date"].apply(
                    lambda m: (
                        (datetime.strptime(m, "%Y-%m-%d") - trade_dt).days >= min_dte
                    )
                )
            ]
            df_put = df_put[
                df_put["maturity_date"].apply(
                    lambda m: (
                        (datetime.strptime(m, "%Y-%m-%d") - trade_dt).days >= min_dte
                    )
                )
            ]

        if df_call.empty or df_put.empty:
            return None, None

        atm_call = df_call.iloc[
            (df_call["strike_price"] - spot).abs().argsort().iloc[0]
        ]
        atm_put = df_put.iloc[(df_put["strike_price"] - spot).abs().argsort().iloc[0]]
        return atm_call, atm_put

    def get_underlying_price(self, trade_date: str) -> float:
        return self.get_spot_price(trade_date)
