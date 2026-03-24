# crypto_bot/risk/manager.py

from crypto_bot.config.settings import RISK_PER_TRADE, STOP_LOSS_PCT

class RiskManager:
    def __init__(self, capital):
        self.capital = capital

    def position_size(self, price):
        risk_amount = self.capital * RISK_PER_TRADE
        stop_distance = price * STOP_LOSS_PCT
        size = risk_amount / stop_distance
        return size
