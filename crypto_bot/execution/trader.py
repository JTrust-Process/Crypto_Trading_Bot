# crypto_bot/execution/trader.py
#
# BUY  → place_order_buy(amount_usd)   — notional USD, Public uses `amount`
# SELL → place_order_sell(quantity)    — exact units,  Public uses `quantity`
#
# This split is required by Public's API: selling by notional amount
# fails with HTTP 400 when the position value is close to the order value.

from crypto_bot.exchange.public_api import (
    get_primary_account_id,
    place_order_buy,
    place_order_sell,
)
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

    def buy(self, symbol: str, price: float, usd_amount: float) -> None:
        if self._dry_run:
            log(f"[DRY RUN] Would BUY {symbol} ${usd_amount:.2f}", self.run_id)
        else:
            try:
                place_order_buy(self._get_account_id(), symbol, usd_amount)
            except Exception as e:
                log_error(f"[trader] BUY {symbol} failed: {e}", self.run_id)
                return

        size_estimate = usd_amount / price
        self.positions[symbol] = {
            "entry":       price,
            "usd_amount":  usd_amount,
            "size_estimate": size_estimate,
            "stop_loss":   round(price * (1 - STOP_LOSS_PCT), 6),
            "take_profit": round(price * (1 + TAKE_PROFIT_PCT), 6),
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
        usd_amount   = pos["usd_amount"]
        size_estimate = pos.get("size_estimate", usd_amount / pos["entry"])
        pnl = (price / pos["entry"] - 1) * usd_amount

        if self._dry_run:
            log(f"[DRY RUN] Would SELL {symbol} qty={size_estimate:.8f}", self.run_id)
        else:
            try:
                # SELL by quantity — required by Public API when closing positions
                place_order_sell(self._get_account_id(), symbol, size_estimate)
            except Exception as e:
                log_error(f"[trader] SELL {symbol} failed: {e}", self.run_id)
                return

        mode = "DRY RUN " if self._dry_run else ""
        log(
            f"{mode}SELL {symbol} | price={price:.2f} | qty={size_estimate:.8f} | "
            f"pnl={pnl:+.4f} | reason={reason}",
            self.run_id,
        )
        full_reason = f"DRY_RUN/{reason}" if self._dry_run else reason
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