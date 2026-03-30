#!/usr/bin/env python3
"""
Browse and display backtest results.

Usage:
    python3 scripts/show_results.py                                    # interactive select
    python3 scripts/show_results.py results/2026-03-29_12-00-00/      # direct path
    python3 scripts/show_results.py results/latest/                   # latest run
    python3 scripts/show_results.py <path> --equity                    # equity curve
    python3 scripts/show_results.py <path> --trades                   # trade list
    python3 scripts/show_results.py <path> --performance              # performance metrics
    python3 scripts/show_results.py <path> --all                       # show all
"""

import argparse
import sys
from pathlib import Path

import pandas as pd


def parse_args():
    parser = argparse.ArgumentParser(description="Browse backtest results")
    parser.add_argument("results_dir", nargs="?", default=None)
    parser.add_argument("--equity", action="store_true", help="Show equity curve")
    parser.add_argument("--trades", action="store_true", help="Show trade list")
    parser.add_argument(
        "--performance", action="store_true", help="Show performance metrics"
    )
    parser.add_argument("--config", action="store_true", help="Show config")
    parser.add_argument("--all", "-a", action="store_true", help="Show all")
    return parser.parse_args()


def find_results_dir(arg: str | None) -> Path:
    if arg is None:
        results_dir = Path("results")
    elif Path(arg).exists():
        results_dir = Path(arg)
    else:
        raise FileNotFoundError(f"Results directory not found: {arg}")

    if not results_dir.is_dir():
        raise NotADirectoryError(f"Not a directory: {results_dir}")

    subdirs = sorted([d for d in results_dir.iterdir() if d.is_dir()])
    if not subdirs:
        raise FileNotFoundError(f"No results found in {results_dir}")
    return subdirs[-1]


def load_results(results_dir: Path) -> dict:
    files = {
        "summary": results_dir / "summary.csv",
        "equity_curve": results_dir / "equity_curve.csv",
        "performance": results_dir / "performance.csv",
        "config": results_dir / "config.yaml",
    }
    trades_dir = results_dir / "trades"
    trades = list(trades_dir.glob("trade_*.csv")) if trades_dir.exists() else []

    data = {}
    if files["summary"].exists():
        data["summary"] = pd.read_csv(files["summary"])
    if files["equity_curve"].exists():
        data["equity_curve"] = pd.read_csv(files["equity_curve"], parse_dates=["date"])
    if files["performance"].exists():
        data["performance"] = pd.read_csv(files["performance"])
    if files["config"].exists():
        import yaml

        with open(files["config"]) as f:
            data["config"] = yaml.load(f, Loader=yaml.UnsafeLoader)
    if trades:
        data["trades"] = [pd.read_csv(t) for t in sorted(trades)]

    return data


