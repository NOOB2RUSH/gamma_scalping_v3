import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from data_source.interface import DataInterface


@pytest.fixture
def mock_ds():
    ds = MagicMock()
    ds.get_trading_dates.return_value = ["2024-12-16", "2024-12-17"]
    ds.get_date_range.return_value = ("2024-12-16", "2024-12-17")
    return ds


class TestDataInterfaceInit:
    def test_init_accepts_data_source(self, mock_ds):
        di = DataInterface(mock_ds)
        assert di._ds is mock_ds


class TestTradingDates:
    def test_trading_dates_delegates_to_ds(self, mock_ds):
        di = DataInterface(mock_ds)
        assert di.trading_dates == ["2024-12-16", "2024-12-17"]
        mock_ds.get_trading_dates.assert_called_once()


class TestDateRange:
    def test_date_range_delegates_to_ds(self, mock_ds):
        di = DataInterface(mock_ds)
        assert di.date_range == ("2024-12-16", "2024-12-17")
        mock_ds.get_date_range.assert_called_once()


class TestGetEtfClose:
    def test_get_etf_close_returns_float(self, mock_ds):
        mock_df = pd.DataFrame({"close": [2.55]})
        mock_ds.get_etf_price.return_value = mock_df
        di = DataInterface(mock_ds)
        result = di.get_etf_close("2024-12-16")
        assert result == 2.55
        assert isinstance(result, float)


class TestGetUnderlyingPrice:
    def test_get_underlying_price_same_as_etf_close(self, mock_ds):
        mock_df = pd.DataFrame({"close": [2.55]})
        mock_ds.get_etf_price.return_value = mock_df
        di = DataInterface(mock_ds)
        assert di.get_underlying_price("2024-12-16") == 2.55


class TestGetOptions:
    def test_get_options_delegates(self, mock_ds):
        mock_df = pd.DataFrame({"strike_price": [2.5]})
        mock_ds.get_options_chain.return_value = mock_df
        di = DataInterface(mock_ds)
        result = di.get_options("2024-12-16")
        assert "strike_price" in result.columns
        mock_ds.get_options_chain.assert_called_once_with("2024-12-16")


class TestGetAtmOptions:
    def test_returns_none_when_no_options(self, mock_ds):
        mock_ds.get_etf_price.return_value = pd.DataFrame({"close": [2.55]})
        mock_ds.get_options_chain.return_value = pd.DataFrame(
            {
                "strike_price": [],
                "maturity_date": [],
                "option_type": [],
                "close": [],
                "volume": [],
            }
        )
        di = DataInterface(mock_ds)
        call, put = di.get_atm_options("2024-12-16")
        assert call is None
        assert put is None

    def test_returns_atm_call_and_put(self, mock_ds):
        mock_ds.get_etf_price.return_value = pd.DataFrame({"close": [2.55]})
        mock_ds.get_options_chain.return_value = pd.DataFrame(
            {
                "order_book_id": ["C1", "C2", "P1", "P2"],
                "strike_price": [2.50, 2.55, 2.50, 2.55],
                "maturity_date": ["2025-01-22"] * 4,
                "option_type": ["C", "C", "P", "P"],
                "bid": [0.1, 0.08, 0.09, 0.07],
                "ask": [0.11, 0.09, 0.10, 0.08],
                "volume": [5000] * 4,
                "open_interest": [1000] * 4,
                "contract_multiplier": [10000] * 4,
                "close": [0.105, 0.085, 0.095, 0.075],
            }
        )
        di = DataInterface(mock_ds)
        call, put = di.get_atm_options("2024-12-16")
        assert call is not None
        assert put is not None
        assert call["option_type"] == "C"
        assert put["option_type"] == "P"
        assert call["strike_price"] == 2.55
        assert put["strike_price"] == 2.55

    def test_respects_moneyness_range(self, mock_ds):
        mock_ds.get_etf_price.return_value = pd.DataFrame({"close": [2.55]})
        mock_ds.get_options_chain.return_value = pd.DataFrame(
            {
                "order_book_id": ["C1", "C2"],
                "strike_price": [2.40, 2.70],
                "maturity_date": ["2025-01-22"] * 2,
                "option_type": ["C", "C"],
                "bid": [0.15, 0.12],
                "ask": [0.16, 0.13],
                "volume": [5000] * 2,
                "open_interest": [1000] * 2,
                "contract_multiplier": [10000] * 2,
                "close": [0.155, 0.125],
            }
        )
        di = DataInterface(mock_ds)
        call, put = di.get_atm_options("2024-12-16", moneyness_range=(0.95, 1.05))
        assert call is None
        assert put is None

    def test_respects_min_volume(self, mock_ds):
        mock_ds.get_etf_price.return_value = pd.DataFrame({"close": [2.55]})
        mock_ds.get_options_chain.return_value = pd.DataFrame(
            {
                "order_book_id": ["C1", "P1"],
                "strike_price": [2.55, 2.55],
                "maturity_date": ["2025-01-22"] * 2,
                "option_type": ["C", "P"],
                "bid": [0.1, 0.09],
                "ask": [0.11, 0.10],
                "volume": [100, 100],
                "open_interest": [1000] * 2,
                "contract_multiplier": [10000] * 2,
                "close": [0.105, 0.095],
            }
        )
        di = DataInterface(mock_ds)
        call, put = di.get_atm_options("2024-12-16", min_volume=2000)
        assert call is None
        assert put is None

    def test_respects_min_dte(self, mock_ds):
        mock_ds.get_etf_price.return_value = pd.DataFrame({"close": [2.55]})
        mock_ds.get_options_chain.return_value = pd.DataFrame(
            {
                "order_book_id": ["C1", "P1"],
                "strike_price": [2.55, 2.55],
                "maturity_date": ["2024-12-17", "2024-12-17"],
                "option_type": ["C", "P"],
                "bid": [0.1, 0.09],
                "ask": [0.11, 0.10],
                "volume": [5000] * 2,
                "open_interest": [1000] * 2,
                "contract_multiplier": [10000] * 2,
                "close": [0.105, 0.095],
            }
        )
        di = DataInterface(mock_ds)
        call, put = di.get_atm_options("2024-12-16", min_dte=7)
        assert call is None
        assert put is None
