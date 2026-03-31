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

        # Check for required market data columns
        if "bid" not in options.columns or "ask" not in options.columns:
            return 0.0

        s = float(self.data_interface.get_underlying_price(date))
        calls = options[options["option_type"] == "C"]
        puts = options[options["option_type"] == "P"]
        if calls.empty or puts.empty:
            return 0.0

        calls = calls.copy()
        calls["dte"] = (
            pd.to_datetime(calls["maturity_date"]) - pd.to_datetime(date)
        ).dt.days
        valid_calls = calls[calls["dte"] >= self.config.min_dte]
        if valid_calls.empty:
            return 0.0
        valid_calls = valid_calls.copy()
        valid_calls["moneyness"] = valid_calls["strike_price"].values / s
        idx_call = valid_calls["moneyness"].sub(1).abs().idxmin()
        row_call = valid_calls.loc[idx_call]
        k = float(row_call["strike_price"])
        dte = int(row_call["dte"])

        puts = puts.copy()
        puts["dte"] = (
            pd.to_datetime(puts["maturity_date"]) - pd.to_datetime(date)
        ).dt.days
        valid_puts = puts[puts["dte"] >= self.config.min_dte]
        if valid_puts.empty:
            return 0.0
        valid_puts = valid_puts.copy()
        valid_puts["moneyness"] = valid_puts["strike_price"].values / s
        idx_put = valid_puts["moneyness"].sub(1).abs().idxmin()
        row_put = valid_puts.loc[idx_put]

        if dte <= 0:
            return 0.0
        t = dte / 252.0

        call_market_price = float((row_call["bid"] + row_call["ask"]) / 2)
        call_iv = 0.0
        if call_market_price > 0:
            call_iv = implied_volatility(
                market_price=call_market_price,
                s=s,
                k=k,
                t=t,
                r=self.config.risk_free_rate,
                option_type="C",
            )

        put_market_price = float((row_put["bid"] + row_put["ask"]) / 2)
        put_iv = 0.0
        if put_market_price > 0:
            put_iv = implied_volatility(
                market_price=put_market_price,
                s=s,
                k=k,
                t=t,
                r=self.config.risk_free_rate,
                option_type="P",
            )

        if call_iv > 0 and put_iv > 0:
            return (call_iv + put_iv) / 2.0
        elif call_iv > 0:
            return call_iv
        elif put_iv > 0:
            return put_iv
        return 0.0

    def _compute_iv_for_position(
        self, date: str, strike: float, dte: int, option_type: str = "C"
    ) -> float:
        """
        计算指定strike和DTE的隐含波动率。
        用于Greeks计算，确保IV与Position参数一致。

        Args:
            date: 交易日期
            strike: 期权strike价格
            dte: 到期天数(days to expiry)
            option_type: 期权类型，"C" for Call, "P" for Put

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

        # 找到对应strike的期权
        strike_opts = options[
            (options["strike_price"] == strike)
            & (options["option_type"] == option_type)
        ]
        if strike_opts.empty:
            logger.warning(
                f"IV calc failed: no {option_type} option for strike={strike}, date={date}, dte={dte}"
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
            option_type=option_type,
        )
        if iv <= 0:
            logger.warning(
                f"IV calc failed: implied_volatility returned {iv}, strike={strike}, dte={dte}"
            )
            return 0.0
        return iv

    def _compute_avg_iv(self, date: str, strike: float, dte: int) -> float:
        """
        计算call和put隐含波动率的平均值。
        用于Greeks计算，确保IV与Position参数一致。

        Args:
            date: 交易日期
            strike: 期权strike价格
            dte: 到期天数(days to expiry)

        Returns:
            call和put隐含波动率的平均值，如果计算失败返回0.0
        """
        call_iv = self._compute_iv_for_position(date, strike, dte, "C")
        put_iv = self._compute_iv_for_position(date, strike, dte, "P")
        if call_iv <= 0 or put_iv <= 0:
            return 0.0
        return (call_iv + put_iv) / 2.0

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

        if iv_percentile is None or current_iv == 0.0:
            return result

        atm_call_opt, atm_put_opt = self.data_interface.get_atm_options(
            date,
            moneyness_range=self.config.moneyness_range,
            min_dte=self.config.min_dte,
            min_volume=self.config.min_volume,
            risk_free_rate=self.config.risk_free_rate,
            max_call_put_iv_diff=self.config.max_call_put_iv_diff,
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

                call_price = call_ask * (1 + self.config.option_slippage)
                put_price = put_ask * (1 + self.config.option_slippage)

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
                avg_iv = self._compute_avg_iv(date, strike, dte)
                if avg_iv <= 0:
                    logger.warning(
                        f"IV fallback: pos_id={pos.trade_id} date={date} strike={strike} "
                        f"dte={dte} falling back to 0.20"
                    )
                    avg_iv = 0.20
                call_iv = avg_iv
                put_iv = avg_iv
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
                risk_free_rate=self.config.risk_free_rate,
                max_call_put_iv_diff=self.config.max_call_put_iv_diff,
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

            avg_iv = self._compute_avg_iv(date, strike, t_raw)
            if avg_iv <= 0:
                logger.warning(
                    f"IV fallback: pos_id={pos.trade_id} date={date} strike={strike} "
                    f"dte={t_raw} falling back to 0.20"
                )
                avg_iv = 0.20
            call_iv = avg_iv
            put_iv = avg_iv

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

            # First hedge block - hedge existing positions (on non-open dates)
            # Opening and closing days: do NOT hedge (design doc Sec 5.4)
            # Use net_delta (pos_delta + net_hedge_qty) for hedge decision
            net_delta = pos_delta + pos.net_hedge_qty
            if (
                date != pos.open_date
                and date != pos.close_date
                and should_hedge(abs(net_delta), self.config.delta_hedge_threshold)
            ):
                # If there's an existing open hedge, close it first
                if pos.hedge_records and pos.hedge_records[-1].get("exit_date") is None:
                    pos.close_current_hedge(
                        date,
                        s,
                        self.config.etf_commission,
                        self.config.etf_handling_fee,
                        self.config.etf_min_commission,
                        self.config.etf_slippage,
                    )
                # Then open a NEW hedge targeting full delta neutrality
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
                    pos.add_hedge_record(date, hedge_qty, exec_price, hedge_total_cost)
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
                # Always update post-hedge delta after hedge decision/execution
                post_hedge_delta = pos_delta + pos.net_hedge_qty
                pos.update_last_daily_greeks_post_hedge(post_hedge_delta)

        result["equity"] = self.portfolio.total_equity()
        result["cash"] = self.portfolio.cash
        return result