def print_equity_curve(df: pd.DataFrame):
    print("\n=== Equity Curve ===")
    print(f"  Start: {df['date'].iloc[0]}  End: {df['date'].iloc[-1]}")
    print(f"  Initial: ¥{df['equity'].iloc[0]:>12,.0f}")
    print(f"  Final:   ¥{df['equity'].iloc[-1]:>12,.0f}")
    print(f"  Peak:    ¥{df['equity'].max():>12,.0f}")
    print(f"  Trough:  ¥{df['equity'].min():>12,.0f}")
    print()
    print("  Date           Equity       Daily PnL    Cum PnL")
    print("  " + "-" * 55)
    n = len(df)
    if n > 30:
        idx = list(range(0, n, n // 10))[:10]
        idx.append(n - 1)
        idx = sorted(set(idx))
    else:
        idx = range(n)
    for i in idx:
        row = df.iloc[i]
        print(
            f"  {row['date']}  {row['equity']:>12,.0f}  {row['daily_pnl']:>+10,.0f}  {row['cumulative_pnl']:>+10,.0f}"
        )


def print_trades(trades: list[pd.DataFrame]):
    print("\n=== Trades ===")
    if not trades:
        print("  (no closed trades)")
        return
    all_trades = pd.concat(trades, ignore_index=True)
    all_trades = all_trades.sort_values("open_date")
    print(
        f"  {'TradeID':<10} {'Open':<12} {'Close':<12} {'Strike':>8}  {'PnL':>10}  {'Return':>8}"
    )
    print("  " + "-" * 65)
    for _, t in all_trades.iterrows():
        oid = t.get("order_id", t.get("trade_id", "?"))
        pnl = t.get("close_proceeds", 0) - t.get("open_cost", 0)
        ret = pnl / t.get("open_cost", 1) * 100 if t.get("open_cost", 0) else 0
        print(
            f"  {str(oid):<10} {t.get('open_date', '?'):<12} {t.get('close_date', '?'):<12}"
            f"  {t.get('strike_price', 0):>8.2f}  {pnl:>+10,.0f}  {ret:>7.1f}%"
        )
    total = (all_trades["close_proceeds"] - all_trades["open_cost"]).sum()
    print(f"  {'TOTAL':<10} {' ' * 24}  {total:>+10,.0f}")


def print_performance(equity_df: pd.DataFrame | None, summary_df: pd.DataFrame | None):
    print("\n=== Performance ===")
    if equity_df is not None and len(equity_df) > 1:
        initial = equity_df["equity"].iloc[0]
        final = equity_df["equity"].iloc[-1]
        total_ret = (final - initial) / initial * 100
        peak = equity_df["equity"].cummax()
        dd = (equity_df["equity"] - peak) / peak * 100
        max_dd = dd.min()
        equity_df = equity_df.copy()
        equity_df["daily_return"] = equity_df["daily_pnl"] / equity_df["equity"].shift(
            1
        )
        sharpe = (
            equity_df["daily_return"].mean()
            / equity_df["daily_return"].std()
            * (252**0.5)
            if equity_df["daily_return"].std() > 0
            else 0
        )
        print(f"  Total Return:     {total_ret:>8.2f}%")
        print(f"  Sharpe Ratio:     {sharpe:>8.2f}")
        print(f"  Max Drawdown:     {max_dd:>8.2f}%")
        print(f"  Final Equity:    ¥{final:>10,.0f}")
    if summary_df is not None and len(summary_df) > 0:
        row = summary_df.iloc[0]
        for col in summary_df.columns:
            val = row[col]
            if isinstance(val, float):
                print(f"  {col:<20} {val:>12.4f}")


def print_config(config: dict):
    print("\n=== Config ===")
    for k, v in sorted(config.items()):
        if isinstance(v, float):
            if abs(v) < 1:
                print(f"  {k:<25} {v:.6f}")
            else:
                print(f"  {k:<25} {v:>12,.2f}")
        else:
            print(f"  {k:<25} {v}")


def main():
    args = parse_args()
    try:
        results_dir = find_results_dir(args.results_dir)
        print(f"Reading: {results_dir}")
        data = load_results(results_dir)
        if not data:
            print("No result files found.", file=sys.stderr)
            sys.exit(1)

        show_all = args.all or not any(
            [args.equity, args.trades, args.performance, args.config]
        )

        if show_all or args.equity:
            if "equity_curve" in data:
                print_equity_curve(data["equity_curve"])
            else:
                print("  (no equity curve data)")

        if show_all or args.performance:
            if "equity_curve" in data or "summary" in data:
                print_performance(data.get("equity_curve"), data.get("summary"))
            else:
                print("  (no performance data)")

        if show_all or args.trades:
            if "trades" in data and data["trades"]:
                print_trades(data["trades"])
            else:
                print("  (no trade data)")

        if show_all or args.config:
            if "config" in data:
                print_config(data["config"])
            else:
                print("  (no config data)")

    except (FileNotFoundError, NotADirectoryError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
