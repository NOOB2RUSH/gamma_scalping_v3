from typing import Optional
import pandas as pd
from datetime import datetime
from .base import DataSourceBase
from core.greeks import implied_volatility


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
        risk_free_rate = kwargs.get("risk_free_rate")
        max_call_put_iv_diff = kwargs.get("max_call_put_iv_diff")

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

        atm_call, atm_put = self._find_matching_atm_pair(df_call, df_put, spot)
        if atm_call is None or atm_put is None:
            return None, None

        if risk_free_rate is not None and max_call_put_iv_diff is not None:
            call_iv = self._calc_iv(atm_call, spot, trade_date, risk_free_rate)
            put_iv = self._calc_iv(atm_put, spot, trade_date, risk_free_rate)
            if call_iv <= 0 or put_iv <= 0:
                return None, None
            if abs(call_iv - put_iv) > max_call_put_iv_diff:
                return None, None

        return atm_call, atm_put

    def _find_matching_atm_pair(self, df_call, df_put, spot):
        """
        Find ATM call and put with matching strike and maturity.
        Prioritizes pairs with highest combined volume.
        """
        call_strikes = set(df_call["strike_price"].unique())
        put_strikes = set(df_put["strike_price"].unique())
        common_strikes = call_strikes & put_strikes
        if not common_strikes:
            return None, None

        closest_strike = min(common_strikes, key=lambda k: abs(k - spot))

        call_at_strike = df_call[df_call["strike_price"] == closest_strike]
        put_at_strike = df_put[df_put["strike_price"] == closest_strike]

        common_maturities = set(call_at_strike["maturity_date"].unique()) & set(
            put_at_strike["maturity_date"].unique()
        )
        if not common_maturities:
            return None, None

        best_maturity = None
        best_combined_vol = -1
        for mat in common_maturities:
            c_vol = call_at_strike[call_at_strike["maturity_date"] == mat][
                "volume"
            ].iloc[0]
            p_vol = put_at_strike[put_at_strike["maturity_date"] == mat]["volume"].iloc[
                0
            ]
            combined = c_vol + p_vol
            if combined > best_combined_vol:
                best_combined_vol = combined
                best_maturity = mat

        atm_call = call_at_strike[
            call_at_strike["maturity_date"] == best_maturity
        ].iloc[0]
        atm_put = put_at_strike[put_at_strike["maturity_date"] == best_maturity].iloc[0]

        return atm_call, atm_put

    def _calc_iv(self, option_row, spot, trade_date, r):
        if option_row is None or option_row.empty:
            return 0.0
        try:
            strike = float(option_row["strike_price"])
            bid = float(option_row["bid"])
            ask = float(option_row["ask"])
            maturity = str(option_row["maturity_date"])
            if ask <= 0 or bid <= 0 or ask == bid:
                return 0.0
            market_price = (bid + ask) / 2.0
            trade_dt = datetime.strptime(trade_date, "%Y-%m-%d")
            maturity_dt = datetime.strptime(maturity, "%Y-%m-%d")
            t = (maturity_dt - trade_dt).days / 365.0
            if t <= 0:
                return 0.0
            option_type = str(option_row.get("option_type", "C"))
            iv = implied_volatility(market_price, spot, strike, t, r, option_type)
            return iv if iv > 0 else 0.0
        except (KeyError, ValueError, TypeError):
            return 0.0

    def get_underlying_price(self, trade_date: str) -> float:
        return self.get_spot_price(trade_date)
