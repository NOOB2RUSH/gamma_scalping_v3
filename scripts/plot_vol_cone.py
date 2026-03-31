#!/usr/bin/env python3
"""
ATM Options Volatility Cone

Usage:
    # Full history cone (default mode)
    python3 scripts/plot_vol_cone.py

    # Cone with ATM options markers for a specific date
    python3 scripts/plot_vol_cone.py --date 2025-06-15

    # All options
    python3 scripts/plot_vol_cone.py --date 2025-06-15 --lookback 120
    python3 scripts/plot_vol_cone.py --date 2025-06-15 --output ./results/vol_cone_2025-06-15.png
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config
from core.greeks import implied_volatility
from core.vol_cone import (
    build_vol_cone,
    current_iv_percentile,
    dte_to_tenor_bucket,
    PERCENTILES,
    TENOR_BUCKETS,
)
from data_source.local import LocalDataSource
from data_source.interface import DataInterface


def parse_args():
    parser = argparse.ArgumentParser(
        description="ATM Options Volatility Cone",
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
        "--date",
        default=None,
        help="Trade date for ATM markers (YYYY-MM-DD). If provided, plots ATM options as markers on the cone.",
    )
    parser.add_argument(
        "--start",
        default="2024-12-16",
        help="Start date for IV history YYYY-MM-DD (default: 2024-12-16)",
    )
    parser.add_argument(
        "--end",
        default="2025-12-16",
        help="End date for IV history YYYY-MM-DD (default: 2025-12-16)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output image path",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=120,
        help="Lookback days (default: 120)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print progress",
    )
    return parser.parse_args()


def calculate_dte(trade_date: str, maturity_date: str) -> float:
    trade_dt = datetime.strptime(trade_date, "%Y-%m-%d")
    maturity_dt = datetime.strptime(maturity_date, "%Y-%m-%d")
    dte_days = (maturity_dt - trade_dt).days
    return max(dte_days, 0) / 365.0


def get_atm_iv(
    di: DataInterface,
    trade_date: str,
    cfg: Config,
) -> list[dict]:
    return get_all_near_atm_options(di, trade_date, cfg)


def get_all_near_atm_options(
    di: DataInterface,
    trade_date: str,
    cfg: Config,
) -> list[dict]:
    try:
        chain = di.get_options_chain(trade_date)
    except FileNotFoundError:
        return []

    if chain.empty:
        return []

    spot = di.get_spot_price(trade_date)
    r = cfg.risk_free_rate
    lo, hi = cfg.moneyness_range

    pairs = {}

    for _, row in chain.iterrows():
        option_type = str(row.get("option_type", ""))
        if option_type not in ("C", "P"):
            continue

        try:
            strike = float(row["strike_price"])
            bid = float(row["bid"])
            ask = float(row["ask"])
            maturity = str(row["maturity_date"])
            volume = int(row.get("volume", 0))
            order_book_id = str(row.get("order_book_id", ""))

            moneyness = strike / spot
            if not (lo <= moneyness <= hi):
                continue
            if ask <= 0 or bid <= 0 or ask == bid:
                continue
            if volume < cfg.min_volume:
                continue

            market_price = (bid + ask) / 2.0
            if market_price < cfg.min_option_price:
                continue

            t = calculate_dte(trade_date, maturity)
            if t <= 0:
                continue

            iv = implied_volatility(market_price, spot, strike, t, r, option_type)
            if iv <= 0:
                continue

            dte_days = int(t * 365)
            tenor = dte_to_tenor_bucket(dte_days)
            if tenor is None:
                continue

            key = (strike, maturity)
            if key not in pairs:
                pairs[key] = {
                    "call": None,
                    "put": None,
                    "strike": strike,
                    "maturity": maturity,
                    "dte_days": dte_days,
                    "tenor": tenor,
                    "spot": spot,
                }

            record = {
                "date": trade_date,
                "dte": dte_days,
                "tenor": tenor,
                "iv": iv,
                "option_type": option_type,
                "strike": strike,
                "spot": spot,
                "market_price": market_price,
                "order_book_id": order_book_id,
                "moneyness": moneyness,
            }

            if option_type == "C":
                pairs[key]["call"] = record
            else:
                pairs[key]["put"] = record
        except (KeyError, ValueError, TypeError):
            continue

    results = []
    for key, pair_data in pairs.items():
        call_rec = pair_data["call"]
        put_rec = pair_data["put"]

        if call_rec is None or put_rec is None:
            continue

        call_iv = call_rec["iv"]
        put_iv = put_rec["iv"]

        if abs(call_iv - put_iv) > cfg.max_call_put_iv_diff:
            continue

        avg_iv = (call_iv + put_iv) / 2.0
        call_rec["iv"] = avg_iv
        put_rec["iv"] = avg_iv
        results.append(call_rec)
        results.append(put_rec)

    return results


def build_iv_history(
    di: DataInterface,
    trading_dates: list[str],
    cfg: Config,
    verbose: bool = False,
) -> pd.DataFrame:
    all_ivs = []
    total = len(trading_dates)
    for i, trade_date in enumerate(trading_dates):
        if verbose and (i % 20 == 0 or i == total - 1):
            print(f"  [{i + 1}/{total}] {trade_date}")

        try:
            iv_records = get_atm_iv(di, trade_date, cfg)
            all_ivs.extend(iv_records)
        except FileNotFoundError:
            continue
        except Exception as e:
            if verbose:
                print(f"    Warning: {e}")
            continue

    if not all_ivs:
        raise ValueError("No IV data found")

    return pd.DataFrame(all_ivs)


def calculate_atm_markers(
    di: DataInterface,
    trade_date: str,
    iv_history: pd.DataFrame,
    cfg: Config,
    lookback_days: int,
) -> list[dict]:
    """
    For each near-ATM option on trade_date, compute its IV percentile
    within the historical distribution for its tenor bucket.
    """
    markers = []
    atm_options = get_all_near_atm_options(di, trade_date, cfg)

    for opt in atm_options:
        tenor = opt["tenor"]
        pct = current_iv_percentile(
            current_iv=opt["iv"],
            trade_date=trade_date,
            iv_history=iv_history,
            target_tenor=tenor,
            lookback_days=lookback_days,
        )
        if pct is None:
            continue
        opt["percentile"] = pct
        markers.append(opt)

    return markers


def plot_vol_cone(
    vol_cone: dict[int, dict[int, float]],
    output_path: Path,
    trade_date: str,
    lookback: int,
    atm_markers: Optional[list[dict]] = None,
) -> None:
    tenors = sorted(vol_cone.keys())
    if not tenors:
        raise ValueError("Vol cone data is empty")

    all_percentiles = [100, 85, 70, 50, 30, 15, 0]
    fig, ax = plt.subplots(figsize=(12, 7))

    for i in range(len(all_percentiles) - 1):
        p_upper = all_percentiles[i]
        p_lower = all_percentiles[i + 1]
        upper_ivs = [vol_cone[t].get(p_upper, float("nan")) for t in tenors]
        lower_ivs = [vol_cone[t].get(p_lower, float("nan")) for t in tenors]
        ax.fill_between(
            tenors,
            upper_ivs,
            lower_ivs,
            alpha=0.12 + i * 0.04,
            color="steelblue",
            step="mid",
        )

    ax.plot(
        tenors,
        [vol_cone[t].get(50, float("nan")) for t in tenors],
        color="steelblue",
        linewidth=2.5,
        marker="o",
        markersize=6,
        label="Median (50%)",
        zorder=5,
    )

    ax.plot(
        tenors,
        [vol_cone[t].get(100, float("nan")) for t in tenors],
        color="steelblue",
        linewidth=1.5,
        linestyle="--",
        marker="^",
        markersize=5,
        label="Upper (100%)",
        alpha=0.7,
    )
    ax.plot(
        tenors,
        [vol_cone[t].get(0, float("nan")) for t in tenors],
        color="steelblue",
        linewidth=1.5,
        linestyle="--",
        marker="v",
        markersize=5,
        label="Lower (0%)",
        alpha=0.7,
    )

    if atm_markers:
        for marker in atm_markers:
            tenor = marker["tenor"]
            pct = marker["percentile"]
            iv = marker["iv"]
            opt_type = marker["option_type"]
            ob_id = marker["order_book_id"]
            strike = marker["strike"]

            # Find nearest percentile key in vol_cone
            pct_key = round(pct * 100)
            vol_keys = sorted(vol_cone[tenor].keys())
            nearest_key = min(vol_keys, key=lambda x: abs(x - pct_key))
            pct_iv = vol_cone[tenor][nearest_key]

            marker_color = "darkgreen" if opt_type == "C" else "darkred"
            marker_label = f"Call" if opt_type == "C" else f"Put"

            ax.scatter(
                [tenor],
                [pct_iv],
                color=marker_color,
                s=80,
                zorder=10,
                marker="D",
                edgecolors="black",
                linewidths=0.5,
            )

            label = f"{ob_id}\n{pct:.0f}%"
            ax.annotate(
                label,
                xy=(tenor, pct_iv),
                xytext=(8, 8),
                textcoords="offset points",
                fontsize=7,
                color=marker_color,
                fontweight="bold",
                bbox=dict(
                    boxstyle="round,pad=0.2",
                    facecolor="white",
                    alpha=0.7,
                    edgecolor=marker_color,
                ),
                arrowprops=dict(arrowstyle="->", color=marker_color, lw=0.8),
            )

    title_suffix = (
        f" | ATM markers: {trade_date}" if atm_markers else f" | as of {trade_date}"
    )
    ax.set_title(
        f"ATM Options Volatility Cone{title_suffix}\n{lookback}-day lookback",
        fontsize=13,
        fontweight="bold",
    )
    ax.set_xlabel("Days to Expiration (DTE)", fontsize=11)
    ax.set_ylabel("Implied Volatility (IV)", fontsize=11)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:.0%}"))
    ax.set_xticks(tenors)
    ax.set_xlim(left=0, right=max(tenors) + 12)
    ax.set_ylim(bottom=0)
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3, linestyle="-.")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"\nChart saved: {output_path}")


def main():
    args = parse_args()

    ds = LocalDataSource(args.data)
    di = DataInterface(ds)
    cfg = Config()
    cfg.risk_free_rate = 0.025

    all_dates = di.trading_dates

    if args.date:
        target_date = args.date
        if target_date not in all_dates:
            print(f"ERROR: Date {target_date} not in trading dates", file=sys.stderr)
            print(f"Available: {all_dates[0]} to {all_dates[-1]}", file=sys.stderr)
            sys.exit(1)
        trading_dates = [d for d in all_dates if d <= target_date]
        if len(trading_dates) < 65:
            print(
                f"ERROR: Need at least 65 trading days before {target_date}",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        target_date = all_dates[-1]
        trading_dates = [d for d in all_dates if args.start <= d <= args.end]
        if not trading_dates:
            print(
                f"ERROR: No trading days in {args.start} to {args.end}", file=sys.stderr
            )
            sys.exit(1)

    print(f"Volatility Cone Analysis")
    print(f"  Data:         {args.data}")
    print(f"  Target date:  {target_date}")
    print(f"  History end:  {trading_dates[-1]}")
    print(f"  Trading days: {len(trading_dates)}")
    print(f"  Lookback:     {args.lookback}")
    print()

    print("Computing daily ATM IV...")
    t0 = time.time()
    iv_history = build_iv_history(di, trading_dates, cfg, verbose=args.verbose)
    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s, {len(iv_history)} IV records")

    print("\nTenor bucket IV stats:")
    for tenor_target, dte_min, dte_max in TENOR_BUCKETS:
        bucket = iv_history[iv_history["dte"].between(dte_min, dte_max)]
        if not bucket.empty:
            print(
                f"  DTE {dte_min:3d}-{dte_max:3d} (bucket {tenor_target:3d}d): "
                f"mean {bucket['iv'].mean():.2%}, median {bucket['iv'].median():.2%}, n={len(bucket)}"
            )

    print(f"\nBuilding vol cone as of {target_date}...")
    vol_cone = build_vol_cone(
        trade_date=target_date,
        iv_history=iv_history,
        lookback_days=args.lookback,
    )
    if not vol_cone:
        print(
            "ERROR: Insufficient data for vol cone (need 60+ lookback days)",
            file=sys.stderr,
        )
        sys.exit(1)

    atm_markers = None
    if args.date:
        print(f"\nComputing ATM option markers for {args.date}...")
        atm_markers = calculate_atm_markers(
            di, args.date, iv_history, cfg, args.lookback
        )
        print(f"Found {len(atm_markers)} near-ATM options with valid percentiles")
        for m in atm_markers:
            print(
                f"  {m['order_book_id']:20s} {m['option_type']} "
                f"strike={m['strike']:.2f} DTE={m['dte']:3d}d "
                f"IV={m['iv']:.2%} → {m['percentile'] * 100:.0f}%"
            )

    if args.output:
        output_path = Path(args.output)
    else:
        visualize_dir = Path("visualize")
        visualize_dir.mkdir(exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_path = visualize_dir / f"vol_cone_{target_date}_{date_str}.png"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    plot_vol_cone(vol_cone, output_path, target_date, args.lookback, atm_markers)

    print("\nVol cone percentiles:")
    print(f"{'DTE bucket':<12}", end="")
    for p in PERCENTILES:
        print(f"{p:>8}%", end="")
    print()
    for tenor in sorted(vol_cone.keys()):
        print(f"{tenor:<12}", end="")
        for p in PERCENTILES:
            iv = vol_cone[tenor].get(p, float("nan"))
            print(f"{iv:>8.2%}", end="")
        print()


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as e:
        print(f"ERROR: Data file not found — {e}", file=sys.stderr)
        print("Hint: use --data to specify data directory", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)
