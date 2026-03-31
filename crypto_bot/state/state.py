# crypto_bot/state/state.py
#
# Schema:
# {
#   "capital": 30.0,
#   "positions": {
#     "BTC": {"entry": 67000.0, "usd_amount": 33.33, "size_estimate": 0.000498,
#             "stop_loss": 64990.0, "take_profit": 70350.0, "order_id": "..."}
#   },
#   "price_history": {
#     "BTC": [67000.0, 67250.0, 66800.0, ...],   # up to PRICE_HISTORY_SIZE entries
#     "ETH": [2300.0, 2310.0, ...]
#   }
# }

import json
import os
from crypto_bot.config.settings import STATE_FILE, INITIAL_CAPITAL, PRICE_HISTORY_SIZE


def _default_state() -> dict:
    return {
        "capital": INITIAL_CAPITAL,
        "positions": {},
        "price_history": {},
    }


def load_state() -> dict:
    """Load state from disk. Returns default state if file missing or corrupt."""
    if not os.path.exists(STATE_FILE):
        return _default_state()
    try:
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
        data.setdefault("capital", INITIAL_CAPITAL)
        data.setdefault("positions", {})
        data.setdefault("price_history", {})
        return data
    except (json.JSONDecodeError, OSError):
        return _default_state()


def save_state(state: dict) -> None:
    """Write state to disk atomically."""
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)


def append_price(state: dict, symbol: str, price: float) -> None:
    """
    Append a new price to the rolling history for a symbol.
    Trims to PRICE_HISTORY_SIZE so the file doesn't grow unbounded.
    """
    history = state["price_history"].setdefault(symbol, [])
    history.append(price)
    if len(history) > PRICE_HISTORY_SIZE:
        state["price_history"][symbol] = history[-PRICE_HISTORY_SIZE:]


def get_price_history(state: dict, symbol: str) -> list[float]:
    """Returns the stored price history for a symbol (may be empty on first runs)."""
    return state["price_history"].get(symbol, [])