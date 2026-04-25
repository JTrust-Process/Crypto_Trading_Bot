# crypto_bot/state/state.py
#
# Schema:
# {
#   "capital": 50.0,
#   "positions": {
#     "BTC": {
#       "entry": 67000.0, "usd_amount": 10.0, "size_estimate": 0.000149,
#       "stop_loss": 64990.0, "take_profit": 70350.0,
#       "entry_candle": 22
#     }
#   },
#   "price_history":      { "BTC": [...], "ETH": [...] },
#   "consecutive_losses": { "BTC": 0, "ETH": 2 },
#   "circuit_notified":   { "BTC": "2025-04-22" },  # last date we pinged Discord
#   "last_daily_summary": "2025-04-22"
# }

import json
import os
from datetime import datetime, timezone
from crypto_bot.config.settings import STATE_FILE, INITIAL_CAPITAL, PRICE_HISTORY_SIZE


def _default_state() -> dict:
    return {
        "capital":            INITIAL_CAPITAL,
        "positions":          {},
        "price_history":      {},
        "consecutive_losses": {},
        "circuit_notified":   {},
        "last_daily_summary": "",
    }


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return _default_state()
    try:
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
        # Ensure all keys exist — protects against stale state files
        data.setdefault("capital",            INITIAL_CAPITAL)
        data.setdefault("positions",          {})
        data.setdefault("price_history",      {})
        data.setdefault("consecutive_losses", {})
        data.setdefault("circuit_notified",   {})
        data.setdefault("last_daily_summary", "")
        return data
    except (json.JSONDecodeError, OSError):
        return _default_state()


def save_state(state: dict) -> None:
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)


def append_price(state: dict, symbol: str, price: float) -> None:
    history = state.setdefault("price_history", {}).setdefault(symbol, [])
    history.append(price)
    if len(history) > PRICE_HISTORY_SIZE:
        state["price_history"][symbol] = history[-PRICE_HISTORY_SIZE:]


def get_price_history(state: dict, symbol: str) -> list:
    return state.get("price_history", {}).get(symbol, [])


def record_loss(state: dict, symbol: str) -> int:
    """Increment consecutive loss counter. Returns new count."""
    losses = state.setdefault("consecutive_losses", {})
    losses[symbol] = losses.get(symbol, 0) + 1
    return losses[symbol]


def record_win(state: dict, symbol: str) -> None:
    """Reset consecutive loss counter on a winning trade."""
    state.setdefault("consecutive_losses", {})[symbol] = 0
    # Also clear circuit notification so next time it trips it'll ping again
    state.setdefault("circuit_notified", {}).pop(symbol, None)


def get_consecutive_losses(state: dict, symbol: str) -> int:
    return state.get("consecutive_losses", {}).get(symbol, 0)


def is_circuit_broken(state: dict, symbol: str, threshold: int) -> bool:
    """Returns True if symbol should be paused due to too many consecutive losses."""
    return get_consecutive_losses(state, symbol) >= threshold


# ── Circuit breaker notification tracking (issue 12) ──────────────────────────

def should_notify_circuit_broken(state: dict, symbol: str) -> bool:
    """
    Returns True if we should send a Discord ping for circuit breaker on this symbol.
    Only fires once per UTC day per symbol — prevents spam every 15 min.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    last_notified = state.setdefault("circuit_notified", {}).get(symbol, "")
    return last_notified != today


def mark_circuit_notified(state: dict, symbol: str) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    state.setdefault("circuit_notified", {})[symbol] = today