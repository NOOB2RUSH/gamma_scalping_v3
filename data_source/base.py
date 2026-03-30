from abc import ABC, abstractmethod
from datetime import date
import pandas as pd


class DataSourceBase(ABC):
    """数据源抽象基类"""

    @abstractmethod
    def get_etf_price(self, trade_date: str) -> pd.DataFrame:
        """
        获取指定日期的 ETF 价格数据

        Args:
            trade_date: 交易日期 (YYYY-MM-DD)

        Returns:
            DataFrame with columns: date, open, close, high, low, volume, money
        """
        pass

    @abstractmethod
    def get_options_chain(self, trade_date: str) -> pd.DataFrame:
        """
        获取指定日期的期权链数据

        Args:
            trade_date: 交易日期 (YYYY-MM-DD)

        Returns:
            DataFrame with columns: order_book_id, strike_price, maturity_date,
            option_type, bid, ask, volume, open_interest, contract_multiplier, close
        """
        pass

    @abstractmethod
    def get_date_range(self) -> tuple[str, str]:
        """
        获取数据日期范围

        Returns:
            (start_date, end_date) tuple of strings (YYYY-MM-DD)
        """
        pass

    @abstractmethod
    def get_trading_dates(self) -> list[str]:
        """
        获取所有交易日期列表

        Returns:
            List of trade date strings (YYYY-MM-DD), sorted ascending
        """
        pass

    @abstractmethod
    def get_iv_history(self, trade_date: str, tenor_days: int) -> pd.Series:
        """
        获取指定日期和期限的历史 IV 数据（用于波动率锥）

        Args:
            trade_date: 交易日期 (YYYY-MM-DD)
            tenor_days: 目标期限天数 (7/14/30/60/90)

        Returns:
            Series of historical IV values
        """
        pass
