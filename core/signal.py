from core.greeks import black_scholes_greeks, implied_volatility, black_scholes_price


def calculate_option_price(bid: float, ask: float) -> float:
    return (bid + ask) / 2.0


def calculate_greeks_for_option(
    s: float,
    k: float,
    t: float,
    r: float,
    sigma: float,
    option_type: str,
) -> dict[str, float]:
    return black_scholes_greeks(s, k, t, r, sigma, option_type)


def calculate_position_greeks(
    call_greeks: dict[str, float],
    put_greeks: dict[str, float],
    contract_multiplier: int = 10000,
) -> dict[str, float]:
    return {
        "delta": (call_greeks["delta"] + put_greeks["delta"]) * contract_multiplier,
        "gamma": (call_greeks["gamma"] + put_greeks["gamma"]) * contract_multiplier,
        "vega": (call_greeks["vega"] + put_greeks["vega"]) * contract_multiplier,
        "theta": (call_greeks["theta"] + put_greeks["theta"]) * contract_multiplier,
    }


def check_open_signals(
    iv_percentile: float,
    cash: float,
    call_volume: int,
    put_volume: int,
    open_threshold: float,
    min_volume: int,
) -> tuple[bool, str]:
    if iv_percentile >= open_threshold:
        return (
            False,
            f"IV percentile {iv_percentile:.1%} >= threshold {open_threshold:.1%}",
        )
    if cash <= 0:
        return False, "No available cash"
    if call_volume < min_volume or put_volume < min_volume:
        return False, f"Low liquidity: call_vol={call_volume}, put_vol={put_volume}"
    return True, "OK"


def check_close_signals(
    iv_percentile: float,
    dte: int,
    holding_days: int,
    close_threshold: float,
    close_dte_threshold: int,
    max_holding_days: int,
) -> tuple[bool, str]:
    if iv_percentile > close_threshold:
        return (
            True,
            f"IV percentile {iv_percentile:.1%} > threshold {close_threshold:.1%}",
        )
    if dte <= close_dte_threshold:
        return True, f"Near expiry: DTE={dte} <= {close_dte_threshold}"
    if holding_days > max_holding_days:
        return True, f"Max holding days: {holding_days} > {max_holding_days}"
    return False, "No close signal"


def should_hedge(delta: float, threshold: float) -> bool:
    return abs(delta) > threshold
