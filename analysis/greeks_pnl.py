class GreeksPnlAnalyzer:
    def __init__(self):
        self.positions: list[dict] = []

    def _get_net_hedge_qty_on_date(self, hedge_records: list[dict], date: str) -> float:
        """Compute the net hedge quantity that was in effect on a given date.

        Sums all hedge qty where hedge date <= date and hedge is still open
        (exit_date is None or exit_date > date).
        """
        net_qty = 0.0
        for rec in hedge_records:
            hedge_date = rec.get("date")
            exit_date = rec.get("exit_date")
            qty = rec.get("qty", 0)

            # Hedge was added on or before this date
            if hedge_date and hedge_date <= date:
                # Hedge is still open if no exit_date or exit_date is after this date
                if exit_date is None or exit_date > date:
                    net_qty += qty
        return net_qty

    def _get_post_hedge_delta(
        self, delta: float, hedge_records: list[dict], date: str
    ) -> float:
        """Compute post-hedge delta = pre-hedge delta + net_hedge_qty."""
        net_hedge_qty = self._get_net_hedge_qty_on_date(hedge_records, date)
        return delta + net_hedge_qty

    def compute_delta_pnl(
        self, greeks_records: list[dict], ds_underlying: float
    ) -> float:
        if len(greeks_records) < 2:
            return 0.0
        total = 0.0
        for i in range(len(greeks_records) - 1):
            delta_avg = (
                greeks_records[i]["delta"] + greeks_records[i + 1]["delta"]
            ) / 2
            total += delta_avg * ds_underlying
        return total

    def compute_gamma_pnl(
        self, greeks_records: list[dict], ds_underlying: float
    ) -> float:
        if len(greeks_records) < 2:
            return 0.0
        total = 0.0
        for i in range(len(greeks_records) - 1):
            gamma_avg = (
                greeks_records[i]["gamma"] + greeks_records[i + 1]["gamma"]
            ) / 2
            total += 0.25 * gamma_avg * (ds_underlying**2)
        return total

    def compute_theta_pnl(self, greeks_records: list[dict], dt: float) -> float:
        if len(greeks_records) < 2:
            return 0.0
        total = 0.0
        for i in range(len(greeks_records) - 1):
            theta_avg = (
                greeks_records[i]["theta"] + greeks_records[i + 1]["theta"]
            ) / 2
            total += theta_avg * dt
        return total

    def compute_vega_pnl(self, greeks_records: list[dict], d_sigma: float) -> float:
        if len(greeks_records) < 2:
            return 0.0
        total = 0.0
        for i in range(len(greeks_records) - 1):
            vega_avg = (greeks_records[i]["vega"] + greeks_records[i + 1]["vega"]) / 2
            total += vega_avg * d_sigma
        return total

    def compute_total_pnl(
        self, delta_pnl: float, gamma_pnl: float, theta_pnl: float, vega_pnl: float
    ) -> float:
        return delta_pnl + gamma_pnl + theta_pnl + vega_pnl

    def analyze_position(
        self,
        position,
        underlying_prices: dict[str, float],
        iv_history: dict[str, float],
    ) -> dict:
        """
        Compute Greeks P&L decomposition for a closed position.
        Uses trapezoidal integration per design doc Sec 6.5.

        Formulas (per interval i):
          Delta P&L  = (Δ_i + Δ_{i+1}) / 2 × (S_{i+1} - S_i)
          Gamma P&L  = 1/4 × (Γ_i + Γ_{i+1}) × (S_{i+1} - S_i)²
          Theta P&L  = (Θ_i + Θ_{i+1}) / 2 × (1/252)
          Vega P&L   = (V_i + V_{i+1}) / 2 × (IV_{i+1} - IV_i)

        Returns dict with keys: delta_pnl, gamma_pnl, theta_pnl, vega_pnl, total_pnl, error_pct
        where error_pct = abs(actual_pnl - total_pnl) / abs(actual_pnl) * 100
        """
        daily_greeks = position.daily_greeks
        if len(daily_greeks) < 2:
            return {
                "delta_pnl": 0.0,
                "gamma_pnl": 0.0,
                "theta_pnl": 0.0,
                "vega_pnl": 0.0,
                "total_pnl": 0.0,
                "error_pct": 0.0,
            }

        delta_pnl = 0.0
        gamma_pnl = 0.0
        theta_pnl = 0.0
        vega_pnl = 0.0
        dt = 1.0 / 252.0

        # Get hedge_records from position for computing post-hedge delta
        hedge_records = getattr(position, "hedge_records", [])

        for i in range(len(daily_greeks) - 1):
            date_i = daily_greeks[i]["date"]
            date_ip1 = daily_greeks[i + 1]["date"]

            # Get underlying prices for delta and gamma calculation
            s_i = underlying_prices.get(date_i, 0.0)
            s_ip1 = underlying_prices.get(date_ip1, s_i)
            ds = s_ip1 - s_i

            # Use pre-hedge delta (option delta before hedging adjustment)
            delta_i = daily_greeks[i].get("delta", 0.0)
            delta_ip1 = daily_greeks[i + 1].get("delta", 0.0)

            # Gamma, theta, vega always use pre-hedge values (they represent theoretical Greek exposure)
            gamma_i = daily_greeks[i].get("gamma", 0.0)
            gamma_ip1 = daily_greeks[i + 1].get("gamma", 0.0)
            theta_i = daily_greeks[i].get("theta", 0.0)
            theta_ip1 = daily_greeks[i + 1].get("theta", 0.0)
            vega_i = daily_greeks[i].get("vega", 0.0)
            vega_ip1 = daily_greeks[i + 1].get("vega", 0.0)

            # Delta P&L: (Δ_i + Δ_{i+1}) / 2 × (S_{i+1} - S_i)
            delta_pnl += (delta_i + delta_ip1) / 2.0 * ds

            # Gamma P&L: 1/4 × (Γ_i + Γ_{i+1}) × (S_{i+1} - S_i)²  (design doc Sec 6.5)
            gamma_pnl += 0.25 * (gamma_i + gamma_ip1) * (ds**2)

            # Theta P&L: (Θ_i + Θ_{i+1}) / 2 × (1/252)
            theta_pnl += (theta_i + theta_ip1) / 2.0 * dt

            # Vega P&L: (V_i + V_{i+1}) / 2 × (IV_{i+1} - IV_i)
            iv_i = iv_history.get(date_i, 0.0)
            iv_ip1 = iv_history.get(date_ip1, iv_i)
            d_iv = iv_ip1 - iv_i
            vega_pnl += (vega_i + vega_ip1) / 2.0 * d_iv

        total_pnl = delta_pnl + gamma_pnl + theta_pnl + vega_pnl

        # Calculate error percentage based on actual option P&L (excluding hedge)
        actual_pnl = position.net_pnl
        if actual_pnl != 0:
            error_pct = abs(actual_pnl - total_pnl) / abs(actual_pnl) * 100
        else:
            error_pct = 0.0 if total_pnl == 0 else 100.0

        return {
            "delta_pnl": delta_pnl,
            "gamma_pnl": gamma_pnl,
            "theta_pnl": theta_pnl,
            "vega_pnl": vega_pnl,
            "total_pnl": total_pnl,
            "error_pct": error_pct,
        }

    def analyze_position_by_interval(
        self,
        position,
        underlying_prices: dict[str, float],
        iv_history: dict[str, float],
    ) -> list[dict]:
        """
        Compute per-interval Greeks P&L decomposition for a closed position.
        Returns list of per-interval dicts:
        [{"date": "2025-03-25", "delta_pnl": 9.05, "gamma_pnl": -28.4, "theta_pnl": 0.07, "vega_pnl": -0.05}, ...]

        Each interval's P&L goes to its corresponding date (the end date of the interval).
        The date in each dict is date_{i+1} (the end of interval i).
        """
        daily_greeks = position.daily_greeks
        if len(daily_greeks) < 2:
            return []

        dt = 1.0 / 252.0
        interval_results = []

        # Get hedge_records from position for computing post-hedge delta
        hedge_records = getattr(position, "hedge_records", [])

        for i in range(len(daily_greeks) - 1):
            date_i = daily_greeks[i]["date"]
            date_ip1 = daily_greeks[i + 1]["date"]

            # Get underlying prices for delta and gamma calculation
            s_i = underlying_prices.get(date_i, 0.0)
            s_ip1 = underlying_prices.get(date_ip1, s_i)
            ds = s_ip1 - s_i

            # Use pre-hedge delta (option delta before hedging adjustment)
            delta_i = daily_greeks[i].get("delta", 0.0)
            delta_ip1 = daily_greeks[i + 1].get("delta", 0.0)

            # Gamma, theta, vega always use pre-hedge values
            gamma_i = daily_greeks[i].get("gamma", 0.0)
            gamma_ip1 = daily_greeks[i + 1].get("gamma", 0.0)
            theta_i = daily_greeks[i].get("theta", 0.0)
            theta_ip1 = daily_greeks[i + 1].get("theta", 0.0)
            vega_i = daily_greeks[i].get("vega", 0.0)
            vega_ip1 = daily_greeks[i + 1].get("vega", 0.0)

            # Delta P&L: (Δ_i + Δ_{i+1}) / 2 × (S_{i+1} - S_i)
            delta_pnl = (delta_i + delta_ip1) / 2.0 * ds

            # Gamma P&L: 1/4 × (Γ_i + Γ_{i+1}) × (S_{i+1} - S_i)²
            gamma_pnl = 0.25 * (gamma_i + gamma_ip1) * (ds**2)

            # Theta P&L: (Θ_i + Θ_{i+1}) / 2 × (1/252)
            theta_pnl = (theta_i + theta_ip1) / 2.0 * dt

            # Vega P&L: (V_i + V_{i+1}) / 2 × (IV_{i+1} - IV_i)
            iv_i = iv_history.get(date_i, 0.0)
            iv_ip1 = iv_history.get(date_ip1, iv_i)
            d_iv = iv_ip1 - iv_i
            vega_pnl = (vega_i + vega_ip1) / 2.0 * d_iv

            interval_results.append(
                {
                    "date": date_ip1,  # End date of interval i
                    "delta_pnl": delta_pnl,
                    "gamma_pnl": gamma_pnl,
                    "theta_pnl": theta_pnl,
                    "vega_pnl": vega_pnl,
                }
            )

        return interval_results
