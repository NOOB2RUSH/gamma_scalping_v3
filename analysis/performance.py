import pandas as pd


class PerformanceAnalyzer:
    def __init__(self):
        self.trades: list[dict] = []
        self.equity_curve: list[dict] = []

    def compute_summary(self) -> dict:
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
