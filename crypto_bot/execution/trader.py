# crypto_bot/execution/trader.py
#
# DRY_RUN=1 → skips place_order(), logs trade to Supabase with reason
# prefixed "DRY_RUN/" so paper trades are clearly distinguishable in the DB
# but live in the same crypto_trades table.

from crypto_bot.exchange.public_api import get_primary_account_id, place_order
from crypto_bot.logging import supabase_logger
from crypto_bot.logging.logger import log, log_error
from crypto_bot.config.settings import STOP_LOSS_PCT, TAKE_PROFIT_PCT, is_dry_run


class Trader:
    def __init__(self, state: dict, run_id: str | None = None):
        self.state = state
        self.run_id = run_id
        self._account_id = None
        self._dry_run = is_dry_run()
        if self._dry_run:
            log("DRY RUN mode enabled — orders will be simulated, not placed", run_id)

    @property
    def positions(self) -> dict:
        return self.state["positions"]

    def _get_account_id(self) -> str:
        if self._account_id is None:
            self._account_id = get_primary_account_id()
        return self._account_id

    def _place(self, symbol: str, side: str, amount: float) -> bool:
        """
        Execute or simulate an order.
        Returns True on success, False on failure.
        In DRY_RUN mode, always returns True without hitting the API.
        """
        if self._dry_run:
            log(f"[DRY RUN] Would place {side} {symbol} ${amount:.2f}", self.run_id)
            return True
        try:
            place_order(self._get_account_id(), symbol, side, amount)
            return True
        except Exception as e:
            log_error(f"[trader] place_order {side} {symbol} failed: {e}", self.run_id)
            return False

    def buy(self, symbol: str, price: float, usd_amount: float) -> None:
        if not self._place(symbol, "BUY", usd_amount):
            return

        size_estimate = usd_amount / price
        self.positions[symbol] = {
            "entry": price,
            "usd_amount": usd_amount,
            "size_estimate": size_estimate,
            "stop_loss":    round(price * (1 - STOP_LOSS_PCT), 6),
            "take_profit":  round(price * (1 + TAKE_PROFIT_PCT), 6),
        }

        mode = "DRY RUN " if self._dry_run else ""
        log(
            f"{mode}BUY  {symbol} | price={price:.2f} | amount=${usd_amount:.2f} | "
            f"SL={self.positions[symbol]['stop_loss']:.2f} "
            f"TP={self.positions[symbol]['take_profit']:.2f}",
            self.run_id,
        )
        reason = "DRY_RUN/entry" if self._dry_run else "entry"
        supabase_logger.log_trade(symbol, "BUY", price, size_estimate, 0.0, reason, self.run_id)

    def sell(self, symbol: str, price: float, reason: str = "signal") -> None:
        if symbol not in self.positions:
            log_error(f"[trader] sell called for {symbol} but no open position", self.run_id)
            return

        pos = self.positions[symbol]
        usd_amount = pos["usd_amount"]
        size_estimate = pos.get("size_estimate", usd_amount / pos["entry"])
        pnl = (price / pos["entry"] - 1) * usd_amount

        full_reason = f"DRY_RUN/{reason}" if self._dry_run else reason
        if not self._place(symbol, "SELL", usd_amount):
            return

        mode = "DRY RUN " if self._dry_run else ""
        log(
            f"{mode}SELL {symbol} | price={price:.2f} | amount=${usd_amount:.2f} | "
            f"pnl={pnl:+.4f} | reason={reason}",
            self.run_id,
        )
        supabase_logger.log_trade(symbol, "SELL", price, size_estimate, pnl, full_reason, self.run_id)

        self.state["capital"] += pnl
        del self.positions[symbol]

    def check_exit(self, symbol: str, price: float) -> str | None:
        pos = self.positions.get(symbol)
        if not pos:
            return None
        if price <= pos["stop_loss"]:
            return "STOP_LOSS"
        if price >= pos["take_profit"]:
            return "TAKE_PROFIT"
        return None