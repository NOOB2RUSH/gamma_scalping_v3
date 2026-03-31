from datetime import datetime
import pandas as pd

from config import Config
from portfolio.portfolio import Portfolio
from backtest.processor import DailyProcessor
from backtest.writer import ResultWriter
from analysis.performance import PerformanceAnalyzer
from analysis.greeks_pnl import GreeksPnlAnalyzer
from core.greeks import implied_volatility


class BacktestEngine:
    MIN_START_DATE = "2024-12-16"

    def __init__(self, config: Config, data_interface, results_dir: str | None = None):
        self.config = config
        self.data_interface = data_interface
        self.portfolio = Portfolio(config.initial_capital)
        if results_dir is None:
            results_dir = datetime.now().strftime("results/%Y-%m-%d_%H-%M-%S")
        self.results_dir = results_dir
        self.writer = ResultWriter(self.results_dir)
        self.processor = DailyProcessor(
            config, self.portfolio, data_interface, writer=self.writer
        )
        self.processed_dates: list[str] = []
        self.results: dict = {}

    def run(self):
        self.processed_dates = []
        self.results = {
            "trades": [],
            "equity_curve": [],
            "config": self.config.to_dict(),
        }
        self.writer._ensure_dir(self.writer.results_dir / "trades")
        self.writer._ensure_dir(self.writer.results_dir / "logs")

        iv_history_df = pd.DataFrame()
        underlying_prices: dict[str, float] = {}

        for date in self.data_interface.trading_dates:
            self.processed_dates.append(date)

            day_result = self.processor.process_day(date)

            try:
                s = self.data_interface.get_underlying_price(date)
                underlying_prices[date] = s
            except (FileNotFoundError, KeyError, OSError, EOFError):
                continue

            if date < self.MIN_START_DATE:
                continue

            call_opt, put_opt = self.data_interface.get_atm_options(
                date,
                moneyness_range=self.config.moneyness_range,
                min_dte=self.config.min_dte,
                min_volume=self.config.min_volume,
                risk_free_rate=self.config.risk_free_rate,
                max_call_put_iv_diff=self.config.max_call_put_iv_diff,
            )
            if call_opt is not None and put_opt is not None:
                # Compute model-implied IV from market price using Call+Put average
                s = float(self.data_interface.get_underlying_price(date))
                k = float(call_opt["strike_price"])
                opt_date = datetime.strptime(date, "%Y-%m-%d")
                mat_date = datetime.strptime(call_opt["maturity_date"], "%Y-%m-%d")
                dte = (mat_date - opt_date).days
                t = max(dte, 1) / 252.0

                if t > 0:
                    # Compute Call IV
                    call_market_price = float((call_opt["bid"] + call_opt["ask"]) / 2)
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

                    # Compute Put IV
                    put_market_price = float((put_opt["bid"] + put_opt["ask"]) / 2)
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

                    # Average Call and Put IV
                    if call_iv > 0 and put_iv > 0:
                        iv = (call_iv + put_iv) / 2.0
                        iv_history_df = pd.concat(
                            [
                                iv_history_df,
                                pd.DataFrame([{"date": date, "dte": dte, "iv": iv}]),
                            ],
                            ignore_index=True,
                        )

            prev_equity = (
                self.results["equity_curve"][-1]["equity"]
                if self.results["equity_curve"]
                else self.config.initial_capital
            )
            current_equity = self.processor.portfolio.total_equity()
            daily_pnl = current_equity - prev_equity
            self.results["equity_curve"].append(
                {
                    "date": date,
                    "equity": current_equity,
                    "daily_pnl": daily_pnl,
                    "cumulative_pnl": current_equity - self.config.initial_capital,
                }
            )

        last_date = (
            self.data_interface.trading_dates[-1]
            if self.data_interface.trading_dates
            else None
        )
        try:
            last_underlying = (
                self.data_interface.get_underlying_price(last_date)
                if last_date
                else 0.0
            )
        except (FileNotFoundError, KeyError, OSError, EOFError):
            last_underlying = 0.0
        for pos in self.processor.portfolio.get_open_positions():
            close_proceeds = pos.open_cost * 0.95
            self.portfolio.close_position(
                pos.trade_id, last_date, close_proceeds, last_underlying
            )

        # Convert iv_history DataFrame to dict for Greeks P&L
        iv_history: dict[str, float] = {}
        if not iv_history_df.empty:
            iv_history = dict(zip(iv_history_df["date"], iv_history_df["iv"]))

        # Persist underlying prices and IV history (DataFrame with date, dte, iv)
        self.writer.write_underlying_prices(underlying_prices)
        self.writer.write_iv_history(iv_history_df)

        # Analyze Greeks P&L for all closed positions
        greeks_by_date: dict[str, dict] = {}
        greeks_analyzer = GreeksPnlAnalyzer()
        for pos in self.processor.portfolio.positions.values():
            if pos.is_closed and pos.daily_greeks:
                interval_results = greeks_analyzer.analyze_position_by_interval(
                    pos, underlying_prices, iv_history
                )
                for interval in interval_results:
                    date = interval["date"]
                    if date not in greeks_by_date:
                        greeks_by_date[date] = {
                            "delta_pnl": 0.0,
                            "gamma_pnl": 0.0,
                            "theta_pnl": 0.0,
                            "vega_pnl": 0.0,
                        }
                    greeks_by_date[date]["delta_pnl"] += interval["delta_pnl"]
                    greeks_by_date[date]["gamma_pnl"] += interval["gamma_pnl"]
                    greeks_by_date[date]["theta_pnl"] += interval["theta_pnl"]
                    greeks_by_date[date]["vega_pnl"] += interval["vega_pnl"]

        analyzer = PerformanceAnalyzer()
        analyzer.trades = [
            p.to_dict()
            for p in self.processor.portfolio.positions.values()
            if p.is_closed
        ]
        analyzer.equity_curve = self.results["equity_curve"]
        self.results["summary"] = analyzer.compute_summary(greeks_by_date)
        self.results["equity_stats"] = analyzer.compute_equity_curve_stats()
        self.results["greeks_by_date"] = greeks_by_date

        self._write_trade_files()
        self._write_summary()
        self._write_equity_curve()
        self._write_equity_curve_png()
        self._write_daily_logs()

    def _write_trade_files(self):
        for pos in self.processor.portfolio.positions.values():
            if pos.is_closed:
                self.writer.write_trade(pos.to_dict())

    def _write_summary(self):
        self.writer.write_config(self.results["config"])
        self.writer.write_summary(self.results["summary"])

    def _write_equity_curve(self):
        self.writer.write_equity_curve(self.results["equity_curve"])
        self.writer.write_performance_csv(self.results.get("greeks_by_date", {}))

    def _write_daily_logs(self):
        pass

    def _write_equity_curve_png(self):
        from analysis.visualization import plot_equity_curve
        import pandas as pd

        equity_df = pd.DataFrame(self.results["equity_curve"])
        if equity_df.empty:
            return
        output_path = self.writer.results_dir / "equity_curve.png"
        plot_equity_curve(equity_df, output_path=str(output_path))
