import pytest
from abc import ABC
from data_source.base import DataSourceBase


def test_base_is_abc():
    """验证 DataSourceBase 是抽象基类"""
    assert issubclass(DataSourceBase, ABC)


def test_base_abstract_methods():
    """验证抽象方法存在"""
    assert hasattr(DataSourceBase, "get_etf_price")
    assert hasattr(DataSourceBase, "get_options_chain")
    assert hasattr(DataSourceBase, "get_date_range")
    assert hasattr(DataSourceBase, "get_trading_dates")
