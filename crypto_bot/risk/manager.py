# crypto_bot/risk/manager.py
#
# Issue 2 fix: position_size_usd now reads capital LIVE from state
# instead of the snapshot passed in at startup. This means if multiple
# trades close in the same run, each new buy sizes from the updated
# capital, not the stale pre-run value.

from crypto_bot.config.settings import RISK_PER_TRADE, STOP_LOSS_PCT, get_max_order_usd


class RiskManager:
    def __init__(self, state: dict):
        """
        Holds a reference to the state dict so capital reads stay live.
        """
        self.state = state

    @property
    def capital(self) -> float:
        return self.state.get("capital", 0.0)

    def position_size_usd(self, price: float) -> float:
        """
        Returns USD notional amount to spend on this trade.

        Formula: (capital * risk_pct) / stop_loss_pct
        Hard capped at MAX_ORDER_AMOUNT_USD so a growing account
        never places oversized orders.

        Example at $50 capital, 2% risk, 3% stop, $25 cap:
          risk_amount  = $1.00
          usd_to_spend = 1.00 / 0.03 = $33.33  → capped at $25
        """
        capital     = self.capital
        risk_amount = capital * RISK_PER_TRADE
        usd_amount  = risk_amount / STOP_LOSS_PCT
        usd_amount  = min(usd_amount, capital)              # never exceed capital
        usd_amount  = min(usd_amount, get_max_order_usd())  # hard cap
        usd_amount  = max(usd_amount, 1.0)                  # minimum viable
        return round(usd_amount, 2)