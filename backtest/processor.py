from config import Config
from portfolio.portfolio import Portfolio
from portfolio.position import OptionLeg, Position
from data_source.interface import DataInterface
from core.signal import check_open_signals, check_close_signals, should_hedge
from core.hedge import hedge_delta_to_zero
from core.greeks import black_scholes_greeks, implied_volatility
from core.vol_cone import current_iv_percentile
import logging
import pandas as pd

logger = logging.getLogger(__name__)


class DailyProcessor:
    def __init__(
        self,
        config: Config,
        portfolio: Portfolio,
        data_interface: DataInterface,
        writer=None,
    ):
        self.config = config
        self.portfolio = portfolio
        self.data_interface = data_interface
        self.writer = writer
        self._iv_history: pd.DataFrame = pd.DataFrame(columns=["date", "dte", "iv"])

    def _compute_current_iv(self, date: str, options: pd.DataFrame) -> float:
        if options.empty:
            return 0.0
        s = float(self.data_interface.get_underlying_price(date))
        calls = options[options["option_type"] == "C"]
        if calls.empty:
            return 0.0
        calls = calls.copy()
        calls["dte"] = (
            pd.to_datetime(calls["maturity_date"]) - pd.to_datetime(date)
        ).dt.days
        valid = calls[calls["dte"] >= 7]
        if valid.empty:
            return 0.0
        valid = valid.copy()
        valid["moneyness"] = valid["strike_price"].values / s
        idx = valid["moneyness"].sub(1).abs().idxmin()
        row = valid.loc[idx]
        k = float(row["strike_price"])
        market_price = float((row["bid"] + row["ask"]) / 2)
        dte = int(row["dte"])
        if market_price <= 0 or dte <= 0:
            return 0.0
        t = dte / 252.0
        iv = implied_volatility(
            market_price=market_price,
            s=s,
            k=k,
            t=t,
            r=self.config.risk_free_rate,
            option_type="C",
        )
        return iv

    def _compute_iv_for_position(self, date: str, strike: float, dte: int) -> float:
        """
        计算指定strike和DTE的隐含波动率。
        用于Greeks计算，确保IV与Position参数一致。

        Args:
            date: 交易日期
            strike: 期权strike价格
            dte: 到期天数(days to expiry)

        Returns:
            隐含波动率，如果计算失败返回0.0
        """
        options = self.data_interface.get_options(date)
        if options.empty:
            logger.warning(
                f"IV calc failed: no options data for date={date}, strike={strike}, dte={dte}"
            )
            return 0.0

        s = float(self.data_interface.get_underlying_price(date))
        t = max(dte, 1) / 252.0
        if t <= 0:
            logger.warning(
                f"IV calc failed: invalid t={t} for date={date}, strike={strike}, dte={dte}"
            )
            return 0.0

        # 找到对应strike的Call期权
        strike_opts = options[
            (options["strike_price"] == strike) & (options["option_type"] == "C")
        ]
        if strike_opts.empty:
            logger.warning(
                f"IV calc failed: no call option for strike={strike}, date={date}, dte={dte}"
            )
            return 0.0

        # 选择DTE最接近目标的期权
        strike_opts = strike_opts.copy()
        strike_opts["opt_dte"] = (
            pd.to_datetime(strike_opts["maturity_date"]) - pd.to_datetime(date)
        ).dt.days
        strike_opts = strike_opts[strike_opts["opt_dte"] >= 1]
        if strike_opts.empty:
            logger.warning(
                f"IV calc failed: no valid DTE for strike={strike}, target_dte={dte}, date={date}"
            )
            return 0.0

        strike_opts["dte_diff"] = abs(strike_opts["opt_dte"] - dte)
        closest = strike_opts.nsmallest(1, "dte_diff")

        market_price = float((closest["bid"].values[0] + closest["ask"].values[0]) / 2)
        if market_price <= 0:
            logger.warning(
                f"IV calc failed: invalid market_price={market_price}, strike={strike}, dte={dte}"
            )
            return 0.0

        iv = implied_volatility(
            market_price=market_price,
            s=s,
            k=strike,
            t=t,
            r=self.config.risk_free_rate,
            option_type="C",
        )
        if iv <= 0:
            logger.warning(
                f"IV calc failed: implied_volatility returned {iv}, strike={strike}, dte={dte}"
            )
            return 0.0
        return iv

    def _accumulate_iv(self, date: str, iv: float, dte: int):
        new_row = pd.DataFrame({"date": [date], "dte": [dte], "iv": [iv]})
        if self._iv_history.empty:
            self._iv_history = new_row
        else:
            self._iv_history = pd.concat([self._iv_history, new_row], ignore_index=True)

    def _get_dte_for_strike(self, date: str, strike: float) -> int:
        options = self.data_interface.get_options(date)
        if options.empty:
            return 30
        strike_opts = options[
            (options["strike_price"] == strike) & (options["option_type"] == "C")
        ]
        if strike_opts.empty:
            return 30
        dte = (
            pd.to_datetime(strike_opts["maturity_date"].iloc[0]) - pd.to_datetime(date)
        ).days
        return max(dte, 1)

    def process_day(self, date: str) -> dict:
        result = {
            "date": date,
            "iv_percentile": None,
            "opened": [],
            "closed": [],
            "hedges": [],
            "equity": self.portfolio.total_equity(),
            "cash": self.portfolio.cash,
        }

        try:
            underlying = self.data_interface.get_underlying_price(date)
        except (KeyError, OSError, EOFError):
            return result
        options = self.data_interface.get_options(date)

        current_iv = self._compute_current_iv(date, options)

        dte_for_iv = self._get_dte_for_strike(date, underlying)
        self._accumulate_iv(date, current_iv, dte_for_iv)

        iv_percentile = current_iv_percentile(
            current_iv,
            date,
            self._iv_history,
            target_tenor=self.config.target_tenor,
            lookback_days=self.config.lookback_days,
        )

        result["iv_percentile"] = iv_percentile

        if iv_percentile is None:
            return result

        atm_call_opt, atm_put_opt = self.data_interface.get_atm_options(
            date,
            moneyness_range=self.config.moneyness_range,
            min_dte=self.config.min_dte,
            min_volume=self.config.min_volume,
            min_price=self.config.min_option_price,
        )

        if atm_call_opt is not None and atm_put_opt is not None:
            call_vol = int(atm_call_opt.get("volume", 0))
            put_vol = int(atm_put_opt.get("volume", 0))
            open_ok, _ = check_open_signals(
                iv_percentile,
                self.portfolio.cash,
                call_vol,
                put_vol,
                self.config.open_threshold,
                self.config.min_volume,
            )
            if (
                open_ok
                and not self.portfolio.has_open_position()
                and not self.portfolio.strike_has_position(
                    float(atm_call_opt["strike_price"])
                )
            ):
                strike = float(atm_call_opt["strike_price"])
                maturity = str(atm_call_opt["maturity_date"])

                call_ask = float(atm_call_opt["ask"])
                put_ask = float(atm_put_opt["ask"])

                call_price = call_ask * (1 - self.config.option_slippage)
                put_price = put_ask * (1 - self.config.option_slippage)

                call_notional = call_price * 10000
                put_notional = put_price * 10000
                total_notional = call_notional + put_notional

                call_commission = max(
                    call_notional * self.config.option_commission,
                    self.config.option_min_commission,
                )
                put_commission = max(
                    put_notional * self.config.option_commission,
                    self.config.option_min_commission,
                )
                total_cost = (
                    total_notional
                    - call_commission
                    - put_commission
                    - total_notional * self.config.option_handling_fee
                    - total_notional * self.config.option_transfer_fee
                )

                call_leg = OptionLeg(
                    order_book_id=str(atm_call_opt["order_book_id"]),
                    strike_price=strike,
                    maturity_date=maturity,
                    option_type="C",
                    open_price=float(atm_call_opt["close"]),
                )
                put_leg = OptionLeg(
                    order_book_id=str(atm_put_opt["order_book_id"]),
                    strike_price=strike,
                    maturity_date=maturity,
                    option_type="P",
                    open_price=float(atm_put_opt["close"]),
                )

                pos = self.portfolio.open_position(
                    date, strike, maturity, call_leg, put_leg, total_cost
                )
                result["opened"].append(pos.trade_id)
                result["equity"] = self.portfolio.total_equity()
                result["cash"] = self.portfolio.cash

                # Record Greeks for the newly opened position on the same day
                s = underlying
                dte = (pd.to_datetime(maturity) - pd.to_datetime(date)).days
                t = max(dte, 1) / 252.0
                call_iv = self._compute_iv_for_position(date, strike, dte)
                if call_iv <= 0:
                    logger.warning(
                        f"IV fallback: pos_id={pos.trade_id} date={date} strike={strike} "
                        f"dte={dte} falling back to 0.20"
                    )
                    call_iv = 0.20
                put_iv = call_iv
                if t > 0:
                    call_greeks = black_scholes_greeks(
                        s, strike, t, self.config.risk_free_rate, call_iv, "C"
                    )
                    put_greeks = black_scholes_greeks(
                        s, strike, t, self.config.risk_free_rate, put_iv, "P"
                    )
                    pos_delta = (call_greeks["delta"] + put_greeks["delta"]) * 10000
                    pos_gamma = (call_greeks["gamma"] + put_greeks["gamma"]) * 10000
                    pos_vega = (call_greeks["vega"] + put_greeks["vega"]) * 10000
                    pos_theta = (call_greeks["theta"] + put_greeks["theta"]) * 10000
                    pos.add_daily_greeks(
                        date, pos_delta, pos_gamma, pos_vega, pos_theta
                    )

                return result

        for pos in self.portfolio.get_open_positions():
            atm_c, atm_p = self.data_interface.get_atm_options(
                date,
                moneyness_range=self.config.moneyness_range,
                min_dte=self.config.min_dte,
                min_volume=self.config.min_volume,
                min_price=self.config.min_option_price,
            )
            if atm_c is None or atm_p is None:
                continue

            pos_maturity = pd.to_datetime(pos.maturity_date)
            current_dt = pd.to_datetime(date)
            dte = (pos_maturity - current_dt).days

            pos_iv = self._compute_current_iv(
                date, self.data_interface.get_options(date)
            )
            self._accumulate_iv(date, pos_iv, dte)

            pos_iv_percentile = current_iv_percentile(
                pos_iv,
                date,
                self._iv_history,
                target_tenor=self.config.target_tenor,
                lookback_days=self.config.lookback_days,
            )

            s = underlying
            strike = float(pos.strike_price)
            t_raw = dte
            t = max(t_raw, 1) / 252.0

            call_iv = self._compute_iv_for_position(date, strike, t_raw)
            if call_iv <= 0:
                logger.warning(
                    f"IV fallback: pos_id={pos.trade_id} date={date} strike={strike} "
                    f"dte={t_raw} falling back to 0.20"
                )
                call_iv = 0.20
            put_iv = call_iv

            pos_delta = 0.0
            pos_gamma = 0.0
            pos_vega = 0.0
            pos_theta = 0.0

            if t > 0:
                call_greeks = black_scholes_greeks(
                    s, strike, t, self.config.risk_free_rate, call_iv, "C"
                )
                put_greeks = black_scholes_greeks(
                    s, strike, t, self.config.risk_free_rate, put_iv, "P"
                )

                pos_delta = (call_greeks["delta"] + put_greeks["delta"]) * 10000
                pos_gamma = (call_greeks["gamma"] + put_greeks["gamma"]) * 10000
                pos_vega = (call_greeks["vega"] + put_greeks["vega"]) * 10000
                pos_theta = (call_greeks["theta"] + put_greeks["theta"]) * 10000

                pos.add_daily_greeks(date, pos_delta, pos_gamma, pos_vega, pos_theta)

            if pos_iv_percentile is not None:
                close_ok, _ = check_close_signals(
                    pos_iv_percentile,
                    dte,
                    pos.holding_days(date),
                    self.config.close_threshold,
                    self.config.close_dte_threshold,
                    self.config.max_holding_days,
                )
                if close_ok:
                    close_call_bid = float(atm_c["bid"])
                    close_put_bid = float(atm_p["bid"])

                    close_call_price = close_call_bid * (
                        1 - self.config.option_slippage
                    )
                    close_put_price = close_put_bid * (1 - self.config.option_slippage)

                    close_call_notional = close_call_price * 10000
                    close_put_notional = close_put_price * 10000
                    close_total_notional = close_call_notional + close_put_notional

                    close_call_commission = max(
                        close_call_notional * self.config.option_commission,
                        self.config.option_min_commission,
                    )
                    close_put_commission = max(
                        close_put_notional * self.config.option_commission,
                        self.config.option_min_commission,
                    )
                    close_proceeds = (
                        close_total_notional
                        - close_call_commission
                        - close_put_commission
                        - close_total_notional * self.config.option_handling_fee
                        - close_total_notional * self.config.option_transfer_fee
                    )

                    self.portfolio.close_position(
                        pos.trade_id, date, close_proceeds, underlying
                    )
                    result["closed"].append(pos.trade_id)
                    result["equity"] = self.portfolio.total_equity()
                    result["cash"] = self.portfolio.cash
                    continue

            if date != pos.open_date:
                if should_hedge(abs(pos_delta), self.config.delta_hedge_threshold):
                    hedge_qty, hedge_cost, hedge_total_cost = hedge_delta_to_zero(
                        current_delta=pos_delta,
                        etf_price=s,
                        etf_min_commission=self.config.etf_min_commission,
                        etf_commission=self.config.etf_commission,
                        etf_handling_fee=self.config.etf_handling_fee,
                        etf_slippage=self.config.etf_slippage,
                    )
                    if hedge_qty != 0:
                        slippage_factor = (
                            1 + self.config.etf_slippage
                            if hedge_qty > 0
                            else 1 - self.config.etf_slippage
                        )
                        exec_price = s * slippage_factor
                        pos.add_hedge_record(
                            date, hedge_qty, exec_price, hedge_total_cost
                        )
                        result["hedges"].append(
                            {
                                "trade_id": pos.trade_id,
                                "date": date,
                                "qty": hedge_qty,
                                "price": exec_price,
                                "cost": hedge_total_cost,
                            }
                        )
                        result["equity"] = self.portfolio.total_equity()
                        result["cash"] = self.portfolio.cash
                    continue

            s = underlying
            strike = float(pos.strike_price)
            t_raw = dte
            t = max(t_raw, 1) / 252.0

            call_iv = self._compute_iv_for_position(date, strike, t_raw)
            if call_iv <= 0:
                logger.warning(
                    f"IV fallback: pos_id={pos.trade_id} date={date} strike={strike} "
                    f"dte={t_raw} falling back to 0.20"
                )
                call_iv = 0.20
            put_iv = call_iv

            if t > 0:
                call_greeks = black_scholes_greeks(
                    s, strike, t, self.config.risk_free_rate, call_iv, "C"
                )
                put_greeks = black_scholes_greeks(
                    s, strike, t, self.config.risk_free_rate, put_iv, "P"
                )

                pos_delta = (call_greeks["delta"] + put_greeks["delta"]) * 10000
                pos_gamma = (call_greeks["gamma"] + put_greeks["gamma"]) * 10000
                pos_vega = (call_greeks["vega"] + put_greeks["vega"]) * 10000
                pos_theta = (call_greeks["theta"] + put_greeks["theta"]) * 10000

                pos.add_daily_greeks(date, pos_delta, pos_gamma, pos_vega, pos_theta)

                if date != pos.open_date:
                    if should_hedge(abs(pos_delta), self.config.delta_hedge_threshold):
                        hedge_qty, hedge_cost, hedge_total_cost = hedge_delta_to_zero(
                            current_delta=pos_delta,
                            etf_price=s,
                            etf_min_commission=self.config.etf_min_commission,
                            etf_commission=self.config.etf_commission,
                            etf_handling_fee=self.config.etf_handling_fee,
                            etf_slippage=self.config.etf_slippage,
                        )
                        if hedge_qty != 0:
                            slippage_factor = (
                                1 + self.config.etf_slippage
                                if hedge_qty > 0
                                else 1 - self.config.etf_slippage
                            )
                            exec_price = s * slippage_factor
                            pos.add_hedge_record(
                                date, hedge_qty, exec_price, hedge_total_cost
                            )
                            result["hedges"].append(
                                {
                                    "trade_id": pos.trade_id,
                                    "date": date,
                                    "qty": hedge_qty,
                                    "price": exec_price,
                                }
                            )

        result["equity"] = self.portfolio.total_equity()
        result["cash"] = self.portfolio.cash
        return result
