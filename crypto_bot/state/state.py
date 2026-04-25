# crypto_bot/state/state.py

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
        # Cooldown: candle index at which a position last closed per symbol
        "last_exit_candle":   {},
    }


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return _default_state()
    try:
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
        data.setdefault("capital",            INITIAL_CAPITAL)
        data.setdefault("positions",          {})
        data.setdefault("price_history",      {})
        data.setdefault("consecutive_losses", {})
        data.setdefault("circuit_notified",   {})
        data.setdefault("last_daily_summary", "")
        data.setdefault("last_exit_candle",   {})
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
    losses = state.setdefault("consecutive_losses", {})
    losses[symbol] = losses.get(symbol, 0) + 1
    return losses[symbol]


def record_win(state: dict, symbol: str) -> None:
    state.setdefault("consecutive_losses", {})[symbol] = 0
    state.setdefault("circuit_notified", {}).pop(symbol, None)


def get_consecutive_losses(state: dict, symbol: str) -> int:
    return state.get("consecutive_losses", {}).get(symbol, 0)


def is_circuit_broken(state: dict, symbol: str, threshold: int) -> bool:
    return get_consecutive_losses(state, symbol) >= threshold


def should_notify_circuit_broken(state: dict, symbol: str) -> bool:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return state.setdefault("circuit_notified", {}).get(symbol, "") != today


def mark_circuit_notified(state: dict, symbol: str) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    state.setdefault("circuit_notified", {})[symbol] = today


# ── Cooldown tracking (NEW) ───────────────────────────────────────────────────

def record_exit(state: dict, symbol: str) -> None:
    """
    Record the candle index at which a position was closed.
    Used to enforce a cooldown before re-entering the same symbol.
    """
    current_candle = len(state.get("price_history", {}).get(symbol, []))
    state.setdefault("last_exit_candle", {})[symbol] = current_candle


def candles_since_exit(state: dict, symbol: str) -> int | None:
    """
    Returns number of candles elapsed since last exit on this symbol.
    Returns None if no prior exit recorded (no cooldown applies).
    """
    last_exit = state.get("last_exit_candle", {}).get(symbol)
    if last_exit is None:
        return None
    current = len(state.get("price_history", {}).get(symbol, []))
    return current - last_exit