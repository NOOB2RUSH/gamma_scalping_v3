import pytest
from config import Config, default_config


def test_default_config_values():
    cfg = default_config()
    assert cfg.initial_capital == 1_000_000
    assert cfg.lookback_days == 120
    assert cfg.open_threshold == 0.15
    assert cfg.close_threshold == 0.85
    assert cfg.close_dte_threshold == 5
    assert cfg.max_holding_days == 30
    assert cfg.delta_hedge_threshold == 0.05
    assert cfg.moneyness_range == (0.95, 1.05)
    assert cfg.target_tenor == 30
    assert cfg.min_dte == 7
    assert cfg.min_option_price == 0.001
    assert cfg.min_volume == 2000
    assert cfg.risk_free_rate == 0.025


def test_config_override():
    cfg = Config(initial_capital=2_000_000, lookback_days=60)
    assert cfg.initial_capital == 2_000_000
    assert cfg.lookback_days == 60


def test_config_to_dict():
    cfg = default_config()
    d = cfg.to_dict()
    assert isinstance(d, dict)
    assert "initial_capital" in d
    assert "lookback_days" in d
