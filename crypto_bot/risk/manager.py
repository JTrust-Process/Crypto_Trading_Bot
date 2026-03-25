# crypto_bot/risk/manager.py
#
# Returns position size in USD notional (e.g. $10.00) to match
# Public API's `amount` parameter in place_order().

from crypto_bot.config.settings import RISK_PER_TRADE, STOP_LOSS_PCT


class RiskManager:
    def __init__(self, capital: float):
        self.capital = capital

    def position_size_usd(self, price: float) -> float:
        """
        Returns the USD notional amount to risk on this trade.

        Formula: (capital * risk_pct) / stop_loss_pct
        Example at $50 capital, 2% risk, 3% stop:
          risk_amount   = $1.00
          stop_loss_pct = 0.03
          usd_to_spend  = 1.00 / 0.03 = $33.33

        Capped at capital so we never spend more than we have.
        Minimum $1.00 to avoid sub-dollar order rejections.
        """
        risk_amount = self.capital * RISK_PER_TRADE
        usd_amount = risk_amount / STOP_LOSS_PCT
        usd_amount = min(usd_amount, self.capital)  # never exceed capital
        usd_amount = max(usd_amount, 1.0)           # minimum viable order
        return round(usd_amount, 2)

    def update_capital(self, pnl: float) -> None:
        self.capital += pnl