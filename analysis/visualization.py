import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.figure
import pandas as pd


def plot_equity_curve(
    equity_df: pd.DataFrame,
    output_path: str | None = None,
) -> matplotlib.figure.Figure | None:
    """
    绘制权益曲线

    Args:
        equity_df: DataFrame with columns: date, equity, daily_pnl, cumulative_pnl
        output_path: 如果指定，保存图像到该路径

    Returns:
        matplotlib Figure
    """
    if equity_df.empty:
        return None
    equity_df = equity_df.copy()
    equity_df["date"] = pd.to_datetime(equity_df["date"])
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))

    # 权益曲线
    ax1.plot(equity_df["date"], equity_df["equity"], label="Equity")
    ax1.set_ylabel("Equity (CNY)")
    ax1.set_title("Gamma Scalping Backtest - Equity Curve")
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=10))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha="right")

    # 每日 P&L
    ax2.bar(
        equity_df["date"],
        equity_df["daily_pnl"],
        color=["green" if x > 0 else "red" for x in equity_df["daily_pnl"]],
    )
    ax2.set_ylabel("Daily P&L (CNY)")
    ax2.set_xlabel("Date")
    ax2.set_title("Daily P&L")
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=10))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha="right")

    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches="tight")

    return fig


class Visualizer:
    def __init__(self, results: dict):
        self.results = results

    def plot_equity_curve(self):
        curve = self.results.get("equity_curve", [])
        if not curve:
            return None
        equity_df = pd.DataFrame(curve)
        equity_df["date"] = pd.to_datetime(equity_df["date"])
        return plot_equity_curve(equity_df)

    def plot_pnl_distribution(self):
        trades = self.results.get("trades", [])
        if not trades:
            return None
        pnls = [t.get("net_pnl", 0) for t in trades if t.get("is_closed")]
        fig, ax = plt.subplots()
        ax.hist(pnls, bins=20)
        ax.set_xlabel("P&L")
        ax.set_ylabel("Count")
        ax.set_title("P&L Distribution")
        fig.tight_layout()
        return fig
