#!/usr/bin/env python3
"""
Gamma Scalping — Hyperparameter Tuning with Optuna TPE

Usage:
    python3 scripts/tune_params.py                    # defaults: 150 trials + 50 refinement
    python3 scripts/tune_params.py --trials 100      # custom trial count
    python3 scripts/tune_params.py --workers 4       # parallel workers
    python3 scripts/tune_params.py --start 2025-01-01 --end 2025-12-31  # custom range
"""

# IMPORTS
import argparse, sys, time, os, uuid
from datetime import datetime
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import optuna

optuna.logging.set_verbosity(optuna.logging.WARNING)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config
from data_source.local import LocalDataSource
from data_source.interface import DataInterface
from portfolio.portfolio import Portfolio
from backtest.engine import BacktestEngine


def _run_backtest_for_trial(
    params: dict, data_dir: str, start_date: str, end_date: str
) -> dict:
    """
    Worker function: create fresh engine, run backtest, return Sharpe + stats.
    Runs in a separate process to avoid state leakage between trials.
    Returns: {"sharpe": float, "total_pnl": float, "n_trades": int, "win_rate": float}
    """
    cfg = Config()
    cfg.open_threshold = params["open_threshold"]
    cfg.close_threshold = params["close_threshold"]
    cfg.delta_hedge_threshold = params["delta_hedge_threshold"]
    cfg.max_holding_days = params["max_holding_days"]
    cfg.lookback_days = params["lookback_days"]
    cfg.min_dte = params["min_dte"]

    # Fresh data source + filtered interface (stateless per trial)
    ds = LocalDataSource(data_dir)
    di = DataInterface(ds)
    dates = [d for d in di.trading_dates if start_date <= d <= end_date]

    class _FilteredInterface:
        def __init__(inner, di, dates):
            inner._di = di
            inner._dates = dates

        @property
        def trading_dates(inner):
            return inner._dates

        def get_underlying_price(inner, date):
            return inner._di.get_underlying_price(date)

        def get_options(inner, date):
            return inner._di.get_options(date)

        def get_atm_options(inner, date, **kwargs):
            return inner._di.get_atm_options(date, **kwargs)

    fdi = _FilteredInterface(di, dates)

    # Isolated temp dir per trial to avoid file conflicts
    trial_id = uuid.uuid4().hex[:8]
    results_dir = f"/tmp/gamma_tuning/{trial_id}"

    engine = BacktestEngine(cfg, fdi, results_dir=results_dir)
    engine.run()

    # Compute Sharpe from equity curve
    equity_curve = engine.results.get("equity_curve", [])
    if len(equity_curve) > 1:
        rets = [
            e["daily_pnl"] / equity_curve[i - 1]["equity"]
            for i, e in enumerate(equity_curve)
            if i > 0 and equity_curve[i - 1]["equity"] != 0
        ]
        mean_ret = sum(rets) / len(rets) if rets else 0.0
        std_ret = (
            (sum((r - mean_ret) ** 2 for r in rets) / len(rets)) ** 0.5
            if len(rets) > 1
            else 1e-9
        )
        sharpe = mean_ret / std_ret * (252**0.5) if std_ret > 1e-9 else 0.0
    else:
        sharpe = 0.0

    summary = engine.results.get("summary", {})
    trades = engine.results.get("trades", [])

    return {
        "sharpe": sharpe,
        "total_pnl": summary.get("total_realized_pnl", 0.0),
        "n_trades": summary.get("total_trades", len(trades)),
        "win_rate": summary.get("win_rate", 0.0),
        "hedge_pnl": summary.get("total_hedge_pnl", 0.0),
    }


