from scipy.stats import norm
from scipy.optimize import brentq
import numpy as np


def norm_cdf(x: float) -> float:
    return norm.cdf(x)


def norm_pdf(x: float) -> float:
    return norm.pdf(x)


def black_scholes_price(
    s: float,
    k: float,
    t: float,
    r: float,
    sigma: float,
    option_type: str,
) -> float:
    if t <= 0 or sigma <= 0:
        return 0.0
    d1 = (np.log(s / k) + (r + 0.5 * sigma**2) * t) / (sigma * np.sqrt(t))
    d2 = d1 - sigma * np.sqrt(t)
    if option_type == "C":
        return s * norm_cdf(d1) - k * np.exp(-r * t) * norm_cdf(d2)
    else:
        return k * np.exp(-r * t) * norm_cdf(-d2) - s * norm_cdf(-d1)


def black_scholes_greeks(
    s: float,
    k: float,
    t: float,
    r: float,
    sigma: float,
    option_type: str,
) -> dict[str, float]:
    if t <= 0 or sigma <= 0:
        return {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0}
    d1 = (np.log(s / k) + (r + 0.5 * sigma**2) * t) / (sigma * np.sqrt(t))
    d2 = d1 - sigma * np.sqrt(t)
    sqrt_t = np.sqrt(t)
    phi = norm_pdf(d1)
    if option_type == "C":
        delta = norm_cdf(d1)
        theta = (
            -s * phi * sigma / (2 * sqrt_t) - r * k * np.exp(-r * t) * norm_cdf(d2)
        ) / 365
    else:
        delta = norm_cdf(d1) - 1
        theta = (
            -s * phi * sigma / (2 * sqrt_t) + r * k * np.exp(-r * t) * norm_cdf(-d2)
        ) / 365
    gamma = phi / (s * sigma * sqrt_t)
    vega = s * phi * sqrt_t / 100
    return {"delta": delta, "gamma": gamma, "vega": vega, "theta": theta}


def implied_volatility(
    market_price: float,
    s: float,
    k: float,
    t: float,
    r: float,
    option_type: str,
) -> float:
    if t <= 0 or market_price <= 0:
        return 0.0

    def objective(sigma: float) -> float:
        return black_scholes_price(s, k, t, r, sigma, option_type) - market_price

    try:
        iv = brentq(objective, 1e-6, 5.0, xtol=1e-8)
        return iv
    except ValueError:
        return 0.0
