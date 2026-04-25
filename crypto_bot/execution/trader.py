# crypto_bot/execution/trader.py
#
# Fixes from audit:
#   - Issue 4: P&L computed from actual fill_price × size, not stale usd_amount
#   - Issue 6: candles_at_entry naming clarified (was entry_candle)
#   - Issue 9: poll attempts increased 5→8, delay 2s→2.5s = 20s max wait

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
from crypto_bot.config.settings import (
    STOP_LOSS_PCT, TAKE_PROFIT_PCT, is_dry_run, get_min_buying_power_buffer,
)

FILL_POLL_ATTEMPTS = 8     # up from 5 — Public has eventual consistency on order endpoint
FILL_POLL_DELAY    = 2.5   # 8 × 2.5s = 20s max wait


def _poll_fill_price(account_id: str, order_id: str, fallback_price: float) -> tuple[float, float]:
    """
    Poll get_order() until the order is FILLED or attempts exhausted.
    Returns (fill_price, filled_quantity).
    """
    for attempt in range(1, FILL_POLL_ATTEMPTS + 1):
        try:
            order = get_order(account_id, order_id)
            status     = order.get("status", "")
            avg_price  = order.get("averagePrice")
            filled_qty = order.get("filledQuantity")

            if status == "FILLED" and avg_price:
                return float(avg_price), float(filled_qty or 0)

            if status in ("CANCELLED", "REJECTED", "EXPIRED"):
                log_warn(f"[trader] Order {order_id} ended with status {status}")
                return fallback_price, 0.0

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
        return self.state.setdefault("positions", {})

    def _get_account_id(self) -> str:
        if self._account_id is None:
            self._account_id = get_primary_account_id()
        return self._account_id

    # ── BUY ────────────────────────────────────────────────────────────────────
    def buy(self, symbol: str, price: float, usd_amount: float) -> None:
        fill_price = price
        actual_qty: float | None = None

        if self._dry_run:
            log(f"[DRY RUN] Would BUY {symbol} ${usd_amount:.2f}", self.run_id)
        else:
            # Buying power check
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
                log(
                    f"[trader] Buying power check passed — ${cash_bp:.2f} available, "
                    f"need ${usd_amount:.2f} + ${buffer:.2f} buffer",
                    self.run_id,
                )
            except Exception as e:
                log_warn(f"[trader] Buying power check failed: {e} — proceeding with order", self.run_id)

            try:
                result   = place_order_buy(self._get_account_id(), symbol, usd_amount)
                order_id = result.get("orderId") or result.get("_clientOrderId")

                if order_id:
                    raw_fill, raw_qty = _poll_fill_price(self._get_account_id(), order_id, price)
                    if raw_fill > 0:
                        fill_price = raw_fill
                        if fill_price != price:
                            log(
                                f"[trader] BUY {symbol} fill price {fill_price:.2f} (quote was {price:.2f})",
                                self.run_id,
                            )
                    else:
                        log_warn(
                            f"[trader] BUY {symbol} fill price from API was invalid ({raw_fill:.2f}) "
                            f"— using quote price {price:.2f}",
                            self.run_id,
                        )
                        fill_price = price
                    if raw_qty > 0:
                        actual_qty = raw_qty

            except Exception as e:
                log_error(f"[trader] BUY {symbol} failed: {e}", self.run_id)
                discord.notify_error(f"BUY {symbol}", str(e))
                return

        # Use actual filled quantity if available (issue 4 — was using stale usd_amount/entry)
        size_estimate = actual_qty if actual_qty else (usd_amount / fill_price)

        sl = round(fill_price * (1 - STOP_LOSS_PCT), 6)
        tp = round(fill_price * (1 + TAKE_PROFIT_PCT), 6)

        # candles_at_entry (renamed from entry_candle for clarity, audit issue 6)
        # By this point append_price has run, so price_history includes the entry candle.
        candles_at_entry = len(self.state.get("price_history", {}).get(symbol, []))

        self.positions[symbol] = {
            "entry":            fill_price,
            "usd_amount":       usd_amount,
            "size_estimate":    size_estimate,
            "stop_loss":        sl,
            "take_profit":      tp,
            "candles_at_entry": candles_at_entry,
            # Keep legacy key for backward-compat with old state files
            "entry_candle":     candles_at_entry,
        }

        mode = "DRY RUN " if self._dry_run else ""
        log(
            f"{mode}BUY  {symbol} | fill={fill_price:.2f} | amount=${usd_amount:.2f} | "
            f"qty={size_estimate:.8f} | SL={sl:.2f} TP={tp:.2f}",
            self.run_id,
        )

        reason = "DRY_RUN/entry" if self._dry_run else "entry"
        supabase_logger.log_trade(symbol, "BUY", fill_price, size_estimate, 0.0, reason, self.run_id)

        if not self._dry_run:
            discord.notify_buy(symbol, fill_price, usd_amount, sl, tp)

    # ── SELL ───────────────────────────────────────────────────────────────────
    def sell(self, symbol: str, price: float, reason: str = "signal") -> None:
        if symbol not in self.positions:
            log_error(f"[trader] sell called for {symbol} but no open position", self.run_id)
            return

        pos           = self.positions[symbol]
        entry_price   = pos["entry"]
        usd_amount    = pos["usd_amount"]
        size_estimate = pos.get("size_estimate", 0)

        if not size_estimate or size_estimate <= 0:
            size_estimate = usd_amount / entry_price
            log_warn(
                f"[trader] {symbol} size_estimate was 0 — recalculated as {size_estimate:.8f} from entry",
                self.run_id,
            )

        fill_price = price

        if self._dry_run:
            log(f"[DRY RUN] Would SELL {symbol} qty={size_estimate:.8f}", self.run_id)
        else:
            # Get real position quantity from Public to avoid short-position errors
            try:
                real_qty = get_crypto_position_quantity(self._get_account_id(), symbol)
                if real_qty is not None and real_qty > 0:
                    if size_estimate > 0 and abs(real_qty - size_estimate) / size_estimate > 0.01:
                        log_warn(
                            f"[trader] {symbol} size_estimate {size_estimate:.8f} differs from "
                            f"actual position {real_qty:.8f} — using real quantity",
                            self.run_id,
                        )
                    size_estimate = real_qty
                else:
                    log_warn(
                        f"[trader] Could not fetch real {symbol} quantity — using estimate {size_estimate:.8f}",
                        self.run_id,
                    )
            except Exception as e:
                log_warn(f"[trader] Portfolio quantity check failed: {e} — using estimate", self.run_id)

            try:
                result   = place_order_sell(self._get_account_id(), symbol, size_estimate)
                order_id = result.get("orderId") or result.get("_clientOrderId")

                if order_id:
                    raw_fill, filled_qty = _poll_fill_price(self._get_account_id(), order_id, price)
                    if raw_fill > 0:
                        fill_price = raw_fill
                        if fill_price != price:
                            log(
                                f"[trader] SELL {symbol} fill price {fill_price:.2f} (quote was {price:.2f})",
                                self.run_id,
                            )
                    else:
                        log_warn(
                            f"[trader] SELL {symbol} fill price from API was invalid ({raw_fill:.2f}) "
                            f"— using quote price {price:.2f}",
                            self.run_id,
                        )
                        fill_price = price
                    if filled_qty > 0:
                        size_estimate = filled_qty

            except Exception as e:
                log_error(f"[trader] SELL {symbol} failed: {e}", self.run_id)
                discord.notify_error(f"SELL {symbol}", str(e))
                return

        # ── P&L from actual quantities (issue 4 fix) ──
        # Old: pnl = (fill / entry - 1) * usd_amount  ← used stale notional
        # New: proceeds - cost using ACTUAL size_estimate (potentially partial fill)
        proceeds = fill_price  * size_estimate
        cost     = entry_price * size_estimate
        pnl      = proceeds - cost

        mode = "DRY RUN " if self._dry_run else ""
        log(
            f"{mode}SELL {symbol} | fill={fill_price:.2f} | qty={size_estimate:.8f} | "
            f"proceeds=${proceeds:.4f} cost=${cost:.4f} pnl={pnl:+.4f} | reason={reason}",
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

        self.state["capital"] = self.state.get("capital", 0.0) + pnl
        del self.positions[symbol]

    def check_exit(self, symbol: str, price: float) -> str | None:
        pos = self.positions.get(symbol)
        if not pos:
            return None
        if price <= pos.get("stop_loss", float("-inf")):
            return "STOP_LOSS"
        if price >= pos.get("take_profit", float("inf")):
            return "TAKE_PROFIT"
        return None