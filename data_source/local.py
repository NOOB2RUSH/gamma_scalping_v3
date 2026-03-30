from pathlib import Path
from typing import Optional
import pandas as pd
from .base import DataSourceBase


class LocalDataSource(DataSourceBase):
    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.etf_dir = self.data_dir / "etf"
        self.options_dir = self.data_dir / "options"

    def _get_files(self, directory: Path, pattern: str) -> list[Path]:
        if not directory.exists():
            return []
        return sorted(directory.glob(pattern))

    def get_etf_price(self, trade_date: str) -> pd.DataFrame:
        filename = f"510050.XSHG_{trade_date}_price.parquet"
        filepath = self.etf_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"ETF data not found: {filepath}")
        return pd.read_parquet(filepath)

    def get_options_chain(self, trade_date: str) -> pd.DataFrame:
        filename = f"510050.XSHG_{trade_date}_chain.parquet"
        filepath = self.options_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Options chain not found: {filepath}")
        return pd.read_parquet(filepath)

    def get_date_range(self) -> tuple[str, str]:
        etf_files = self._get_files(self.etf_dir, "510050.XSHG_*_price.parquet")
        if not etf_files:
            raise FileNotFoundError("No ETF price files found")

        dates = []
        for f in etf_files:
            date_str = f.stem.split("_")[1]
            dates.append(date_str)

        return (min(dates), max(dates))

    def get_trading_dates(self) -> list[str]:
        etf_files = self._get_files(self.etf_dir, "510050.XSHG_*_price.parquet")
        dates = [f.stem.split("_")[1] for f in etf_files]
        return sorted(dates)

    def get_iv_history(self, trade_date: str, tenor_days: int) -> pd.Series:
        raise NotImplementedError(
            "get_iv_history should be implemented by VolCone, not LocalDataSource"
        )
