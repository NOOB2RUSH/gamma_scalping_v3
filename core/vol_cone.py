import numpy as np
import pandas as pd
from typing import Optional


TENOR_BUCKETS = [
    (7, 5, 9),
    (14, 10, 18),
    (30, 22, 37),
    (60, 45, 75),
    (90, 75, 105),
]
PERCENTILES = [100, 90, 85, 80, 75, 50, 25, 20, 15, 10, 0]
MIN_LOOKBACK_DAYS = 60


def dte_to_tenor_bucket(dte: int) -> Optional[int]:
    for tenor_target, dte_min, dte_max in TENOR_BUCKETS:
        if dte_min <= dte <= dte_max:
            return tenor_target
    return None


def compute_iv_percentile(
    iv: float,
    historical_ivs: list[float],
) -> float:
    if not historical_ivs:
        return 0.5
    below = sum(1 for v in historical_ivs if v < iv)
    equal = sum(1 for v in historical_ivs if v == iv)
    n = len(historical_ivs)
    rank = (below + 0.5 * equal) / n
    return max(0.0, min(1.0, rank))


def build_vol_cone(
    trade_date: str,
    iv_history: pd.DataFrame,
    lookback_days: int = 120,
) -> dict[int, dict[int, float]]:
    current_dt = pd.to_datetime(trade_date)
    iv_history = iv_history.copy()
    iv_history["date"] = pd.to_datetime(iv_history["date"])
    past = iv_history[iv_history["date"] < current_dt].tail(lookback_days)
    if len(past) < MIN_LOOKBACK_DAYS:
        return {}

    result: dict[int, dict[int, float]] = {}
    for tenor_target, dte_min, dte_max in TENOR_BUCKETS:
        bucket_ivs = past[past["dte"].between(dte_min, dte_max)]["iv"].tolist()
        if len(bucket_ivs) < 2:
            continue
        pct_values: dict[int, float] = {}
        for p in PERCENTILES:
            pct_values[p] = float(np.percentile(bucket_ivs, p))
        result[tenor_target] = pct_values

    return result


def current_iv_percentile(
    current_iv: float,
    trade_date: str,
    iv_history: pd.DataFrame,
    target_tenor: int,
    lookback_days: int = 120,
) -> Optional[float]:
    current_dt = pd.to_datetime(trade_date)
    iv_history = iv_history.copy()
    iv_history["date"] = pd.to_datetime(iv_history["date"])
    past = iv_history[iv_history["date"] < current_dt].tail(lookback_days)
    if len(past) < MIN_LOOKBACK_DAYS:
        return None

    tenor_bounds = {t: (mn, mx) for t, mn, mx in TENOR_BUCKETS}
    if target_tenor not in tenor_bounds:
        return None
    dte_min, dte_max = tenor_bounds[target_tenor]
    bucket_ivs = past[past["dte"].between(dte_min, dte_max)]["iv"].tolist()
    if len(bucket_ivs) < 5:
        return None

    return compute_iv_percentile(current_iv, bucket_ivs)
