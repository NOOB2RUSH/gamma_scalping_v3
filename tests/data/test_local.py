import pytest
import pandas as pd
from pathlib import Path
from unittest.mock import patch, MagicMock
from data_source.local import LocalDataSource


class TestLocalDataSourceInit:
    """测试 LocalDataSource 初始化"""

    def test_init_default_data_dir(self):
        """默认 data_dir 为 ./data"""
        ds = LocalDataSource()
        assert ds.data_dir == Path("./data")

    def test_init_custom_data_dir(self):
        """可指定自定义 data_dir"""
        ds = LocalDataSource("/custom/path")
        assert ds.data_dir == Path("/custom/path")

    def test_data_dir_is_path_object(self):
        """data_dir 会被转换为 Path 对象"""
        ds = LocalDataSource("/foo/bar")
        assert isinstance(ds.data_dir, Path)


class TestGetEtfPrice:
    """测试 get_etf_price"""

    def test_etf_file_not_found_raises(self, tmp_path):
        """文件不存在时抛出 FileNotFoundError"""
        ds = LocalDataSource(str(tmp_path))
        with pytest.raises(FileNotFoundError):
            ds.get_etf_price("2024-12-16")

    def test_etf_file_format(self, tmp_path):
        """验证 ETF 文件读取格式"""
        etf_dir = tmp_path / "etf"
        etf_dir.mkdir()
        etf_file = etf_dir / "510050.XSHG_2024-12-16_price.parquet"

        df = pd.DataFrame(
            {
                "date": ["2024-12-16"],
                "open": [2.5],
                "close": [2.55],
                "high": [2.58],
                "low": [2.48],
                "volume": [1_000_000],
                "money": [2_550_000],
            }
        )
        df.to_parquet(etf_file, index=False)

        ds = LocalDataSource(str(tmp_path))
        result = ds.get_etf_price("2024-12-16")

        assert "close" in result.columns
        assert "open" in result.columns
        assert result.loc[0, "close"] == 2.55

    def test_etf_date_format_variations(self, tmp_path):
        """支持不同日期格式变体"""
        etf_dir = tmp_path / "etf"
        etf_dir.mkdir()
        # 文件名使用 YYYY-MM-DD 格式
        etf_file = etf_dir / "510050.XSHG_2024-12-16_price.parquet"
        df = pd.DataFrame(
            {
                "date": ["2024-12-16"],
                "open": [2.5],
                "close": [2.55],
                "high": [2.58],
                "low": [2.48],
                "volume": [1_000_000],
                "money": [2_550_000],
            }
        )
        df.to_parquet(etf_file, index=False)

        ds = LocalDataSource(str(tmp_path))
        # 传入 2024-12-16 格式应能找到文件
        result = ds.get_etf_price("2024-12-16")
        assert len(result) == 1


class TestGetOptionsChain:
    """测试 get_options_chain"""

    def test_options_file_not_found_raises(self, tmp_path):
        """文件不存在时抛出 FileNotFoundError"""
        ds = LocalDataSource(str(tmp_path))
        with pytest.raises(FileNotFoundError):
            ds.get_options_chain("2024-12-16")

    def test_options_file_columns(self, tmp_path):
        """验证期权链文件读取返回正确列"""
        options_dir = tmp_path / "options"
        options_dir.mkdir()
        options_file = options_dir / "510050.XSHG_2024-12-16_chain.parquet"

        df = pd.DataFrame(
            {
                "order_book_id": ["10000001"],
                "strike_price": [2.5],
                "maturity_date": ["2025-01-22"],
                "option_type": ["C"],
                "bid": [0.1],
                "ask": [0.11],
                "volume": [5000],
                "open_interest": [1000],
                "contract_multiplier": [10000],
                "close": [0.105],
            }
        )
        df.to_parquet(options_file, index=False)

        ds = LocalDataSource(str(tmp_path))
        result = ds.get_options_chain("2024-12-16")

        assert "strike_price" in result.columns
        assert "option_type" in result.columns
        assert "bid" in result.columns
        assert "ask" in result.columns


class TestGetDateRange:
    def test_date_range_no_files_raises(self, tmp_path):
        ds = LocalDataSource(str(tmp_path))
        with pytest.raises(FileNotFoundError):
            ds.get_date_range()


class TestGetTradingDates:
    """测试 get_trading_dates"""

    def test_trading_dates_returns_list(self, tmp_path):
        """get_trading_dates 返回列表"""
        ds = LocalDataSource(str(tmp_path))
        result = ds.get_trading_dates()
        assert isinstance(result, list)

    def test_trading_dates_sorted(self, tmp_path):
        """交易日列表应按日期排序"""
        etf_dir = tmp_path / "etf"
        etf_dir.mkdir()

        # 创建两个 ETF 文件
        for date in ["2024-12-16", "2024-12-17", "2024-12-18"]:
            etf_file = etf_dir / f"510050.XSHG_{date}_price.parquet"
            df = pd.DataFrame(
                {
                    "date": [date],
                    "open": [2.5],
                    "close": [2.55],
                    "high": [2.58],
                    "low": [2.48],
                    "volume": [1_000_000],
                    "money": [2_550_000],
                }
            )
            df.to_parquet(etf_file, index=False)

        ds = LocalDataSource(str(tmp_path))
        dates = ds.get_trading_dates()

        assert dates == sorted(dates)
        assert "2024-12-16" in dates
        assert "2024-12-18" in dates
