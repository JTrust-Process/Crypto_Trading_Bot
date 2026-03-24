# crypto_bot/execution/trader.py

class Trader:
    def __init__(self):
        self.position = None

    def buy(self, symbol, price, size):
        self.position = {
            "symbol": symbol,
            "entry": price,
            "size": size,
            "stop_loss": price * 0.97,
            "take_profit": price * 1.05
        }
        print(f"BUY {symbol} | Price: {price:.2f} | Size: {size:.4f}")

    def check_exit(self, price):
        if not self.position:
            return None

        if price <= self.position["stop_loss"]:
            return "STOP_LOSS"

        if price >= self.position["take_profit"]:
            return "TAKE_PROFIT"

        return None

    def sell(self, price, reason="manual"):
        entry = self.position["entry"]
        pnl = (price - entry) * self.position["size"]

        print(f"SELL | Price: {price:.2f} | PnL: {pnl:.2f} | Reason: {reason}")

        self.position = None
