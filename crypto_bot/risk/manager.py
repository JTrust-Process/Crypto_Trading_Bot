# crypto_bot/risk/manager.py

from crypto_bot.config.settings import RISK_PER_TRADE, STOP_LOSS_PCT, get_max_order_usd


class RiskManager:
    def __init__(self, capital: float):
        self.capital = capital

    def position_size_usd(self, price: float) -> float:
        """
        Returns USD notional amount to spend on this trade.

        Formula: (capital * risk_pct) / stop_loss_pct
        Hard capped at MAX_ORDER_AMOUNT_USD so a growing account
        never places oversized orders.

        Example at $15 capital, 2% risk, 3% stop, $10 cap:
          risk_amount  = $0.30
          usd_to_spend = 0.30 / 0.03 = $10.00  → capped at $10
        """
        risk_amount = self.capital * RISK_PER_TRADE
        usd_amount  = risk_amount / STOP_LOSS_PCT
        usd_amount  = min(usd_amount, self.capital)     # never exceed capital
        usd_amount  = min(usd_amount, get_max_order_usd())  # hard cap
        usd_amount  = max(usd_amount, 1.0)              # minimum viable order
        return round(usd_amount, 2)

    def update_capital(self, pnl: float) -> None:
        self.capital += pnl