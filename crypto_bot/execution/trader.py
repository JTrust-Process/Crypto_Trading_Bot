# crypto_bot/execution/trader.py
#
# After placing any order, polls get_order() to get the real fill price
# (averagePrice) and filled quantity instead of using the quote price.
#
# Why this matters: market orders fill at exchange execution price which
# can differ from the quote price at signal time. Using the real fill
# price ensures P&L calculations are accurate.
#
# Polling strategy: try up to 5 times with 2s delay.
# If the order isn't filled yet (NEW/PARTIALLY_FILLED) or 404s due to
# eventual consistency, fall back to the quote price gracefully.

import time
from crypto_bot.exchange.public_api import (
    get_primary_account_id,
    place_order_buy,
    place_order_sell,
    get_order,
    get_cash_buying_power,
    get_crypto_position_quantity,
)
from crypto_bot.logging import supabase_logger
from crypto_bot.logging.logger import log, log_error, log_warn
from crypto_bot.notifications import discord
from crypto_bot.state.state import record_win, record_loss
from crypto_bot.config.settings import STOP_LOSS_PCT, TAKE_PROFIT_PCT, is_dry_run, get_min_buying_power_buffer

FILL_POLL_ATTEMPTS = 5
FILL_POLL_DELAY    = 2  # seconds between polls


def _poll_fill_price(account_id: str, order_id: str, fallback_price: float) -> tuple[float, float]:
    """
    Poll get_order() until the order is FILLED or attempts are exhausted.

    Returns (fill_price, filled_quantity).
    Falls back to (fallback_price, 0.0) if fill can't be confirmed.
    """
    for attempt in range(1, FILL_POLL_ATTEMPTS + 1):
        try:
            order = get_order(account_id, order_id)
            status = order.get("status", "")
            avg_price = order.get("averagePrice")
            filled_qty = order.get("filledQuantity")

            if status == "FILLED" and avg_price:
                return float(avg_price), float(filled_qty or 0)

            if status in ("CANCELLED", "REJECTED", "EXPIRED"):
                log_warn(f"[trader] Order {order_id} ended with status {status}")
                return fallback_price, 0.0

            # Still pending — wait and retry
            if attempt < FILL_POLL_ATTEMPTS:
                time.sleep(FILL_POLL_DELAY)

        except Exception as e:
            if attempt < FILL_POLL_ATTEMPTS:
                time.sleep(FILL_POLL_DELAY)
            else:
                log_warn(f"[trader] Could not confirm fill for {order_id}: {e} — using quote price")

    return fallback_price, 0.0


