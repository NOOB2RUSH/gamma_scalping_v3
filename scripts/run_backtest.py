#!/usr/bin/env python3
"""
Gamma Scalping Backtest — Entry Point

Usage:
    python3 scripts/run_backtest.py                          # defaults
    python3 scripts/run_backtest.py --data ./data           # custom data dir
    python3 scripts/run_backtest.py --capital 2000000        # custom capital
    python3 scripts/run_backtest.py --open-threshold 0.20    # custom open threshold
    python3 scripts/run_backtest.py --start 2025-01-01       # date range
    python3 scripts/run_backtest.py --end 2025-06-30
    python3 scripts/run_backtest.py --results ./results/run1  # custom output dir
    python3 scripts/run_backtest.py --list-params            # show all parameters
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config
from data_source.local import LocalDataSource
from data_source.interface import DataInterface
from portfolio.portfolio import Portfolio
from backtest.engine import BacktestEngine


def parse_args():
    parser = argparse.ArgumentParser(
        description="50ETF Gamma Scalping Backtest Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--data",
        "-d",
        default="./data",
        help="Data directory (default: ./data)",
    )
    parser.add_argument(
        "--results",
        "-r",
        default=None,
        help="Results output directory (default: results/YYYY-MM-DD_HH-MM-SS/)",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=None,
        help=f"Initial capital (default: {Config().initial_capital:,.0f})",
    )
    parser.add_argument(
        "--open-threshold",
        type=float,
        dest="open_threshold",
        default=None,
        help=f"IV percentile to open position (default: {Config().open_threshold})",
    )
    parser.add_argument(
        "--close-threshold",
        type=float,
        dest="close_threshold",
        default=None,
        help=f"IV percentile to close position (default: {Config().close_threshold})",
    )
    parser.add_argument(
        "--delta-hedge",
        type=float,
        dest="delta_hedge_threshold",
        default=None,
        help=f"Delta threshold to trigger hedge (default: {Config().delta_hedge_threshold})",
    )
    parser.add_argument(
        "--max-holding",
        type=int,
        dest="max_holding_days",
        default=None,
        help=f"Max days to hold a position (default: {Config().max_holding_days})",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=None,
        help=f"IV percentile lookback window in days (default: {Config().lookback_days})",
    )
    parser.add_argument(
        "--min-dte",
        type=int,
        dest="min_dte",
        default=None,
        help=f"Min DTE for option contracts (default: {Config().min_dte})",
    )
    parser.add_argument(
        "--target-tenor",
        type=int,
        dest="target_tenor",
        default=None,
        help=f"Target DTE tenor for IV percentile (default: {Config().target_tenor})",
    )
    parser.add_argument(
        "--start",
        default=None,
        help="Start date (YYYY-MM-DD). Default: first available date",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="End date (YYYY-MM-DD). Default: last available date",
    )
    parser.add_argument(
        "--list-params",
        action="store_true",
        help="Print all default parameters and exit",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print progress during backtest",
    )
    return parser.parse_args()


def apply_overrides(cfg: Config, args) -> Config:
    params = {
        "initial_capital": args.capital,
        "open_threshold": args.open_threshold,
        "close_threshold": args.close_threshold,
        "delta_hedge_threshold": args.delta_hedge_threshold,
        "max_holding_days": args.max_holding_days,
        "lookback_days": args.lookback,
        "target_tenor": args.target_tenor,
        "min_dte": args.min_dte,
    }
    for name, value in params.items():
        if value is not None:
            setattr(cfg, name, value)
    return cfg


def print_params(cfg: Config):
    print("=" * 60)
    print("Gamma Scalping — Default Parameters")
    print("=" * 60)
    fields = [
        ("initial_capital", "Initial capital", "¥"),
        ("lookback_days", "IV percentile lookback", "days"),
        ("target_tenor", "Target DTE tenor", "days"),
        ("open_threshold", "Open IV percentile threshold", "%"),
        ("close_threshold", "Close IV percentile threshold", "%"),
        ("close_dte_threshold", "Close DTE threshold", "days"),
        ("max_holding_days", "Max holding days", "days"),
        ("delta_hedge_threshold", "Delta hedge threshold", "delta"),
        ("moneyness_range", "ATM moneyness range", ""),
        ("min_dte", "Min DTE for options", "days"),
        ("min_volume", "Min option volume", "lots"),
        ("min_option_price", "Min option price", "¥"),
        ("risk_free_rate", "Risk-free rate", ""),
        ("option_slippage", "Option slippage", ""),
        ("etf_slippage", "ETF slippage", ""),
    ]
    for attr, label, unit in fields:
        val = getattr(cfg, attr)
        if attr == "moneyness_range":
            print(f"  {label:<30} [{val[0]:.2f}, {val[1]:.2f}]")
        elif unit == "¥":
            print(f"  {label:<30} {val:>12,.2f} {unit}")
        elif unit == "%":
            print(f"  {label:<30} {val:>12.1%}")
        elif unit == "days" or unit == "delta":
            print(f"  {label:<30} {val:>12}")
        else:
            print(f"  {label:<30} {val}")
    print("=" * 60)


def print_summary(results: dict, elapsed: float, results_dir: Path):
    summary = results.get("summary", {})
    equity_stats = results.get("equity_stats", {})
    equity_curve = results.get("equity_curve", [])
    trades = results.get("trades", [])

    start_equity = equity_stats.get("start_equity", 0)
    end_equity = equity_stats.get("end_equity", 0)
    total_return = equity_stats.get("total_return_pct", 0)

    if len(equity_curve) > 1:
        rets = [
            e["daily_pnl"] / equity_curve[i - 1]["equity"]
            for i, e in enumerate(equity_curve)
            if i > 0 and equity_curve[i - 1]["equity"] != 0
        ]
        sharpe = (
            (
                sum(rets)
                / len(rets)
                / (sum((r - sum(rets) / len(rets)) ** 2 for r in rets) / len(rets))
                ** 0.5
                * (252**0.5)
            )
            if len(rets) > 1
            and (sum((r - sum(rets) / len(rets)) ** 2 for r in rets) / len(rets)) > 0
            else 0.0
        )
        peak = 0.0
        max_dd = 0.0
        for e in equity_curve:
            if e["equity"] > peak:
                peak = e["equity"]
            dd = (e["equity"] - peak) / peak if peak > 0 else 0.0
            if dd < max_dd:
                max_dd = dd
    else:
        sharpe = 0.0
        max_dd = 0.0

    win_rate = summary.get("win_rate", 0)
    n_trades = summary.get("total_trades", len(trades))
    total_pnl = summary.get("total_realized_pnl", 0)
    avg_pnl = total_pnl / n_trades if n_trades > 0 else 0.0

    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║              BACKTEST COMPLETE — SUMMARY                    ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print(f"║  Results:    {str(results_dir):<46}  ║")
    print(f"║  Duration:   {elapsed:>6.1f}s                                       ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print(f"║  Total Return    {total_return:>8.2%}   Sharpe      {sharpe:>6.2f}     ║")
    print(f"║  Max Drawdown  {max_dd:>10.2%}   Win Rate   {win_rate:>7.1%}     ║")
    print(f"║  # Trades        {n_trades:>6}   Avg PnL   {avg_pnl:>10,.0f}     ║")
    print(f"║  Total PnL    {total_pnl:>12,.0f}                             ║")
    print(
        f"║  Final Equity {end_equity:>12,.0f}  ({end_equity - start_equity:>+,.0f})     ║"
    )

    # Greeks P&L 分解
    greeks_delta = summary.get("greeks_delta_pnl", 0.0)
    greeks_gamma = summary.get("greeks_gamma_pnl", 0.0)
    greeks_theta = summary.get("greeks_theta_pnl", 0.0)
    greeks_vega = summary.get("greeks_vega_pnl", 0.0)
    greeks_total = summary.get("greeks_total_pnl", 0.0)
    greeks_diff = summary.get("greeks_vs_pnl_diff", 0.0)
    greeks_pct = summary.get("greeks_vs_pnl_pct", 0.0)

    print("╠══════════════════════════════════════════════════════════════╣")
    print("║                    GREEKS P&L 分解                          ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print(
        f"║  Delta P&L   {greeks_delta:>12,.0f}   Theta P&L  {greeks_theta:>10,.0f}     ║"
    )
    print(
        f"║  Gamma P&L   {greeks_gamma:>12,.0f}   Vega P&L   {greeks_vega:>10,.0f}     ║"
    )
    print(f"║  Greeks Total{greeks_total:>12,.0f}                             ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print(
        f"║  Greeks vs Actual: {greeks_diff:>+9,.0f}  (差异 {greeks_pct:>5.1f}%)        ║"
    )

    print("╚══════════════════════════════════════════════════════════════╝")

    print()
    print("Output files:")
    for f in sorted(results_dir.rglob("*")):
        if f.is_file():
            size = f.stat().st_size
            print(f"  {str(f.relative_to(results_dir.parent)):<50}  {size:>8,} B")


def run_backtest(args):
    ds = LocalDataSource(args.data)
    di = DataInterface(ds)

    all_dates = di.trading_dates
    start_date = args.start or all_dates[0]
    end_date = args.end or all_dates[-1]

    if args.start or args.end:
        di = _DateRangeFilteredInterface(di, start_date, end_date)

    n_dates = len(di.trading_dates)

    cfg = Config()
    cfg = apply_overrides(cfg, args)

    results_dir = args.results
    if results_dir is None:
        results_dir = datetime.now().strftime("results/%Y-%m-%d_%H-%M-%S")

    engine = BacktestEngine(cfg, di, results_dir=results_dir)

    t0 = time.time()

    if args.verbose:
        print(f"Running backtest: {n_dates} trading days")
        print(f"  Data:     {args.data}")
        print(f"  Dates:    {di.trading_dates[0]} → {di.trading_dates[-1]}")
        print(f"  Capital:  ¥{cfg.initial_capital:,.0f}")
        print(f"  Open @:   IV < {cfg.open_threshold:.0%}")
        print(f"  Close @:  IV > {cfg.close_threshold:.0%}")
        print()

    engine.run()

    elapsed = time.time() - t0
    print_summary(engine.results, elapsed, Path(results_dir))

    return engine.results


class _DateRangeFilteredInterface:
    def __init__(self, inner: DataInterface, start: str, end: str):
        self._inner = inner
        self._dates = [d for d in inner.trading_dates if start <= d <= end]

    @property
    def trading_dates(self) -> list[str]:
        return self._dates

    @property
    def date_range(self) -> tuple[str, str]:
        return self._dates[0], self._dates[-1]

    def get_underlying_price(self, date: str) -> float:
        return self._inner.get_underlying_price(date)

    def get_options(self, date: str):
        return self._inner.get_options(date)

    def get_atm_options(self, date, **kwargs):
        return self._inner.get_atm_options(date, **kwargs)


def main():
    args = parse_args()

    if args.list_params:
        print_params(Config())
        return

    try:
        run_backtest(args)
    except FileNotFoundError as e:
        print(f"ERROR: Data file not found — {e}", file=sys.stderr)
        print("Hint: Use --data to specify your data directory.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
