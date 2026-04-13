# crypto_bot/state/state.py
#
# Schema:
# {
#   "capital": 15.0,
#   "positions": {
#     "BTC": {"entry": 67000.0, "usd_amount": 10.0, "size_estimate": 0.000149,
#             "stop_loss": 64990.0, "take_profit": 70350.0}
#   },
#   "price_history": {
#     "BTC": [67000.0, 67250.0, ...],
#     "ETH": [2300.0, ...]
#   },
#   "consecutive_losses": {
#     "BTC": 0,
#     "ETH": 2
#   }
# }

import json
import os
from crypto_bot.config.settings import STATE_FILE, INITIAL_CAPITAL, PRICE_HISTORY_SIZE


def _default_state() -> dict:
    return {
        "capital":            INITIAL_CAPITAL,
        "positions":          {},
        "price_history":      {},
        "consecutive_losses": {},
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
        return data
    except (json.JSONDecodeError, OSError):
        return _default_state()


def save_state(state: dict) -> None:
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)


def append_price(state: dict, symbol: str, price: float) -> None:
    history = state["price_history"].setdefault(symbol, [])
    history.append(price)
    if len(history) > PRICE_HISTORY_SIZE:
        state["price_history"][symbol] = history[-PRICE_HISTORY_SIZE:]


def get_price_history(state: dict, symbol: str) -> list[float]:
    return state["price_history"].get(symbol, [])


def record_loss(state: dict, symbol: str) -> int:
    """Increment consecutive loss counter. Returns new count."""
    losses = state["consecutive_losses"].get(symbol, 0) + 1
    state["consecutive_losses"][symbol] = losses
    return losses


def record_win(state: dict, symbol: str) -> None:
    """Reset consecutive loss counter on a winning trade."""
    state["consecutive_losses"][symbol] = 0


def get_consecutive_losses(state: dict, symbol: str) -> int:
    return state["consecutive_losses"].get(symbol, 0)


def is_circuit_broken(state: dict, symbol: str, threshold: int) -> bool:
    """Returns True if symbol should be paused due to too many consecutive losses."""
    return get_consecutive_losses(state, symbol) >= threshold