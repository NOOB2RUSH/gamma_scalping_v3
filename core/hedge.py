from config import Config


def hedge_delta_to_zero(
    current_delta: float,
    etf_price: float,
    etf_min_commission: float,
    etf_commission: float,
    etf_handling_fee: float,
    etf_slippage: float,
) -> tuple[int, float, float]:
    target_qty = int(-current_delta)
    if target_qty == 0:
        return 0, 0.0, 0.0

    is_buy = target_qty > 0
    slippage_factor = 1 + etf_slippage if is_buy else 1 - etf_slippage
    exec_price = etf_price * slippage_factor
    notional = abs(target_qty) * exec_price

    commission = max(notional * etf_commission, etf_min_commission)
    handling = notional * etf_handling_fee
    total_cost = commission + handling

    cost_or_proceeds = (
        -abs(target_qty) * exec_price - total_cost
        if is_buy
        else abs(target_qty) * exec_price - total_cost
    )

    return target_qty, cost_or_proceeds, total_cost


def calculate_hedge_pnl(
    qty: int,
    entry_price: float,
    exit_price: float,
    etf_commission: float,
    etf_handling_fee: float,
    etf_stamp_tax: float,
    etf_min_commission: float,
) -> float:
    if qty == 0:
        return 0.0

    is_buy = qty > 0
    slippage_factor_exit = 1 + 0.001 if is_buy else 1 - 0.001
    exit_price_adj = exit_price * slippage_factor_exit

    if not is_buy:
        notional = abs(qty) * exit_price_adj
        stamp_tax = notional * etf_stamp_tax
    else:
        stamp_tax = 0.0

    commission_exit = max(
        abs(qty) * exit_price_adj * etf_commission, etf_min_commission
    )
    handling_exit = abs(qty) * exit_price_adj * etf_handling_fee

    pnl = qty * (exit_price_adj - entry_price)
    pnl -= commission_exit + handling_exit + stamp_tax
    return pnl