class Trader:
    def __init__(self, state: dict, run_id: str | None = None):
        self.state       = state
        self.run_id      = run_id
        self._account_id = None
        self._dry_run    = is_dry_run()
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
        fill_price = price  # default to quote price

        if self._dry_run:
            log(f"[DRY RUN] Would BUY {symbol} ${usd_amount:.2f}", self.run_id)
        else:
            # Check buying power before placing order.
            # Ensures we never spend below the minimum buffer, preventing
            # margin maintenance calls when both bots are running.
            try:
                cash_bp = get_cash_buying_power(self._get_account_id())
                buffer  = get_min_buying_power_buffer()
                if cash_bp - usd_amount < buffer:
                    log_warn(
                        f"[trader] BUY {symbol} skipped — buying power ${cash_bp:.2f} "
                        f"would drop below ${buffer:.2f} buffer after ${usd_amount:.2f} order",
                        self.run_id,
                    )
                    return
                log(f"[trader] Buying power check passed — ${cash_bp:.2f} available, need ${usd_amount:.2f} + ${buffer:.2f} buffer", self.run_id)
            except Exception as e:
                log_warn(f"[trader] Buying power check failed: {e} — proceeding with order", self.run_id)

            try:
                result   = place_order_buy(self._get_account_id(), symbol, usd_amount)
                order_id = result.get("orderId") or result.get("_clientOrderId")

                # Poll for real fill price
                if order_id:
                    raw_fill, _ = _poll_fill_price(self._get_account_id(), order_id, price)
                    if raw_fill > 0:
                        fill_price = raw_fill
                        if fill_price != price:
                            log(f"[trader] BUY {symbol} fill price {fill_price:.2f} (quote was {price:.2f})", self.run_id)
                    else:
                        log_warn(f"[trader] BUY {symbol} fill price from API was invalid ({raw_fill:.2f}) — using quote price {price:.2f}", self.run_id)
                        fill_price = price

            except Exception as e:
                log_error(f"[trader] BUY {symbol} failed: {e}", self.run_id)
                discord.notify_error(f"BUY {symbol}", str(e))
                return

        # Use real fill price for SL/TP and position tracking
        sl            = round(fill_price * (1 - STOP_LOSS_PCT), 6)
        tp            = round(fill_price * (1 + TAKE_PROFIT_PCT), 6)
        size_estimate = usd_amount / fill_price

        self.positions[symbol] = {
            "entry":         fill_price,
            "usd_amount":    usd_amount,
            "size_estimate": size_estimate,
            "stop_loss":     sl,
            "take_profit":   tp,
            # Track candle count at entry for minimum hold time check
            "entry_candle":  len(self.state["price_history"].get(symbol, [])),
        }

        mode = "DRY RUN " if self._dry_run else ""
        log(
            f"{mode}BUY  {symbol} | fill={fill_price:.2f} | amount=${usd_amount:.2f} | "
            f"SL={sl:.2f} TP={tp:.2f}",
            self.run_id,
        )

        reason = "DRY_RUN/entry" if self._dry_run else "entry"
        supabase_logger.log_trade(symbol, "BUY", fill_price, size_estimate, 0.0, reason, self.run_id)

        if not self._dry_run:
            discord.notify_buy(symbol, fill_price, usd_amount, sl, tp)

    def sell(self, symbol: str, price: float, reason: str = "signal") -> None:
        if symbol not in self.positions:
            log_error(f"[trader] sell called for {symbol} but no open position", self.run_id)
            return

        pos           = self.positions[symbol]
        usd_amount    = pos["usd_amount"]
        size_estimate = pos.get("size_estimate", 0)

        # Guard against zero/missing size — recalculate from entry if needed
        if not size_estimate or size_estimate <= 0:
            size_estimate = usd_amount / pos["entry"]
            log_warn(f"[trader] {symbol} size_estimate was 0 — recalculated as {size_estimate:.8f} from entry", self.run_id)

        fill_price    = price  # default to quote price

        if self._dry_run:
            log(f"[DRY RUN] Would SELL {symbol} qty={size_estimate:.8f}", self.run_id)
        else:
            # Fetch actual position quantity from Public before selling.
            # Our size_estimate may differ from actual fill due to fees/rounding
            # or bad fill price data — using the real quantity prevents
            # "would result in short position" rejections.
            try:
                real_qty = get_crypto_position_quantity(self._get_account_id(), symbol)
                if real_qty is not None and real_qty > 0:
                    if abs(real_qty - size_estimate) / size_estimate > 0.01:
                        log_warn(
                            f"[trader] {symbol} size_estimate {size_estimate:.8f} differs from "
                            f"actual position {real_qty:.8f} — using real quantity",
                            self.run_id,
                        )
                    size_estimate = real_qty
                else:
                    log_warn(f"[trader] Could not fetch real {symbol} quantity — using estimate {size_estimate:.8f}", self.run_id)
            except Exception as e:
                log_warn(f"[trader] Portfolio quantity check failed: {e} — using estimate", self.run_id)

            try:
                result   = place_order_sell(self._get_account_id(), symbol, size_estimate)
                order_id = result.get("orderId") or result.get("_clientOrderId")

                # Poll for real fill price
                if order_id:
                    raw_fill, filled_qty = _poll_fill_price(self._get_account_id(), order_id, price)
                    if raw_fill > 0:
                        fill_price = raw_fill
                        if fill_price != price:
                            log(f"[trader] SELL {symbol} fill price {fill_price:.2f} (quote was {price:.2f})", self.run_id)
                    else:
                        log_warn(f"[trader] SELL {symbol} fill price from API was invalid ({raw_fill:.2f}) — using quote price {price:.2f}", self.run_id)
                        fill_price = price
                    # Use actual filled quantity if available for more accurate P&L
                    if filled_qty > 0:
                        size_estimate = filled_qty

            except Exception as e:
                log_error(f"[trader] SELL {symbol} failed: {e}", self.run_id)
                discord.notify_error(f"SELL {symbol}", str(e))
                return

        # P&L calculated using real fill prices on both sides
        pnl = (fill_price / pos["entry"] - 1) * usd_amount

        mode = "DRY RUN " if self._dry_run else ""
        log(
            f"{mode}SELL {symbol} | fill={fill_price:.2f} | qty={size_estimate:.8f} | "
            f"pnl={pnl:+.4f} | reason={reason}",
            self.run_id,
        )

        full_reason = f"DRY_RUN/{reason}" if self._dry_run else reason
        supabase_logger.log_trade(symbol, "SELL", fill_price, size_estimate, pnl, full_reason, self.run_id)

        if pnl >= 0:
            record_win(self.state, symbol)
        else:
            record_loss(self.state, symbol)

        if not self._dry_run:
            discord.notify_sell(symbol, fill_price, pnl, reason)

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