# crypto_bot/execution/trader.py
#
# Trader reads/writes positions via the shared state dict (backed by state.json).
# engine.py owns the state dict — Trader mutates it in place.
#
# Order amounts are in notional USD (e.g. $10.00 of BTC) because Public's
# place_order API uses `amount` (notional) not `quantity` (base currency units).

from crypto_bot.exchange.public_api import get_primary_account_id, place_order
from crypto_bot.logging import supabase_logger
from crypto_bot.logging.logger import log, log_error
from crypto_bot.config.settings import STOP_LOSS_PCT, TAKE_PROFIT_PCT


class Trader:
    def __init__(self, state: dict, run_id: str | None = None):
        """
        Args:
            state:  loaded state dict with keys "capital" and "positions"
            run_id: current monitor run id, forwarded to trade logs
        """
        self.state = state
        self.run_id = run_id
        self._account_id = None  # lazy-fetched once per run

    @property
    def positions(self) -> dict:
        return self.state["positions"]

    def _get_account_id(self) -> str:
        if self._account_id is None:
            self._account_id = get_primary_account_id()
        return self._account_id

    # ── Orders ────────────────────────────────────────────────────────────────

    def buy(self, symbol: str, price: float, usd_amount: float) -> None:
        """
        Place a BUY order for `usd_amount` dollars worth of `symbol`.

        Args:
            symbol:     e.g. "BTC"
            price:      current price (for stop/TP calculation and logging)
            usd_amount: notional USD to spend, e.g. 10.00
        """
        pair = symbol + "USD"
        try:
            order = place_order(self._get_account_id(), pair, "BUY", usd_amount)
        except Exception as e:
            log_error(f"[trader] place_order BUY {symbol} failed: {e}", self.run_id)
            return

        size_estimate = usd_amount / price  # approximate — actual fill may differ

        self.positions[symbol] = {
            "entry": price,
            "usd_amount": usd_amount,
            "size_estimate": size_estimate,
            "stop_loss": round(price * (1 - STOP_LOSS_PCT), 6),
            "take_profit": round(price * (1 + TAKE_PROFIT_PCT), 6),
            "order_id": order.get("orderId") or order.get("_clientOrderId"),
        }

        log(
            f"BUY  {symbol} | price={price:.2f} | amount=${usd_amount:.2f} | "
            f"SL={self.positions[symbol]['stop_loss']:.2f} "
            f"TP={self.positions[symbol]['take_profit']:.2f}",
            self.run_id,
        )
        supabase_logger.log_trade(
            symbol, "BUY", price, size_estimate, 0.0, "entry", self.run_id
        )

    def sell(self, symbol: str, price: float, reason: str = "signal") -> None:
        """
        Sell the full open position in `symbol`.
        Uses the same USD amount that was used to buy.
        """
        if symbol not in self.positions:
            log_error(f"[trader] sell called for {symbol} but no open position", self.run_id)
            return

        pos = self.positions[symbol]
        usd_amount = pos["usd_amount"]
        size_estimate = pos.get("size_estimate", usd_amount / pos["entry"])

        # Estimate PnL: (current price / entry price - 1) * USD invested
        pnl = (price / pos["entry"] - 1) * usd_amount

        pair = symbol + "USD"
        try:
            place_order(self._get_account_id(), pair, "SELL", usd_amount)
        except Exception as e:
            log_error(f"[trader] place_order SELL {symbol} failed: {e}", self.run_id)
            return

        log(
            f"SELL {symbol} | price={price:.2f} | amount=${usd_amount:.2f} | "
            f"pnl={pnl:+.4f} | reason={reason}",
            self.run_id,
        )
        supabase_logger.log_trade(symbol, "SELL", price, size_estimate, pnl, reason, self.run_id)

        self.state["capital"] += pnl
        del self.positions[symbol]

    # ── Exit checks ───────────────────────────────────────────────────────────

    def check_exit(self, symbol: str, price: float) -> str | None:
        """Returns 'STOP_LOSS', 'TAKE_PROFIT', or None."""
        pos = self.positions.get(symbol)
        if not pos:
            return None
        if price <= pos["stop_loss"]:
            return "STOP_LOSS"
        if price >= pos["take_profit"]:
            return "TAKE_PROFIT"
        return None