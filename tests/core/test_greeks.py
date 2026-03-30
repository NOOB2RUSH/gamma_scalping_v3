import pytest
import numpy as np
from core.greeks import (
    norm_cdf,
    norm_pdf,
    black_scholes_price,
    black_scholes_greeks,
    implied_volatility,
)


class TestNormCdf:
    def test_norm_cdf_at_zero(self):
        assert abs(norm_cdf(0) - 0.5) < 1e-6

    def test_norm_cdf_positive(self):
        assert 0.5 < norm_cdf(1) < 1.0

    def test_norm_cdf_negative(self):
        assert 0.0 < norm_cdf(-1) < 0.5


class TestNormPdf:
    def test_norm_pdf_at_zero(self):
        assert abs(norm_pdf(0) - 0.398942) < 1e-5

    def test_norm_pdf_positive(self):
        assert norm_pdf(1) < norm_pdf(0)


class TestBlackScholesPrice:
    def test_call_price_basic(self):
        price = black_scholes_price(
            s=100, k=100, t=0.5, r=0.025, sigma=0.2, option_type="C"
        )
        assert 5 < price < 15

    def test_put_price_basic(self):
        price = black_scholes_price(
            s=100, k=100, t=0.5, r=0.025, sigma=0.2, option_type="P"
        )
        assert 5 < price < 15

    def test_call_gt_put_when_s_above_k(self):
        call = black_scholes_price(
            s=110, k=100, t=0.5, r=0.025, sigma=0.2, option_type="C"
        )
        put = black_scholes_price(
            s=110, k=100, t=0.5, r=0.025, sigma=0.2, option_type="P"
        )
        assert call > put

    def test_zero_when_t_is_zero(self):
        price = black_scholes_price(
            s=100, k=100, t=0.0, r=0.025, sigma=0.2, option_type="C"
        )
        assert price == 0.0


class TestBlackScholesGreeks:
    def test_delta_call_atm(self):
        greeks = black_scholes_greeks(
            s=100, k=100, t=0.5, r=0.025, sigma=0.2, option_type="C"
        )
        assert 0.4 < greeks["delta"] < 0.6

    def test_delta_put_atm(self):
        greeks = black_scholes_greeks(
            s=100, k=100, t=0.5, r=0.025, sigma=0.2, option_type="P"
        )
        assert -0.6 < greeks["delta"] < -0.4

    def test_gamma_positive(self):
        greeks = black_scholes_greeks(
            s=100, k=100, t=0.5, r=0.025, sigma=0.2, option_type="C"
        )
        assert greeks["gamma"] > 0

    def test_call_delta_gt_put_delta(self):
        call = black_scholes_greeks(
            s=100, k=100, t=0.5, r=0.025, sigma=0.2, option_type="C"
        )
        put = black_scholes_greeks(
            s=100, k=100, t=0.5, r=0.025, sigma=0.2, option_type="P"
        )
        assert call["delta"] > put["delta"]

    def test_zero_greeks_when_t_is_zero(self):
        greeks = black_scholes_greeks(
            s=100, k=100, t=0.0, r=0.025, sigma=0.2, option_type="C"
        )
        assert greeks["delta"] == 0.0
        assert greeks["gamma"] == 0.0


class TestImpliedVolatility:
    def test_iv_recovery_call(self):
        s, k, t, r, sigma, ot = 100, 100, 0.5, 0.025, 0.2, "C"
        market = black_scholes_price(s, k, t, r, sigma, ot)
        iv = implied_volatility(market, s, k, t, r, ot)
        assert abs(iv - sigma) < 1e-4

    def test_iv_recovery_put(self):
        s, k, t, r, sigma, ot = 100, 100, 0.5, 0.025, 0.2, "P"
        market = black_scholes_price(s, k, t, r, sigma, ot)
        iv = implied_volatility(market, s, k, t, r, ot)
        assert abs(iv - sigma) < 1e-4

    def test_iv_zero_when_t_is_zero(self):
        iv = implied_volatility(5.0, 100, 100, 0.0, 0.025, "C")
        assert iv == 0.0

    def test_iv_zero_when_price_is_zero(self):
        iv = implied_volatility(0.0, 100, 100, 0.5, 0.025, "C")
        assert iv == 0.0
