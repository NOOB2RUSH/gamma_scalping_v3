import pandas as pd


class PerformanceAnalyzer:
    def __init__(self):
        self.trades: list[dict] = []
        self.equity_curve: list[dict] = []

    def compute_summary(self, greeks_by_date: dict[str, dict] | None = None) -> dict:
        closed = [t for t in self.trades if t.get("is_closed")]
        wins = [t for t in closed if t.get("net_pnl", 0) > 0]
        losses = [t for t in closed if t.get("net_pnl", 0) < 0]
        total_premium_net = sum(
            t.get("close_proceeds", 0) - t.get("open_cost", 0) for t in closed
        )
        total_hedge_pnl = sum(t.get("hedge_pnl", 0.0) for t in closed)
        total_realized = sum(t.get("net_pnl", 0) for t in closed)
        win_rate = len(wins) / len(closed) if closed else 0.0
        avg_win = sum(t["net_pnl"] for t in wins) / len(wins) if wins else 0.0
        avg_loss = sum(t["net_pnl"] for t in losses) / len(losses) if losses else 0.0

        # 计算年化利润
        trading_days = 0
        annualized_profit = 0.0
        if self.equity_curve and len(self.equity_curve) >= 2:
            start_date = pd.to_datetime(self.equity_curve[0]["date"])
            end_date = pd.to_datetime(self.equity_curve[-1]["date"])
            trading_days = (end_date - start_date).days
            if trading_days > 0:
                annualized_profit = total_realized / trading_days * 365

        # Greeks P&L 汇总
        greeks_total_delta = 0.0
        greeks_total_gamma = 0.0
        greeks_total_theta = 0.0
        greeks_total_vega = 0.0
        greeks_total_pnl = 0.0
        if greeks_by_date:
            for greeks in greeks_by_date.values():
                greeks_total_delta += greeks.get("delta_pnl", 0.0)
                greeks_total_gamma += greeks.get("gamma_pnl", 0.0)
                greeks_total_theta += greeks.get("theta_pnl", 0.0)
                greeks_total_vega += greeks.get("vega_pnl", 0.0)
            greeks_total_pnl = (
                greeks_total_delta
                + greeks_total_gamma
                + greeks_total_theta
                + greeks_total_vega
            )

        # Greeks P&L 与实际 P&L 对比
        greeks_vs_pnl_diff = 0.0
        greeks_vs_pnl_pct = 0.0
        if total_realized != 0:
            greeks_vs_pnl_diff = greeks_total_pnl - total_realized
            greeks_vs_pnl_pct = abs(greeks_vs_pnl_diff) / abs(total_realized) * 100

        return {
            "total_trades": len(closed),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "total_premium_net": total_premium_net,
            "total_hedge_pnl": total_hedge_pnl,
            "total_realized_pnl": total_realized,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "trading_days": trading_days,
            "annualized_profit": annualized_profit,
            # Greeks P&L 分解
            "greeks_delta_pnl": greeks_total_delta,
            "greeks_gamma_pnl": greeks_total_gamma,
            "greeks_theta_pnl": greeks_total_theta,
            "greeks_vega_pnl": greeks_total_vega,
            "greeks_total_pnl": greeks_total_pnl,
            # Greeks P&L vs 实际 P&L
            "greeks_vs_pnl_diff": greeks_vs_pnl_diff,
            "greeks_vs_pnl_pct": greeks_vs_pnl_pct,
        }

    def compute_equity_curve_stats(self) -> dict:
        if not self.equity_curve:
            return {}
        start = self.equity_curve[0]["equity"]
        end = self.equity_curve[-1]["equity"]
        total_return_pct = (end - start) / start if start != 0 else 0.0
        return {
            "start_equity": start,
            "end_equity": end,
            "total_return_pct": total_return_pct,
        }
