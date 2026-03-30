import csv
import os
from pathlib import Path

import pandas as pd
import yaml


class ResultWriter:
    def __init__(self, results_dir: str):
        self.results_dir = Path(results_dir)
        self._ensure_dir(self.results_dir)
        self._ensure_dir(self.results_dir / "trades")
        self._ensure_dir(self.results_dir / "logs")

    def _ensure_dir(self, path: Path):
        path.mkdir(parents=True, exist_ok=True)

    def write_config(self, config_dict: dict):
        config_path = self.results_dir / "config.yaml"
        cleaned = self._sanitize_for_yaml(config_dict)
        with open(config_path, "w") as f:
            yaml.dump(cleaned, f, default_flow_style=False)

    def _sanitize_for_yaml(self, obj):
        if isinstance(obj, tuple):
            return [self._sanitize_for_yaml(x) for x in obj]
        if isinstance(obj, dict):
            return {k: self._sanitize_for_yaml(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._sanitize_for_yaml(x) for x in obj]
        return obj

    def write_trade(self, position_dict: dict):
        trade_id = position_dict.get("trade_id", "000")
        filename = f"trade_{trade_id.zfill(3)}.csv"
        trade_path = self.results_dir / "trades" / filename
        self._write_dict_as_csv(trade_path, position_dict)

    def write_summary(self, summary: dict):
        summary_path = self.results_dir / "summary.csv"
        with open(summary_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self._summary_fields())
            writer.writeheader()
            writer.writerow(summary)

    def _summary_fields(self):
        return [
            "total_trades",
            "winning_trades",
            "losing_trades",
            "total_premium_net",
            "total_hedge_pnl",
            "total_realized_pnl",
            "win_rate",
            "avg_win",
            "avg_loss",
            "trading_days",
            "annualized_profit",
            # Greeks P&L 分解
            "greeks_delta_pnl",
            "greeks_gamma_pnl",
            "greeks_theta_pnl",
            "greeks_vega_pnl",
            "greeks_total_pnl",
            # Greeks P&L vs 实际 P&L
            "greeks_vs_pnl_diff",
            "greeks_vs_pnl_pct",
        ]

    def write_equity_curve(self, equity_curve: list[dict]):
        eq_path = self.results_dir / "equity_curve.csv"
        with open(eq_path, "w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["date", "equity", "daily_pnl", "cumulative_pnl"]
            )
            writer.writeheader()
            writer.writerows(equity_curve)

    def write_performance_csv(self, greeks_by_date):
        perf_path = self.results_dir / "performance.csv"
        rows = []
        if isinstance(greeks_by_date, list):
            for ec in greeks_by_date:
                rows.append(
                    {
                        "date": ec["date"],
                        "delta_pnl": 0.0,
                        "gamma_pnl": 0.0,
                        "theta_pnl": 0.0,
                        "vega_pnl": 0.0,
                    }
                )
        else:
            for date, greeks in sorted(greeks_by_date.items()):
                rows.append(
                    {
                        "date": date,
                        "delta_pnl": greeks.get("delta_pnl", 0.0),
                        "gamma_pnl": greeks.get("gamma_pnl", 0.0),
                        "theta_pnl": greeks.get("theta_pnl", 0.0),
                        "vega_pnl": greeks.get("vega_pnl", 0.0),
                    }
                )
        with open(perf_path, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["date", "delta_pnl", "gamma_pnl", "theta_pnl", "vega_pnl"],
            )
            writer.writeheader()
            writer.writerows(rows)

    def write_underlying_prices(self, underlying_prices: dict[str, float]):
        path = self.results_dir / "underlying_prices.csv"
        rows = [{"date": d, "price": p} for d, p in sorted(underlying_prices.items())]
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["date", "price"])
            writer.writeheader()
            writer.writerows(rows)

    def write_iv_history(self, iv_history_df: pd.DataFrame):
        """Write IV history to CSV with columns: date, dte, iv.
        
        Args:
            iv_history_df: DataFrame with columns [date, dte, iv]
        """
        path = self.results_dir / "iv_history.csv"
        if iv_history_df is None or iv_history_df.empty:
            # Create empty CSV with correct columns
            df = pd.DataFrame(columns=["date", "dte", "iv"])
        elif "date" in iv_history_df.columns and "dte" in iv_history_df.columns and "iv" in iv_history_df.columns:
            df = iv_history_df[["date", "dte", "iv"]].sort_values("date")
        else:
            # Legacy format: dict[str, float] passed directly
            # Convert to DataFrame
            df = pd.DataFrame(list(iv_history_df.items()), columns=["date", "iv"])
            df["dte"] = 30  # Default DTE for legacy format
            df = df[["date", "dte", "iv"]]
        df.to_csv(path, index=False)

    def write_daily_debug_log(self, date: str, debug_lines: list[str]):
        log_path = self.results_dir / "logs" / "daily_debug.log"
        with open(log_path, "a") as f:
            for line in debug_lines:
                f.write(line + "\n")

    def _write_dict_as_csv(self, path: Path, data: dict):
        flat = self._flatten_trade(data)
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(flat.keys()))
            writer.writeheader()
            writer.writerow(flat)

    def _flatten_trade(self, data: dict) -> dict:
        result = {}
        for key, value in data.items():
            if key in ("hedge_records", "daily_greeks"):
                result[key] = str(value)
            else:
                result[key] = value
        return result
