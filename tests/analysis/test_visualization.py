import pytest
import pandas as pd
from pathlib import Path
from analysis.visualization import Visualizer, plot_equity_curve


class TestVisualizerInit:
    def test_initializes_with_results(self):
        results = {"trades": [], "equity_curve": []}
        viz = Visualizer(results)
        assert viz.results is results


class TestVisualizerPlots:
    def test_plot_equity_curve_returns_figure(self):
        viz = Visualizer(
            {
                "equity_curve": [
                    {"date": "2024-12-16", "equity": 1_000_000.0, "daily_pnl": 0.0},
                    {
                        "date": "2024-12-17",
                        "equity": 1_010_000.0,
                        "daily_pnl": 10_000.0,
                    },
                ]
            }
        )
        fig = viz.plot_equity_curve()
        assert fig is not None

    def test_plot_returns_none_for_empty_curve(self):
        viz = Visualizer({"equity_curve": []})
        fig = viz.plot_equity_curve()
        assert fig is None

    def test_plot_pnl_distribution_returns_figure(self):
        viz = Visualizer(
            {
                "trades": [
                    {"trade_id": "001", "is_closed": True, "net_pnl": 100.0},
                    {"trade_id": "002", "is_closed": True, "net_pnl": -40.0},
                ]
            }
        )
        fig = viz.plot_pnl_distribution()
        assert fig is not None


class TestPlotEquityCurveFunction:
    def test_plot_equity_curve_returns_figure(self):
        equity_df = pd.DataFrame(
            [
                {
                    "date": "2024-12-16",
                    "equity": 1_000_000.0,
                    "daily_pnl": 0.0,
                    "cumulative_pnl": 0.0,
                },
                {
                    "date": "2024-12-17",
                    "equity": 1_010_000.0,
                    "daily_pnl": 10_000.0,
                    "cumulative_pnl": 10_000.0,
                },
                {
                    "date": "2024-12-18",
                    "equity": 1_005_000.0,
                    "daily_pnl": -5_000.0,
                    "cumulative_pnl": 5_000.0,
                },
                {
                    "date": "2024-12-19",
                    "equity": 1_015_000.0,
                    "daily_pnl": 10_000.0,
                    "cumulative_pnl": 15_000.0,
                },
                {
                    "date": "2024-12-20",
                    "equity": 1_008_350.0,
                    "daily_pnl": -6_650.0,
                    "cumulative_pnl": 8_350.0,
                },
            ]
        )
        fig = plot_equity_curve(equity_df)
        assert fig is not None

    def test_plot_equity_curve_saves_png(self, tmp_path):
        equity_df = pd.DataFrame(
            [
                {
                    "date": "2024-12-16",
                    "equity": 1_000_000.0,
                    "daily_pnl": 0.0,
                    "cumulative_pnl": 0.0,
                },
                {
                    "date": "2024-12-17",
                    "equity": 1_010_000.0,
                    "daily_pnl": 10_000.0,
                    "cumulative_pnl": 10_000.0,
                },
                {
                    "date": "2024-12-18",
                    "equity": 1_005_000.0,
                    "daily_pnl": -5_000.0,
                    "cumulative_pnl": 5_000.0,
                },
            ]
        )
        output_path = tmp_path / "equity_curve.png"
        plot_equity_curve(equity_df, output_path=str(output_path))
        assert output_path.exists()