# ── Optuna objective ───────────────────────────────────────────────────────────
def objective(
    trial: optuna.Trial, data_dir: str, start_date: str, end_date: str
) -> float:
    params = {
        "open_threshold": trial.suggest_float("open_threshold", 0.05, 0.50, step=0.05),
        "close_threshold": trial.suggest_float(
            "close_threshold", 0.50, 0.95, step=0.05
        ),
        "delta_hedge_threshold": trial.suggest_float(
            "delta_hedge_threshold", 0.05, 0.50, step=0.05
        ),
        "max_holding_days": trial.suggest_int("max_holding_days", 1, 15),
        "lookback_days": trial.suggest_int("lookback_days", 20, 120, step=10),
        "min_dte": trial.suggest_int("min_dte", 3, 14),
    }

    result = _run_backtest_for_trial(params, data_dir, start_date, end_date)
    trial.set_user_attr("total_pnl", result["total_pnl"])
    trial.set_user_attr("n_trades", result["n_trades"])
    trial.set_user_attr("win_rate", result["win_rate"])
    trial.set_user_attr("hedge_pnl", result["hedge_pnl"])

    return result["sharpe"]


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Gamma Scalping Hyperparameter Tuning")
    parser.add_argument(
        "--trials", type=int, default=150, help="Phase 1 Optuna trials (default: 150)"
    )
    parser.add_argument(
        "--refinement",
        type=int,
        default=50,
        help="Phase 2 refinement trials (default: 50)",
    )
    parser.add_argument(
        "--workers", "-w", type=int, default=8, help="Parallel workers (default: 8)"
    )
    parser.add_argument("--data", default="./data", help="Data directory")
    parser.add_argument("--start", default="2025-01-01", help="Start date")
    parser.add_argument("--end", default="2025-12-31", help="End date")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    n_dates = len(
        [
            d
            for d in LocalDataSource(args.data).get_trading_dates()
            if args.start <= d <= args.end
        ]
    )
    print(
        f"[Tuning] {n_dates} trading days | {args.trials} trials + {args.refinement} refinement | {args.workers} workers"
    )
    print(f"[Tuning] Date range: {args.start} → {args.end}")
    print(
        f"[Tuning] Expected time: ~{(args.trials / args.workers * 5 / 60):.1f}–{(args.trials / args.workers * 8 / 60):.1f} min"
    )
    print()

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(
            multivariate=True, n_startup_trials=20, seed=args.seed
        ),
    )

    # Optuna manages parallelization internally via n_jobs
    study.optimize(
        lambda trial: objective(trial, args.data, args.start, args.end),
        n_trials=args.trials,
        n_jobs=args.workers,
        show_progress_bar=True,
    )

    print(f"\nPhase 1 complete — Best Sharpe: {study.best_value:.4f}")
    print(f"Best params: {study.best_params}")

    # Phase 2: refinement around best params
    if args.refinement > 0:
        refine_study = optuna.create_study(
            direction="maximize",
            sampler=optuna.samplers.TPESampler(
                multivariate=True,
                n_startup_trials=10,
                seed=args.seed + 1,
            ),
        )
        refine_study.optimize(
            lambda trial: objective(trial, args.data, args.start, args.end),
            n_trials=args.refinement,
            n_jobs=args.workers,
            show_progress_bar=True,
        )
        if refine_study.best_value > study.best_value:
            study = refine_study
            print(
                f"\nPhase 2 (refinement) — Better params found: {refine_study.best_value:.4f}"
            )

    # Save trials to CSV
    output_dir = Path("results/tuning")
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    csv_path = output_dir / f"{ts}_trials.csv"

    import csv

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "number",
                "sharpe",
                "total_pnl",
                "n_trades",
                "win_rate",
                "open_threshold",
                "close_threshold",
                "delta_hedge_threshold",
                "max_holding_days",
                "lookback_days",
                "min_dte",
            ],
        )
        writer.writeheader()
        for trial in study.trials:
            row = {
                "number": trial.number,
                "sharpe": trial.value,
                "total_pnl": trial.user_attrs.get("total_pnl", 0),
                "n_trades": trial.user_attrs.get("n_trades", 0),
                "win_rate": trial.user_attrs.get("win_rate", 0),
            }
            row.update(trial.params)
            writer.writerow(row)

    print(f"\nTrials saved to: {csv_path}")

    # Top-10 summary
    sorted_trials = sorted(
        study.trials,
        key=lambda t: t.value if t.value is not None else -999,
        reverse=True,
    )[:10]
    print(f"\n{'Rank':<5} {'Sharpe':>8} {'PnL':>10} {'Trades':>7} {'Win%':>7}  Params")
    print("-" * 80)
    for i, t in enumerate(sorted_trials, 1):
        attrs = t.user_attrs
        print(
            f"{i:<5} {t.value or 0:>8.4f} {attrs.get('total_pnl', 0):>10,.0f} {attrs.get('n_trades', 0):>7} {attrs.get('win_rate', 0):>7.1%}  {t.params}"
        )

    print(f"\n{'=' * 80}")
    print(f"BEST: Sharpe={study.best_value:.4f}")
    print(f"Params: {study.best_params}")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
